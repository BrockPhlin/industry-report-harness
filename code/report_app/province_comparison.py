"""Compare the same NEA provincial capacity measure across two archived releases."""

import csv
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from io import StringIO
from urllib.parse import urljoin

from .errors import AppError
from .provinces import (
    ADDITIONS, HALF_YEAR_TABLES, HTML_QUARTER_TABLES, HOUSEHOLD_NEW, HOUSEHOLD_STOCK,
    NUMBER, REGIONS, STOCK, TABLE_DIR, TABLES, table_caveat,
)


PERIODS = {
    "half_year": (2025, 2026, "上半年"),
    "three_quarters": (2025, 2026, "前三季度"),
    "annual": (2024, 2025, "全年"),
}
METRICS = dict(zip(
    ("total_new", "central_new", "distributed_new", "household_new",
     "total_stock", "central_stock", "distributed_stock", "household_stock"),
    (*ADDITIONS, HOUSEHOLD_NEW, *STOCK, HOUSEHOLD_STOCK),
))
UNIT = "万千瓦"
# CSV extracts and the official source files have distinct hashes.
CSV_DIGESTS = {
    "2024.csv": "b4e0aa735ff3881f171b8e2df7f1a0cf4c822375ed4733387616141397380577",
    "2025.csv": "7b5dfd8cae86ff88260cde78c4bc51d3fc9dff2c6016f0750dce76f278e78acd",
    "2025-h1.csv": "0734386715cb6e48c82e5802c9cca5d2986986c1331b9ecdca59ef7d9fc76f88",
    "2026-h1.csv": "dc79d380c4cc650a26432690c3842af81d659bb5bf9ab7f5a824db58117ef161",
    "2025-q3.csv": "ee18daaf7136b5fffff7c958c7dce660901f8d6274a7cfc9c5e707b583b60c70",
    "2026-q3.csv": "a27ddb64fb0b80ac5e78a421f96c4100dbabdd923da8c9c67a2d6bbf1549dfe9",
}
HTML_2025_Q3_SHA256 = "0a4a15217927b8cccd8d437ed470562f7b551cd5094e0886e9e16c73968d8daa"


def _metrics(period):
    if period == "annual":
        return METRICS
    addition, closing = ("上半年新增", "截至六月底累计") if period == "half_year" else ("前三季度新增", "截至九月底累计")
    return {
        key: label.replace("新增", addition).replace("年末累计", closing)
        for key, label in METRICS.items()
    }


def _regions(period):
    return sorted(REGIONS if period == "annual" else REGIONS - {"新疆兵团"})


def comparison_catalog():
    periods = []
    for period, (first, last, window) in PERIODS.items():
        periods.append(dict(
            id=period, label=f"{first}、{last} 年{window}", before_year=first, after_year=last,
            metrics=[dict(id=k, label=v, unit=UNIT) for k, v in _metrics(period).items()],
            regions=_regions(period),
        ))
    return dict(periods=periods, default=dict(
        period="half_year", metric="central_new", regions=["江西", "湖北", "浙江"],
    ))


def _read_release(period, year, metric):
    suffix = {"annual": "", "half_year": "-h1", "three_quarters": "-q3"}[period]
    filename = f"{year}{suffix}.csv"
    try:
        raw = (TABLE_DIR / filename).read_bytes()
    except OSError as exc:
        raise AppError("找不到已归档的分省并网统计表。", 503, "comparison_data_unavailable") from exc
    digest = sha256(raw).hexdigest()
    if digest != CSV_DIGESTS[filename]:
        raise AppError(f"{filename} 的指纹与已核对的归档不同，请核对原表。", 503, "comparison_data_changed")
    rows = csv.DictReader(StringIO(raw.decode("utf-8"), newline=""))
    values = {}
    for row in rows:
        value = row[metric]
        if value and not NUMBER.fullmatch(value):
            raise AppError("归档表出现无法识别的量值，请核对原表。", 503, "comparison_data_changed")
        values[row["地区"]] = value or None
    if period == "three_quarters" and year == 2025:
        url = data_url = HTML_QUARTER_TABLES[year]
        source_type, source_hash = "html", HTML_2025_Q3_SHA256
    else:
        url, asset, source_hash = (HALF_YEAR_TABLES if period == "half_year" else TABLES)[year]
        source_type, data_url = "image", urljoin(url, asset)
    window = "" if period == "annual" else PERIODS[period][2]
    source = dict(
        year=year, title=f"{year}年{window}光伏发电建设情况", url=url, data_url=data_url,
        csv_file="code/data/nea/" + filename, csv_sha256=digest,
        source_type=source_type, source_sha256=source_hash,
        image_sha256=source_hash if source_type == "image" else None,
    )
    return values, source


