"""Bind a stated period change to the cited series whose two end values the writer quotes."""
from dataclasses import dataclass
from decimal import Decimal, DecimalException
import re

from .solar_data import trend


NUMBER = r"[-+−]?\d+(?:\.\d+)?"
YEARS = re.compile(r"((?:19|20)\d{2})\s*年?\s*[至到—–~-]\s*((?:19|20)\d{2})\s*年?")
RATE = re.compile(
    r"(?P<lead>累计|期间)?(?P<verb>增长率|变化率|增速|增幅|降幅|增长|上升|下降|减少|变化)"
    rf"(?P<copula>为|达)?\s*(?P<number>{NUMBER})\s*[%％]"
)
STOCK = re.compile(r"年末累计|累计装机|累计并网|累计容量")
# Only the grammatical link between a printed pair and its immediate rate can be rewritten.
SIMPLE_GAP = re.compile(
    r"(?:[\s，,（(]|累计装机|累计并网|累计容量|年末累计|年度新增|新增|装机|容量|并网|光伏|"
    r"两项指标|两项|两组|二者|两者|上述|数据|序列|指标|均|合计|整体|总体|该指标|该项|同期|期间|其|的|从|在|两年间)*"
)


@dataclass(frozen=True)
class RateIssue:
    start: int
    end: int
    replacement: str
    value_start: int
    refs: tuple
    reason: str


def _number(value):
    return Decimal(str(value).replace("−", "-"))


def _verified_series(cited):
    for row in cited:
        series = row.get("series") or []
        raw = row.get("raw_series") or series
        unit = row.get("unit", "")
        if len(series) < 2 or len(raw) < 2 or not unit or unit in ("%", "％", "个百分点"):
            continue
        # Only use changes produced by the existing evidence builder from unrounded inputs.
        try:
            if int(raw[0][0]) >= int(raw[-1][0]) or _number(raw[0][1]) <= 0:
                continue
            endpoints = (unit, _number(series[0][1]), _number(series[-1][1]))
            formula = trend(raw, unit)
        except (DecimalException, TypeError, ValueError, IndexError):
            continue
        rate = re.search(r"年累计变化([+-]\d+\.\d+)%", formula)
        if not rate or formula not in row.get("text", ""):
            continue
        yield endpoints, (
            row["ref"], row.get("metric", ""), (str(raw[0][0]), str(raw[-1][0])), _number(rate[1])
        )


def growth_issues(sentence, cited):
    """Check immediate end-to-end comparisons; leave shares, annualised or reported rates alone."""
    if not RATE.search(sentence):
        return []
    rows = {}
    for key, info in _verified_series(cited):
        rows.setdefault(key, []).append(info)
    if not rows:
        return []
    units = "|".join(re.escape(u) for u in sorted({k[0] for k in rows}, key=len, reverse=True))
    pair = re.compile(
        rf"(?<![\d.])({NUMBER})\s*({units})?\s*"
        rf"(?:与|和|、|到|至|→|->|增至|升至|降至|减至|变为|增加到|下降到)\s*"
        rf"({NUMBER})\s*({units})(?![A-Za-z/])"
    )
    issues = []
    for sentence_part in re.finditer(r"[^。！？!?；;\n]+", sentence):
        text = sentence_part[0]
        for rate in RATE.finditer(text):
            pairs = list(pair.finditer(text, 0, rate.start()))
            if not pairs or re.match(r"\s*(?:以上|以下|左右|至|到|[-—–~～]|(?:和|与|、)\s*\d)", text[rate.end():]):
                continue
            nearest = pairs[-1]
            gap = text[nearest.end():rate.start()]
            windows = YEARS.findall(gap) or YEARS.findall(text[:nearest.start()])[-1:]
            words = YEARS.sub("", gap)
            if not SIMPLE_GAP.fullmatch(words) or len(windows) > 1:
                continue
            # An explicitly renamed series must be matched against its own pair.
            stock, added = bool(STOCK.search(words)), "新增" in words
            combined = bool(re.search(r"两项|两组|二者|两者|总体|整体|合计", words))
            candidates = []
            relevant_pairs = pairs if combined or stock or added else [nearest]
            identified = set()
            for hit in relevant_pairs:
                if hit[2] and hit[2] != hit[4]:
                    continue
                for ref, metric, years, change in rows.get((hit[4], _number(hit[1]), _number(hit[3])), []):
                    if windows and tuple(windows[0]) != years:
                        continue
                    if stock != added and (stock and not STOCK.search(metric) or added and "新增" not in metric):
                        continue
                    candidates.append((ref, change))
                    identified.add(hit.start())
            if not candidates:
                continue
            expected = {value for _, value in candidates}
            refs = tuple(dict.fromkeys(ref for ref, _ in candidates))
            pos = sentence_part.start()
            actual = _number(rate["number"])
            if rate["verb"] in ("降幅", "下降", "减少"):
                actual = -abs(actual)
            unresolved_group = combined and (len(identified) < 2 or len(identified) != len(relevant_pairs)
                                             or re.search(r"总体|整体|合计", words))
            if len(expected) != 1 or unresolved_group:
                # Keep the checked observations, omit a rate with no unique denominator.
                issues.append(RateIssue(pos + nearest.end(), pos + rate.end(), "",
                                        pos + rate.start("number"), refs, "同句列出不同序列，合并变化率缺少共同分母。"))
                continue
            value, = expected
            if value == actual:
                continue
            verb = "增长" if value >= 0 else "下降"
            replacement = f"{rate['lead'] or ''}{verb}{abs(value):f}%"
            issues.append(RateIssue(pos + rate.start(), pos + rate.end(), replacement,
                                    pos + rate.start("number"), refs, "所述变化率与该序列两端原值的计算结果不一致。"))
    return issues


def repair_growth(text, cited):
    issues = growth_issues(text, cited)
    for item in reversed(issues):
        text = text[:item.start] + item.replacement + text[item.end:]
    return text
