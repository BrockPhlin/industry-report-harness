"""Match individual quantitative statements to the observations in their own citations."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from .provinces import REGIONS
from .series_growth import growth_issues
from .trade import COUNTRIES


CITE = re.compile(r"\[\s*E\d+(?:\s*[,，、]\s*E\d+)*\s*\]")
YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?=\s*年|\s*[—–至和与到、,-]\s*(?:19|20)\d{2})")
MONTH = re.compile(r"(?<!\d)(1[0-2]|[1-9])\s*(?:[-—–至到]\s*(1[0-2]|[1-9])\s*)?月")
NUMBER = r"(?<![\d.])([+−-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*"
UNITS = {
    "GWdc", "GWac", "GW", "MW", "TW", "kW", "TWh", "GWh", "MWh", "kWh", "kWh/人",
    "亿欧元", "亿美元", "亿元", "万元", "美元/kWh", "美元/MWh", "美元/W", "元/千瓦时",
    "万亿千瓦时", "亿千瓦时", "万千瓦时", "千瓦时", "亿千瓦", "万千瓦", "千瓦", "万吨", "吨",
    "个百分点", "%", "欧元", "美元",
}
LABELS = {key: value[1] for key, value in COUNTRIES.items()}
LABELS.update(World="全球", **{"European Union": "欧盟"})
REGION_ALIASES = {**{v: k for k, v in LABELS.items()}, **{k: k for k in REGIONS}, "全国": "China"}
REGION_RE = re.compile("|".join(map(re.escape, sorted(REGION_ALIASES, key=len, reverse=True))))
END_SECTIONS = {"数据附表", "数据口径与覆盖范围", "资料来源", "参考文献"}
# These alternatives distinguish *incompatible* indicators, not every synonym.
FAMILIES = (
    (("新增",), ("年末累计", "累计装机", "累计并网")),
    (("集中式",), ("分布式",)),
    (("发电量",), ("产量",)),
    (("直流侧",), ("交流侧",)),
    (("平准化发电成本", "平准化度电成本", "LCOE"), ("上网电价", "成交价", "零售电价", "售电价", "组件售价")),
)
INTERPRETATION = re.compile(r"导致|归因于|证明|从而|(?<!无)造成|主要原因|说明.*(?:需求|利润|压力)|可能|最高|最低|排名|居首|连续.{0,4}年|全球领先")
DERIVED = re.compile(r"估算|折合|换算|约为|约合|折算|四舍五入|相差|差额|相减|推算")


def normalized(text):
    return unicodedata.normalize("NFKC", str(text)).replace("−", "-")


def decimal_value(value):
    try:
        result = Decimal(normalized(value).replace(",", ""))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def periods(text):
    found = set()
    for month, chinese in ((6, "六"), (9, "九"), (12, "十二")):
        text, count = re.subn(rf"(?:{month}|{chinese})月底", "", text)
        if count:
            found.add(f"{month}月底")
    for first, end in MONTH.findall(text):
        found.add(f"{int(first)}—{int(end)}月" if end else f"{int(first)}月")
    for name, pattern in (("1—6月", r"上半年|H1"), ("1—9月", r"前三季度|Q3"), ("1—12月", "全年|年末累计")):
        if re.search(pattern, text, re.I):
            found.add(name)
    return found


def references(text):
    return list(dict.fromkeys(ref for group in CITE.findall(text) for ref in re.findall(r"E\d+", group)))


def sentences(markdown):
    """The native writer places paragraph citations after its closing sentence."""
    section = ""
    fenced = False
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced or not line:
            continue
        if line.startswith("#"):
            section = line.lstrip("# ").strip()
            if section in END_SECTIONS:
                break
            continue
        if line.startswith(("|", "运行方式", "状态：", "状态:")):
            continue
        parts = list(CITE.finditer(line))
        shared = []
        if parts:
            # A trailing run applies to this paragraph. Citations embedded in
            # the body stay on their own sentence instead.
            tail = line[parts[0].start():]
            if not CITE.sub("", tail).strip(" 。！？.!?"):
                shared = references(tail)
                line = line[:parts[0].start()]
        if not shared:
            line = re.sub(r"([。！？!?])\s*((?:" + CITE.pattern + r"\s*)+)", r"\2\1", line)
        for sentence in re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+(?=[A-Z])", line):
            text = CITE.sub("", sentence).strip()
            if text:
                yield section, text, shared or references(sentence)


@dataclass(frozen=True)
class Observation:
    ref: str
    year: str
    region: str
    metric: str
    publisher: str


def prepare(row, pattern):
    values = {}
    for series in ("series", "raw_series"):
        for item in row.get(series) or ():
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            year, value = item
            number = decimal_value(value)
            if number is None:
                continue
            key = (number, normalized(row.get("unit", "")))
            obs = Observation(row["ref"], str(year), row.get("region", ""), row.get("metric", ""), row.get("publisher", ""))
            values.setdefault(key, set()).add(obs)
    text = normalized(row.get("text", ""))
    literals = {quantity_key(match, text[:match.start()]) for match in pattern.finditer(text)}
    return values, literals


def incompatible_metric(context, metric):
    for left, right in FAMILIES:
        names_left = any(s in context for s in left)
        names_right = any(s in context for s in right)
        if names_left != names_right and any(s in metric for s in (right if names_left else left)):
            return True
    return False


def scope_check(context, prefix, observations):
    # A prior value starts a new comparison. Single-year or single-region
    # sentences can supply unambiguous context to the next clause as well.
    years = set(YEAR.findall(context)) or set(YEAR.findall(prefix))
    windows = periods(context) or periods(prefix)
    def places(text):
        # "从中国进口" describes the trade partner instead of the reporting region.
        text = re.sub(r"(?:自|从|向|对)(中国|美国|德国|荷兰)(?=进口|出口)", "", text)
        return {REGION_ALIASES[name] for name in REGION_RE.findall(text)}

    regions = places(context) or places(prefix)
    source_refs = sorted({obs.ref for obs in observations})
    trend = re.search(r"(?:上半年|下半年|全年|前三季度)(?:内|期间)?(?:从|由)", prefix)
    if trend and not MONTH.search(prefix[trend.end():]):
        return "review", "期间内的起点与终点需分别核对实际月份。", source_refs
    if "累计" in prefix and any(re.fullmatch(r"\d{1,2}月", win) for win in windows):
        cumulative_windows = {"1—" + win for win in windows}
        if any(periods(obs.metric) & cumulative_windows for obs in observations):
            return "review", "句中月份可能指单月或累计至该月，需确认统计口径。", source_refs
    if any(len(values) > 1 for values in (years, windows, regions)) or "分别" in context:
        return "review", "同一句涉及多个年份、时期或地区，需逐项核对。", source_refs
    valid = []
    for obs in observations:
        metric_periods = periods(obs.metric)
        if years and obs.year not in years:
            continue
        if regions and obs.region and obs.region not in regions and REGION_ALIASES.get(obs.region) not in regions:
            continue
        if windows and metric_periods and not windows.intersection(metric_periods):
            continue
        if incompatible_metric(context, obs.metric):
            continue
        if re.search(r"规上工业|规模以上工业", context) and "全国光伏发电量" in obs.metric:
            continue
        if "发布下限" in obs.metric and re.search(r"(?:等于|恰为|正好|为)\s*$", context):
            continue
        agencies = {name for name in ("国家能源局", "国家统计局") if name in context}
        if len(agencies) == 1 and obs.publisher and obs.publisher not in agencies:
            continue
        valid.append(obs)
    if not valid:
        return "mismatch", "同值同单位只出现在其他年份、地区、统计期或指标中。", source_refs
    refs = sorted({o.ref for o in valid})
    if any(windows and not periods(o.metric) for o in valid):
        return "review", "量值命中，所引指标没有标出句中的统计期。", refs
    if len({(o.region, o.year, o.metric) for o in valid}) > 1:
        return "review", "同值命中多个统计对象，需确认本句所指的记录。", refs
    return "matched", "在所引统计行中找到同值同单位。", refs


def quantity_key(match, context):
    value, unit = decimal_value(match[1]), match[2]
    if value is not None and value > 0 and unit == "%" and re.search(r"(?:同比下降|同比降低|同比减少|降幅(?:为|达)?)\s*$", context):
        value = -value
    return value, unit


def check_measurement(match, context, sentence, snapshots):
    key = quantity_key(match, context)
    observations = set()
    literal_refs = []
    for ref, (values, literals) in snapshots.items():
        observations.update(values.get(key, ()))
        if key in literals:
            literal_refs.append(ref)
    if observations:
        status, reason, refs = scope_check(context, sentence[:match.start()], observations)
        if status == "mismatch" and set(literal_refs) - {obs.ref for obs in observations}:
            status, reason, refs = "review", "统计行的限定与本句不符，其他文字引用也载有该值，需核对。", literal_refs
    else:
        status, refs = "review", literal_refs
        if literal_refs:
            reason = "数值在证据文字中出现，需核对它所描述的对象与条件。"
        elif not snapshots:
            reason = "缺少可用于比对的引用。"
        elif DERIVED.search(sentence):
            reason = "涉及估算、舍入或换算，需核对计算过程。"
        else:
            status = "mismatch"
            reason = "所引快照中找不到这组数值和单位。"
    return dict(value=match[1], unit=match[2], status=status, refs=refs, reason=reason)


def audit_claims(markdown, evidence):
    """Return an offline, citation-scoped measurement audit of the narrative body."""
    rows = [r for r in (evidence or []) if isinstance(r, dict) and isinstance(r.get("ref"), str)]
    units = UNITS | {normalized(r["unit"]) for r in rows if r.get("unit")}
    pattern = re.compile(NUMBER + "(" + "|".join(map(re.escape, sorted(units, key=len, reverse=True))) + r")(?![A-Za-z/])")
    catalog = {r["ref"]: prepare(r, pattern) for r in rows}
    by_ref = {r["ref"]: r for r in rows}
    counts = dict(total=0, matched=0, mismatch=0, review=0)
    claims = []
    for section, text, refs in sentences(markdown or ""):
        known = {r: catalog[r] for r in refs if r in catalog}
        missing = [r for r in refs if r not in catalog]
        clean = normalized(text)
        growth = {item.value_start: item for item in growth_issues(clean, [by_ref[r] for r in known])}
        checks = []
        start = 0
        for match in pattern.finditer(clean):
            context = clean[start:match.start()].rsplit(";", 1)[-1]
            check = check_measurement(match, context, clean, known)
            if issue := growth.get(match.start(1)):
                check.update(status="mismatch", refs=list(issue.refs), reason=issue.reason)
            checks.append(check)
            start = match.end()
        reasons = []
        if missing:
            reasons.append("引用清单中缺少 " + "、".join(missing) + "。")
        if not refs:
            reasons.append("本句没有证据编号。")
        if not checks:
            reasons.append("本句没有识别到带单位的量值，需阅读原文。")
        if INTERPRETATION.search(clean):
            reasons.append("本句含解释或推断，需判断引用能否支持。")
        outcomes = {check["status"] for check in checks}
        if "mismatch" in outcomes and known and not missing:
            status = "mismatch"
        elif reasons or "review" in outcomes:
            status = "review"
        else:
            status = "matched"
        reasons.extend(dict.fromkeys(c["reason"] for c in checks if c["status"] != "matched"))
        counts[status] += 1
        counts["total"] += 1
        claims.append(dict(id=f"C{len(claims)+1}", section=section, text=text, refs=refs,
                           status=status, reasons=reasons, checks=checks))
    return {"version": 1, "summary": counts, "claims": claims}
