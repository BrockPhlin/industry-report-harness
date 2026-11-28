"""Human-readable reports and offline replay bundles for a two-period provincial comparison."""
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from .errors import AppError


SCHEMA = "pv-province-comparison"
VERSION = 2
ROOT = Path(__file__).resolve().parents[2]
LEGACY_RANK_NOTE = "按后期原表数值降序排列，名次限所选且两期可比的地区。并列地区同名次，下一名按实际顺位。"


def _names(rows):
    names = [row["region"] for row in rows]
    if len(names) > 4:
        return "、".join(names[:3]) + f"等 {len(names)} 个地区"
    return "、".join(names)


def _findings(rows, plan):
    unit = plan["unit"]
    if not rows:
        return ["所选地区都缺少可直接对照的两期记录。下表列出已取得的原值和各地缺口。"]
    leaders = [r for r in rows if r["rank"] == 1]
    leader = leaders[0]
    position = "并列第一" if len(leaders) > 1 else "位居第一"
    findings = [f"{plan['after_year']} 年，{_names(leaders)}在所选可比地区中{position}，"
                f"{plan['metric_label']}为 {leader['after']} {unit}。"]
    deltas = [Decimal(r["delta"]) for r in rows]
    positive = sum(d > 0 for d in deltas)
    negative = sum(d < 0 for d in deltas)
    directions = [(positive, "增加"), (negative, "减少"), (len(deltas) - positive - negative, "持平")]
    findings.append("两期相比，" + "，".join(f"{n} 个地区{label}" for n, label in directions if n) + "。")
    for value, direction in ((max(deltas), "增加"), (min(deltas), "减少")):
        if (direction == "增加" and value <= 0) or (direction == "减少" and value >= 0):
            continue
        group = [r for r in rows if Decimal(r["delta"]) == value]
        if len(group) == 1:
            row = group[0]
            findings.append(f"{row['region']}的{direction}量最大。上期为 {row['before']} {unit}，"
                            f"本期为 {row['after']} {unit}，两期相差 {abs(value):f} {unit}。")
        else:
            findings.append(f"{_names(group)}的{direction}量相同，均为 {abs(value):f} {unit}，在可比地区中并列最大。")
    return findings


def _has_period_ranks(rows):
    return all("before_rank" in row for row in rows)


def _table(head, rows):
    return "\n".join("| " + " | ".join(cells) + " |" for cells in [head, ["---"] * len(head), *rows])


def _markdown(result):
    plan, rows, missing = result["plan"], result["rows"], result["missing"]
    before, after, unit = plan["before_year"], plan["after_year"], plan["unit"]
    measure = plan["metric_label"]
    title_measure = measure
    for time_label in ("上半年", "前三季度", "截至六月底", "截至九月底", "年末"):
        title_measure = title_measure.replace(time_label, "")
    blocks = [f"# {title_measure}分省比较",
              f"{plan['period_label']}，共选取 {len(plan['regions'])} 个地区，其中 {len(rows)} 个可比较。"
              f"数据来自国家能源局两期分省并网表，计量单位为{unit}。",
              "## 主要结果", *_findings(rows, plan)]
    if rows:
        both_ranks = _has_period_ranks(rows)
        rank_heading = "名次变化" if both_ranks else "名次"
        caption = f"表 1　{measure}（{unit}），名次按 {after} 年数值从高到低排列。"
        if both_ranks:
            caption += f"名次变化按 {before} 年 → {after} 年列示，两期参加排名的地区相同。"
        blocks += ["## 两期数据与排名",
                   caption,
                   _table([rank_heading, "地区", f"{before} 年", f"{after} 年", "变化量", "相对变化率"],
                          [[f"{r['before_rank']}→{r['rank']}" if both_ranks else str(r["rank"]),
                            r["region"], r["before"], r["after"], r["delta"],
                            (r["growth_pct"] + "%") if r["growth_pct"] is not None else "—"] for r in rows])]
        for note in dict.fromkeys(r["growth_note"] for r in rows if r.get("growth_note")):
            affected = [r for r in rows if r["growth_note"] == note]
            blocks.append(f"{_names(affected)}未列相对变化率。{note.rstrip('。')}。")
        negative_cells = [r for r in rows if min(Decimal(r["before"]), Decimal(r["after"])) < 0]
        if negative_cells:
            blocks.append(f"{_names(negative_cells)}的原表记录含负值，表中按原符号列示。")
    if missing:
        blocks += ["## 资料缺口",
                   _table(["地区", f"{before} 年", f"{after} 年", "未作比较的原因"],
                          [[r["region"], r["before"] if r["before"] is not None else "—",
                            r["after"] if r["after"] is not None else "—", r["reason"]] for r in missing])]
    blocks += ["## 统计口径与计算方法", *result["notes"],
               "两期原值沿用原表的小数位。变化量按十进制计算，保留原值中较多的小数位数。"]
    blocks.append("## 两期原始资料")
    for source in result["sources"]:
        blocks.append(f"[国家能源局《{source['title']}》]({source['url']})")
        if source["data_url"] != source["url"]:
            blocks.append(f"[查看 {source['year']} 年分省数据原表]({source['data_url']})")
    blocks.append(f"核对原值时，在上述两张表中找到相应地区行，再查看“{measure}”列。")
    return "\n\n".join(blocks) + "\n"


