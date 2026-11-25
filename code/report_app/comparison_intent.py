"""Recognize explicit requests matching one archived provincial grid comparison."""

import re
from unicodedata import normalize

from .province_comparison import comparison_catalog
from .provinces import REGIONS


REGION = re.compile("|".join(sorted(REGIONS, key=len, reverse=True)))
ALL_PROVINCES = re.compile(r"(?:全国|中国)(?:的)?(?:各省|所有省|全部省|31个省)|(?:所有|全部)省(?:份|级地区|区市)")
ACTION = re.compile(r"比较|对比|对照|排名|排行|排序|名次|排第|同比|差额|差距|相差|变化|变动|谁(?:更)?[高低多少]")
NEGATION = re.compile(r"(?:不(?:要|用|做|需要|需|必)?|无需|别|避免)(?:做|列|进行)?(?:地区|分省|省际)?(?:比较|对比|排名|排序)")
OTHER_TOPIC = re.compile(
    r"企业|公司|厂商|制造|产能|产量|出货|发电量|发电小时|利用率|消纳率|占比|渗透率|"
    r"成本|电价|营收|价格|进出口|外贸|组件|电池|风电|风光|光热|储能|预测|预计|预估|展望|情景|推演|"
    r"国内外|全球|海外|美国|欧洲|港澳|台湾|香港|澳门|工商业|海上|地面电站|园区|县域|城市排名|"
    r"非(?:户用|集中式|分布式)|项目数|电站数|政策(?:变化|比较|排名)"
)
# A number of words in reports (e.g. “2000字”) can otherwise look like years.
YEAR = re.compile(r"(?<!\d)(?:19|20|21)\d{2}(?!\d|字|元|万|千|兆|[gm]w)")
WINDOWS = {
    "annual": (r"全年|年度|1(?:月)?[-—–~至到]12月", r"(?:年末|年底|12月[底末])"),
    "half_year": (r"上半年|前半年|前(?:6|六)个月|h1|(?:1|一)(?:月)?[-—–~至到](?:6|六)月", r"(?:6|六)月[底末]"),
    "three_quarters": (r"前(?:3|三)(?:个)?季度|前(?:9|九)个月|(?:1|一)(?:月)?[-—–~至到](?:9|九)月", r"(?:9|九)月[底末]"),
}
OTHER_PERIOD = re.compile(r"下半年|半年度|季度|第[一二三四1234]季|[qh][1-4]|[0-9一二三四五六七八九十]+月|月度|单月|近[几两三]年|环比")
KINDS = {"central": "集中式", "distributed": "分布式", "household": "户用"}


def _plain(text):
    text = normalize("NFKC", text).lower()
    # Keep years written as “2025 2026” distinct when removing spaces.
    text = re.sub(r"(?<=\d)\s+(?=\d)", "、", text)
    return re.sub(r"\s+", "", text).replace("新疆生产建设兵团", "新疆兵团")


def _window(text, stock):
    matches = set()
    rest = text
    for period, (span, endpoint) in WINDOWS.items():
        if re.search(span, text) or (stock and re.search(endpoint, text)):
            matches.add(period)
        rest = re.sub(span, "", rest)
        rest = re.sub(endpoint, "", rest) if stock else rest
    if len(matches) == 1 and not OTHER_PERIOD.search(rest):
        return matches.pop()
    return None


def _metric(text):
    if "光伏" not in text or "并网" not in text:
        return None
    if not re.search(r"容量|装机", text):
        return None
    new, stock = bool(re.search(r"新增|新并网", text)), bool(re.search(r"累计|存量", text))
    if new == stock:
        return None
    # Household installations can also be described as household distributed PV.
    text = re.sub(r"户用(?:型)?分布式|分布式户用", "户用", text)
    kinds = [key for key, token in KINDS.items() if token in text]
    if len(kinds) > 1 or (kinds and re.search(r"全口径|所有类型|各类型|总体|整体|总量.{0,5}(?:和|与|及)|(?:和|与|及)(?:总量|合计)", text)):
        return None
    return (kinds[0] if kinds else "total") + ("_new" if new else "_stock")


def _regions(text, available):
    named = list(dict.fromkeys(REGION.findall(text)))
    if any(name not in available for name in named):
        return None
    if re.search(r"除.+(?:以外|之外|外)|不含|不包括|排除", text):
        return None
    if ALL_PROVINCES.search(text):
        if re.search(r"仅限|只看|只比较|重点(?:看|比较)|全国(?:平均|总量|合计|总计)", text):
            return None
        return [name for name in available if name != "新疆兵团" or name in named]
    if re.search(r"全国|中国合计|中国总量|其他省|等省|等地|为例|例如|不限于|省内|市级|地级市", text):
        return None
    if len(named) >= 2:
        return named
    return None


def _selection(text):
    if not ACTION.search(text) or NEGATION.search(text) or OTHER_TOPIC.search(text):
        return None
    # Published ranks available from the tool sort by the later period's level.
    ranking = r"(?:排名|排行|排序)"
    change = r"(?:增速|增长率|变动率|变化率|差额|增幅|变动幅度|增量差)"
    if re.search(change + r"(?:的)?(?:全国|省际|分省)?(?:进行)?" + ranking +
                 r"|(?:按|根据)" + change + r"[^。，；]{0,8}" + ranking +
                 "|" + ranking + r"(?:按|依据)" + change +
                 r"|按(?:基期|前期)|升序|从低到高|分别排名|各年排名", text):
        return None
    metric = _metric(text)
    if not metric:
        return None
    years = {int(y) for y in YEAR.findall(text)}
    window = _window(text, metric.endswith("_stock"))
    for p in comparison_catalog()["periods"]:
        if p["id"] != window or years != {p["before_year"], p["after_year"]}:
            continue
        regions = _regions(text, p["regions"])
        if regions:
            return dict(period=window, metric=metric, regions=regions)
    return None


def infer_comparison(question, scope="", outline=()):
    """Only user-authored question/scope may specify the job; headings can veto a conflicting job."""
    if not isinstance(question, str) or not question.strip() or not isinstance(scope, str):
        return None
    if not isinstance(outline, (list, tuple)) or not all(isinstance(t, str) for t in outline):
        return None
    if len(question) > 7000 or len(scope) > 7000 or len(outline) > 12 or any(len(t) > 250 for t in outline):
        return None
    question, scope = _plain(question), _plain(scope)
    original = question + "。" + scope
    requested = _selection(original)
    if requested and scope and re.search(r"改为|改成|仅限|只(?:看|比较|选)|缩小到", scope):
        # Joining two contradictory user messages must not turn a narrowed list into a union.
        named = set(REGION.findall(scope))
        if named and named != set(requested["regions"]):
            return None
    if requested and outline:
        # A generated outline cannot supply a missing date, metric, region or comparison request.
        with_headings = _selection(original + "。" + _plain("。".join(outline)))
        if with_headings != requested:
            return None
    return requested
