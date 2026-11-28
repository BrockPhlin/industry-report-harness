"""Generate, audit and confirm a photovoltaic brief from the command line."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from report_app.errors import AppError
from report_app.generator import read_config
from report_app.pv_checkpoint import RunCheckpoint, input_fingerprint
from report_app.pv_evidence import CODE_DIR, load_inputs, search_evidence
from report_app.pv_model import ChatWriter


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def review_contract(markdown, protected_lines):
    """Keep verified evidence and status under their original headings."""
    selected = set(protected_lines)
    return [line for line in markdown.splitlines()
            if line.startswith(("# ", "## ")) or line in selected
            or line.startswith(("运行方式：", "- 待核实：", "- 候选资料："))]


def create_run(args, *, config=None, question=None, focus=None):
    from report_app.pv_agent import FixtureWriter, generate_brief

    if args.output.exists():
        raise AppError("任务目录已存在，请指定新目录")
    template, sources, facts = load_inputs(args.omit_source, template_path=args.template, corpus_path=args.corpus)
    if focus is not None:
        sections = [s for s in template["sections"] if s["title"] in focus]
        if not sections or len(sections) != len(focus):
            raise AppError("请选择模板中已有的研究重点")
        template = dict(template, sections=[dict(s, research_question=question) for s in sections],
                        scope="本次依据公开统计，核对2024年中国光伏的" +
                              "、".join(s["title"] for s in sections) + "。")
    if not sources:
        raise AppError("演示任务至少需要一份资料")
    if args.mode == "live":
        model = ChatWriter(read_config(CODE_DIR / ".env") if config is None else config, request_timeout=args.request_timeout)
        route = model.connection[:2]
    else:
        model = FixtureWriter()
        route = None
    checkpoint = RunCheckpoint(args.output)
    identity = input_fingerprint(template, sources, facts, args.mode, route)
    with checkpoint.open(identity, args.resume):
        if args.output.exists():
            raise AppError("任务目录已存在，请指定新目录")
        try:
            draft, trace = generate_brief(template, sources, facts, model, args.mode, checkpoint=checkpoint)
        except AppError as exc:
            if exc.code not in {"model_timeout", "model_unavailable"}:
                raise
            raise AppError(f"{exc}。已保存 {len(checkpoint.completed)} 章。重跑原命令并追加 --resume 可继续。",
                           exc.status, exc.code) from None
        trace["review_contract"] = review_contract(draft, trace["protected_lines"])
        with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
            staging = Path(tmp) / "run"
            staging.mkdir()
            (staging / "draft.md").write_text(draft, encoding="utf-8")
            write_json(staging / "trace.json", trace)
            staging.rename(args.output)
    shutil.rmtree(checkpoint.path, ignore_errors=True)
    print(f"草稿和调用记录已写入 {args.output}。缺资料 {len(trace['missing'])} 项，"
          f"资料表述不一致 {len(trace['conflicts'])} 项。")


def pdf_blocks(markdown):
    link = re.compile(r"^\[([^\]]+)\]\((https://[^\s)]+)\)(.*)$")
    for line in markdown.splitlines():
        line = line.strip()
        if not line:
            continue
        match = link.match(line)
        if match:
            label, url, detail = match.groups()
            yield {"kind": "link", "text": label + detail, "url": url}
            continue
        prefix, sep, tail = line.partition(" ")
        kinds = {"#": "title", "##": "heading", "-": "bullet"}
        yield {"kind": kinds.get(prefix, "paragraph"), "text": tail if sep and prefix in kinds else line}


def study_blocks(markdown, charts=(), evidence=()):
    rows = []
    table_number = 0
    figures = {chart.get("table_number",1): chart for chart in charts}
    links = {row["ref"]:row["url"] for row in evidence}
    for block in pdf_blocks(markdown):
        line = block["text"]
        if line.startswith("|") and line.endswith("|"):
            if not re.fullmatch(r"[| :\-]+", line):
                rows.append([cell.strip() for cell in line[1:-1].split("|")])
            continue
        if rows:
            table_number += 1
            yield {"kind": "table", "rows": rows}
            if table_number in figures:
                yield {"kind":"chart", **figures[table_number]}
            rows = []
        if block["kind"] == "heading" and line == "摘要":
            yield {"kind": "contents"}
        if block["kind"] == "paragraph":
            if re.match(r"^表 \d+",line):
                block["kind"] = "caption"
            pieces = re.split(r"(\[E\d+\])",line)
            if len(pieces)>1:
                block["spans"] = [{"text":part,"url":links.get(part[1:-1])} for part in pieces if part]
        yield block
    if rows:
        yield {"kind": "table", "rows": rows}
        if table_number+1 in figures:
            yield {"kind":"chart", **figures[table_number+1]}


def approve_run(args, *, confirmation="explicit_cli_confirmation"):
    trace = json.loads((args.output / "trace.json").read_text(encoding="utf-8"))
    draft_path = args.markdown or args.output / "draft.md"
    draft = draft_path.read_text(encoding="utf-8")
    is_long = trace.get("kind") == "long"
    if len(draft) > (90000 if is_long else 20000):
        raise AppError("审阅稿超过导出长度上限")
    if is_long and args.markdown:
        from report_app.long_report import editorial_revision
        editorial_revision((args.output / "draft.md").read_text(encoding="utf-8"),draft,trace.get("evidence"))
    elif review_contract(draft, trace["protected_lines"]) != trace["review_contract"]:
        raise AppError("审阅稿更改了指标、待核实项或对应来源，请重新生成后核对")
    pending = trace["missing"] or trace.get("conflicts")
    status = "状态：已按命令确认，仍有待核实项。" if pending else "状态：已按命令确认。"
    if draft.count("状态：待人工核对。") != 1:
        raise AppError("审阅稿缺少唯一的待确认标识")
    if confirmation == "explicit_web_confirmation":
        status = status.replace("按命令确认", "经网页审阅确认")
    approved = draft.replace("状态：待人工核对。", status, 1)
    final_dir = args.output / "reviewed"
    if final_dir.exists():
        raise AppError("此任务已有核对件，请使用新任务或保留旧件后重跑")
    if not shutil.which("typst"):
        raise AppError("导出 PDF 需要安装 Typst")
    with tempfile.TemporaryDirectory(dir=args.output) as tmp:
        staging = Path(tmp)
        charts = trace.get("charts", [trace["chart"]] if trace.get("chart") else [])
        blocks = study_blocks(approved,charts,trace.get("evidence",[])) if is_long else pdf_blocks(approved)
        write_json(staging / "brief.json", list(blocks))
        template = "solar-study.typ" if is_long else "pv-brief.typ"
        shutil.copyfile(CODE_DIR / "templates" / template, staging / "brief.typ")
        fonts = CODE_DIR.parent / "assets/fonts"
        result = subprocess.run(["typst", "compile", "--font-path", str(fonts), "brief.typ", "brief.pdf"],
                                cwd=staging, capture_output=True, text=True, timeout=30)
        if result.returncode or not (staging / "brief.pdf").is_file():
            raise AppError("Typst 未成功生成 PDF", 500, "pdf_export_failed")
        finished = staging / "reviewed"
        finished.mkdir()
        (finished / "brief.md").write_text(approved, encoding="utf-8")
        shutil.move(staging / "brief.pdf", finished / "brief.pdf")
        write_json(finished / "confirmation.json", {
            "mode": trace["mode"], "missing": trace["missing"], "conflicts": trace.get("conflicts", []),
            "markdown_sha256": sha256(approved.encode()).hexdigest(),
            "source_approval": confirmation,
        })
        finished.rename(final_dir)
    print(f"已导出 {final_dir / 'brief.pdf'}")


def evidence_command(args):
    _, sources, facts = load_inputs(args.omit_source, template_path=args.template, corpus_path=args.corpus)
    print(json.dumps(search_evidence(args.keys, sources, facts), ensure_ascii=False, indent=2))


def inspect_run(args):
    trace = json.loads((args.output / "trace.json").read_text(encoding="utf-8"))
    if trace.get("kind") == "long":
        if args.json:
            fields = ("plan", "target", "body_length", "evidence", "retrieval", "missing", "operations")
            print(json.dumps({field: trace[field] for field in fields if field in trace}, ensure_ascii=False, indent=2))
        else:
            print(f"{trace['plan']['title']} ｜ 正文 {trace['body_length']} 字")
            for source in trace["retrieval"]:
                print(f"{source['source']} ｜ {source['result']}")
            for item in trace["missing"]:
                print("待补资料 ｜ " + item)
        return
    if args.json:
        public = {key: trace[key] for key in ("mode", "framework", "sources", "events", "missing")}
        if trace.get("conflicts"):
            public["conflicts"] = trace["conflicts"]
        if trace.get("resumed_sections"):
            public["resumed_sections"] = trace["resumed_sections"]
        print(json.dumps(public, ensure_ascii=False, indent=2))
        return
    print(f"{trace['framework']} ｜ {trace['mode']}")
    if trace.get("resumed_sections"):
        print(f"本次跳过已完成章节 {trace['resumed_sections']} 个")
    for event in trace["events"]:
        if event["stage"] == "resume_retry":
            print(f"{event['section']} 恢复｜从头重跑本章 {event['attempts']} 次")
        elif event["stage"] == "draft":
            completed = "、".join(event["selected"]) or "无证据"
            pending = "、".join(event["missing"]) or "无"
            conflicts = "、".join(event.get("conflicts", [])) or "无"
            print(f"{event['section']} 草稿｜采用 {completed}｜缺资料 {pending}｜资料表述不一致 {conflicts}")
        else:
            verb = "补查" if event["stage"] == "supplement" else "检索"
            received = "、".join(f"{hit['fact']} [{hit['source']}]" for hit in event["returned"]) or "无结果"
            print(f"{event['section']} {verb}｜返回 {received}")


def seconds(raw):
    value = float(raw)
    if not math.isfinite(value) or not 0 < value <= 600:
        raise argparse.ArgumentTypeError("请求超时须大于 0 秒且最多 600 秒")
    return value


def audit_export(args):
    from report_app.report_review import review_report

    raw = args.markdown.read_bytes()
    bundle = json.loads(args.evidence.read_text(encoding="utf-8"))
    if not isinstance(bundle, dict) or bundle.get("markdown_sha256") != sha256(raw).hexdigest():
        raise AppError("正文指纹不匹配，请选择同一次导出的 Markdown 和证据 JSON")
    rows = bundle.get("evidence")
    if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("ref"), str) for r in rows):
        raise AppError("证据 JSON 缺少可识别的证据记录")
    result = review_report(raw.decode("utf-8"), rows)
    result["markdown_sha256"] = bundle["markdown_sha256"]
    print(json.dumps(result, ensure_ascii=False, indent=2))


def input_options(command):
    command.add_argument("--template", type=Path, help="章节模板 JSON，默认使用光伏模板")
    command.add_argument("--corpus", type=Path, help="来源及指标 JSON，默认使用光伏样例")
    command.add_argument("--omit-source", action="append", default=[], help="临时排除指定来源")


def compare_provinces(args):
    from report_app.comparison_report import render_comparison
    from report_app.province_comparison import build_comparison, comparison_catalog

    selection = comparison_catalog()["default"].copy()
    for name in ("period", "metric", "regions"):
        if getattr(args, name) is not None:
            selection[name] = getattr(args, name)
    if args.output.exists():
        raise AppError("输出目录已存在，请为分省对比选择新目录")
    result = build_comparison(selection)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        stage = Path(tmp) / "comparison"
        stage.mkdir()
        (stage / "report.md").write_bytes(render_comparison(result, "markdown"))
        (stage / "calculation.json").write_bytes(render_comparison(result, "json"))
        if args.pdf:
            (stage / "report.pdf").write_bytes(render_comparison(result, "pdf"))
        stage.rename(args.output)
    print(f"分省对比及复算记录已写入 {args.output}")


def verify_exported_comparison(args):
    from report_app.comparison_report import verify_comparison

    bundle = json.loads(args.calculation.read_text(encoding="utf-8"))
    result = verify_comparison(bundle, args.markdown.read_bytes() if args.markdown else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("compare", help="离线生成分省光伏对比报告及复算记录")
    compare.add_argument("output", type=Path, help="保存报告的新目录")
    compare.add_argument("--period", choices=("half_year", "annual", "three_quarters"))
    compare.add_argument("--metric", help="指标编号，例如 central_new 或 distributed_stock")
    compare.add_argument("--regions", nargs="+", help="参与比较的省级地区简称，用空格隔开")
    compare.add_argument("--pdf", action="store_true", help="同时导出 PDF，需要 Typst")
    compare.set_defaults(handler=compare_provinces)
    verify = commands.add_parser("verify-comparison", help="用仓库原表复算已下载的计算记录")
    verify.add_argument("calculation", type=Path)
    verify.add_argument("--markdown", type=Path, help="一并核对 Markdown 原始文件的指纹")
    verify.set_defaults(handler=verify_exported_comparison)
    run = commands.add_parser("run", help="生成草稿和可审计运行记录")
    run.add_argument("output", type=Path, help="新建任务目录，其上级必须存在")
    run.add_argument("--mode", choices=("fixture", "live"), required=True)
    input_options(run)
    run.add_argument("--request-timeout", type=seconds, default=60, help="模型请求等待网络响应的秒数，默认 60")
    run.add_argument("--resume", action="store_true", help="从相同输入的最后一个完整章节继续")
    run.set_defaults(handler=create_run)
    approve = commands.add_parser("approve", help="显式确认已核对的 Markdown 并导出")
    approve.add_argument("output", type=Path)
    approve.add_argument("--confirm", action="store_true", required=True)
    approve.add_argument("--markdown", type=Path, help="可选的审阅后 Markdown 文件")
    approve.set_defaults(handler=approve_run)
    evidence = commands.add_parser("evidence", help="单独运行资料检索工具")
    evidence.add_argument("keys", nargs="+")
    input_options(evidence)
    evidence.set_defaults(handler=evidence_command)
    inspect = commands.add_parser("inspect", help="查看已保存的工具调用和待核实项")
    inspect.add_argument("output", type=Path)
    inspect.add_argument("--json", action="store_true", help="输出机器可读记录")
    inspect.set_defaults(handler=inspect_run)
    audit = commands.add_parser("audit", help="离线核对已导出的报告正文与引用")
    audit.add_argument("markdown", type=Path)
    audit.add_argument("evidence", type=Path)
    audit.set_defaults(handler=audit_export)
    args = parser.parse_args()
    try:
        args.handler(args)
    except (AppError, OSError, UnicodeError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"任务失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