def _pdf(markdown):
    from pv_brief import study_blocks

    binary = shutil.which("typst")
    if not binary:
        raise AppError("导出比较报告 PDF 需要安装 Typst。", 503, "pdf_export_failed")
    with TemporaryDirectory(prefix="pv-comparison-") as tmp:
        folder = Path(tmp)
        (folder / "brief.json").write_text(
            json.dumps(list(study_blocks(markdown)), ensure_ascii=False), encoding="utf-8"
        )
        shutil.copyfile(ROOT / "code/templates/province-comparison.typ", folder / "brief.typ")
        try:
            subprocess.run(
                [binary, "compile", "--font-path", str(ROOT / "assets/fonts"), "brief.typ", "brief.pdf"],
                cwd=folder, capture_output=True, check=True, timeout=30,
            )
            return (folder / "brief.pdf").read_bytes()
        except (OSError, subprocess.SubprocessError) as exc:
            raise AppError("比较报告 PDF 生成失败，请检查 Typst 后重试。", 500, "pdf_export_failed") from exc


def render_comparison(result, format, *, markdown=None):
    """Return one download. Persisted Markdown is the source of truth for PDF layout."""
    body = _markdown(result) if markdown is None else markdown
    raw = body.encode("utf-8")
    if format in {"md", "markdown"}:
        return raw
    if format == "pdf":
        return _pdf(body)
    if format == "json":
        version = VERSION if _has_period_ranks(result["rows"]) else 1
        bundle = dict(result, schema=SCHEMA, version=version, markdown_sha256=sha256(raw).hexdigest())
        return (json.dumps(bundle, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    raise ValueError("比较报告支持 Markdown、PDF 和 JSON")


def verify_comparison(bundle, markdown=None):
    """Rebuild numeric results from local pinned files. No paths or links in the bundle are opened."""
    from .province_comparison import build_comparison

    if (not isinstance(bundle, dict) or bundle.get("schema") != SCHEMA
            or type(bundle.get("version")) is not int or bundle["version"] not in (1, VERSION)):
        raise ValueError("无法识别比较报告 JSON 的格式或版本")
    if not isinstance(bundle.get("plan"), dict):
        raise ValueError("比较报告缺少可重算的选择条件")
    selection = {key: bundle["plan"].get(key) for key in ("period", "metric", "regions")}
    try:
        expected = build_comparison(selection)
    except (KeyError, TypeError) as exc:
        raise ValueError("比较报告选择条件有误") from exc
    if bundle["version"] == 1:
        for row in expected["rows"]:
            row.pop("before_rank", None)
        if isinstance(bundle.get("notes"), list) and bundle["notes"][:1] == [LEGACY_RANK_NOTE]:
            expected["notes"][0] = LEGACY_RANK_NOTE
    for key, value in expected.items():
        # Canonical JSON equality retains the distinction between a boolean and an integer.
        try:
            received = json.dumps(bundle.get(key), sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"比较报告的 {key} 格式有误") from exc
        if received != json.dumps(value, sort_keys=True, allow_nan=False):
            raise ValueError(f"比较报告的 {key} 与本地归档重算结果不一致")
    canonical = sha256(_markdown(expected).encode()).hexdigest()
    if canonical != bundle.get("markdown_sha256"):
        raise ValueError("比较报告正文指纹与重算结果不一致")
    if markdown is not None:
        raw = markdown.encode("utf-8") if isinstance(markdown, str) else markdown
        if not isinstance(raw, bytes) or sha256(raw).hexdigest() != canonical:
            raise ValueError("所给 Markdown 文件与比较报告正文指纹不一致")
    return {"verified": True, "rows": len(expected["rows"]), "missing": len(expected["missing"]),
            "sources": len(expected["sources"]), "markdown_sha256": canonical}