def _compare_values(region, before, after):
    base, current = Decimal(before), Decimal(after)
    delta = current - base
    growth, note = None, ""
    if base > 0:
        rounded = (100 * delta / base).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        growth = format(rounded, "f")
    elif base == 0:
        note = "基期值为零，无法计算相对变化率。"
    else:
        note = "基期值为负，仅列两期差额。"
    return dict(region=region, before=before, after=after, delta=format(delta, "f"),
                growth_pct=growth, growth_note=note)


def _set_ranks(ordered_rows, value_key, rank_key):
    previous = None
    rank = 0
    for position, row in enumerate(ordered_rows, 1):
        current = Decimal(row[value_key])
        if current != previous:
            rank = position
        row[rank_key] = rank
        previous = current


def build_comparison(selection):
    """Return JSON-safe published cells and derived quantities without a network or model call."""
    if not isinstance(selection, dict) or selection.keys() != {"period", "metric", "regions"}:
        raise AppError("请指定比较期间、指标和地区。")
    period, metric, regions = selection["period"], selection["metric"], selection["regions"]
    if not isinstance(period, str) or period not in PERIODS:
        raise AppError("请选择可比较的同一统计期间。")
    metrics = _metrics(period)
    if not isinstance(metric, str) or metric not in metrics:
        raise AppError("请选择该期间支持的一项容量指标。")
    available = _regions(period)
    if not isinstance(regions, list) or not 2 <= len(regions) <= len(available):
        raise AppError(f"请选择 2 至 {len(available)} 个地区。")
    if any(not isinstance(r, str) or r not in available for r in regions):
        raise AppError("所选地区超出该期间的分省表范围。")
    if len(set(regions)) != len(regions):
        raise AppError("请勿重复选择地区。")

    first, last, window = PERIODS[period]
    column = metrics[metric]
    earlier, earlier_source = _read_release(period, first, column)
    later, later_source = _read_release(period, last, column)
    rows, missing = [], []
    for region in regions:
        before, after = earlier.get(region), later.get(region)
        scope_change = period == "annual" and region in {"新疆", "新疆兵团"}
        reasons = [
            f"{year} 年原表未列该地区或该项数值。"
            for year, value in ((first, before), (last, after)) if value is None
        ]
        if scope_change:
            reasons.append("2024 年新疆与新疆兵团分列，2025 年只列新疆，地区范围需核实。")
        if reasons:
            missing.append(dict(region=region, before=before, after=after, reason="".join(reasons)))
        else:
            rows.append(_compare_values(region, before, after))
    _set_ranks(sorted(rows, key=lambda row: Decimal(row["before"]), reverse=True), "before", "before_rank")
    rows.sort(key=lambda row: Decimal(row["after"]), reverse=True)
    _set_ranks(rows, "after", "rank")
    notes = [
        "两期均按同一批所选且可比的地区排名，数值高者在前。并列地区同名次，下一名按实际顺位。结果按后期值降序列出。",
        "本报告根据两期原表计算差额和相对变化率。差额等于后期值减基期值。相对变化率等于差额除以正基期值，以百分数表示，四舍五入至两位小数。",
    ]
    # Generic period notes once, plus any extra notes specific to selected regions.
    for region in dict.fromkeys(["", *regions]):
        caveat = table_caveat(region, last, half_year=period == "half_year", quarter=period == "three_quarters")
        for sentence in caveat.split("。"):
            if sentence and sentence + "。" not in notes:
                notes.append(sentence + "。")
    if period == "three_quarters" and metric.startswith("household_"):
        notes.append("2025 年前三季度原表注明，户用光伏包括自然人户用和非自然人户用。")
    plan = dict(period=period, period_label=f"{first}、{last} 年{window}", before_year=first,
                after_year=last, metric=metric, metric_label=column, unit=UNIT, regions=list(regions))
    return dict(plan=plan, sources=[earlier_source, later_source], rows=rows, missing=missing, notes=notes)
