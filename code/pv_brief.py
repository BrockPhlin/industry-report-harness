"""Generate, compare and confirm a photovoltaic brief from the command line."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from report_app.errors import AppError
from report_app.generator import excerpt_report, read_config
from report_app.pv_checkpoint import RunCheckpoint, input_fingerprint
from report_app.pv_evidence import CODE_DIR, fact_line, load_inputs, search_evidence
from report_app.pv_model import ChatWriter


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def review_contract(markdown, protected_lines):
    """Keep verified evidence and status under their original headings."""
    selected = set(protected_lines)
    return [line for line in markdown.splitlines()
            if line.startswith(("# ", "## ")) or line in selected
            or line.startswith(("运行方式：", "- 待核实："))]


def baseline_sources(sources, facts):
    return [dict(source, body="【公开统计资料人工摘编】\n" +
                 "\n".join(fact_line(fact).rsplit(" [", 1)[0] for fact in facts.values()
                           if fact["source"] == source["id"]))
            for source in sources.values()]


def create_run(args):
    from report_app.pv_agent import FixtureWriter, generate_brief

    if args.output.exists():
        raise AppError("任务目录已存在，请指定新目录")
    template, sources, facts = load_inputs(args.omit_source)
    if not sources:
        raise AppError("演示任务至少需要一份资料")
    if args.mode == "live":
        model = ChatWriter(read_config(CODE_DIR / ".env"))
        route = model.connection[:2]
    else:
        model = FixtureWriter()
        route = None
    checkpoint = RunCheckpoint(args.output)
    identity = input_fingerprint(template, sources, facts, args.mode, route)
    with checkpoint.open(identity, args.resume):
        if args.output.exists():
            raise AppError("任务目录已存在，请指定新目录")
        draft, trace = generate_brief(template, sources, facts, model, args.mode, checkpoint=checkpoint)
        baseline, _ = excerpt_report(template["title"], baseline_sources(sources, facts))
        trace["review_contract"] = review_contract(draft, trace["protected_lines"])
        with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
            staging = Path(tmp) / "run"
            staging.mkdir()
            (staging / "draft.md").write_text(draft, encoding="utf-8")
            (staging / "baseline.md").write_text(baseline, encoding="utf-8")
            write_json(staging / "trace.json", trace)
            staging.rename(args.output)
    shutil.rmtree(checkpoint.path, ignore_errors=True)
    print(f"草稿、同源摘录基线、调用记录已写入 {args.output}。未核实指标 {len(trace['missing'])} 项。")


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


def approve_run(args):
    trace = json.loads((args.output / "trace.json").read_text(encoding="utf-8"))
    draft_path = args.markdown or args.output / "draft.md"
    draft = draft_path.read_text(encoding="utf-8")
    if len(draft) > 20000:
        raise AppError("审阅稿不能超过20000字符")
    if review_contract(draft, trace["protected_lines"]) != trace["review_contract"]:
        raise AppError("审阅稿更改了指标、待核实项或对应来源，请重新生成后核对")
    status = "状态：已按命令确认，仍有待核实项。" if trace["missing"] else "状态：已按命令确认。"
    if draft.count("状态：待人工核对。") != 1:
        raise AppError("审阅稿缺少唯一的待确认标识")
    approved = draft.replace("状态：待人工核对。", status, 1)
    final_dir = args.output / "reviewed"
    if final_dir.exists():
        raise AppError("此任务已有核对件，请使用新任务或保留旧件后重跑")
    if not shutil.which("typst"):
        raise AppError("导出 PDF 需要安装 Typst")
    with tempfile.TemporaryDirectory(dir=args.output) as tmp:
        staging = Path(tmp)
        write_json(staging / "brief.json", list(pdf_blocks(approved)))
        shutil.copyfile(CODE_DIR / "templates/pv-brief.typ", staging / "brief.typ")
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
            "mode": trace["mode"], "missing": trace["missing"],
            "markdown_sha256": sha256(approved.encode()).hexdigest(),
            "source_approval": "explicit_cli_confirmation",
        })
        finished.rename(final_dir)
    print(f"已导出 {final_dir / 'brief.pdf'}")


def evidence_command(args):
    _, sources, facts = load_inputs(args.omit_source)
    print(json.dumps(search_evidence(args.keys, sources, facts), ensure_ascii=False, indent=2))


def inspect_run(args):
    trace = json.loads((args.output / "trace.json").read_text(encoding="utf-8"))
    if args.json:
        public = {key: trace[key] for key in ("mode", "framework", "sources", "events", "missing")}
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
            print(f"{event['section']} 草稿｜采用 {completed}｜待核实 {pending}")
        else:
            verb = "补查" if event["stage"] == "supplement" else "检索"
            received = "、".join(f"{hit['fact']} [{hit['source']}]" for hit in event["returned"]) or "无结果"
            print(f"{event['section']} {verb}｜返回 {received}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="生成草稿和可审计运行记录")
    run.add_argument("output", type=Path, help="新建任务目录，其上级必须存在")
    run.add_argument("--mode", choices=("fixture", "live"), required=True)
    run.add_argument("--omit-source", action="append", default=[], help="用指定来源缺失验证补查分支")
    run.add_argument("--resume", action="store_true", help="从相同输入的最后一个完整章节继续")
    run.set_defaults(handler=create_run)
    approve = commands.add_parser("approve", help="显式确认已核对的 Markdown 并导出")
    approve.add_argument("output", type=Path)
    approve.add_argument("--confirm", action="store_true", required=True)
    approve.add_argument("--markdown", type=Path, help="可选的审阅后 Markdown 文件")
    approve.set_defaults(handler=approve_run)
    evidence = commands.add_parser("evidence", help="单独运行资料检索工具")
    evidence.add_argument("keys", nargs="+")
    evidence.add_argument("--omit-source", action="append", default=[])
    evidence.set_defaults(handler=evidence_command)
    inspect = commands.add_parser("inspect", help="查看已保存的工具调用和待核实项")
    inspect.add_argument("output", type=Path)
    inspect.add_argument("--json", action="store_true", help="输出机器可读记录")
    inspect.set_defaults(handler=inspect_run)
    args = parser.parse_args()
    try:
        args.handler(args)
    except (AppError, OSError, UnicodeError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"任务失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
