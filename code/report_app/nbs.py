"""National Bureau of Statistics monthly above-scale industrial solar production."""

from decimal import Decimal
from functools import partial
import re
from urllib.parse import urljoin, urlsplit

from .provinces import TableRows

INDEX = "https://www.stats.gov.cn/sj/zxfb/"
RELEASE_TITLE = re.compile(r"(20\d{2})年(?:1[—–-])?(1[0-2]|[2-9])月份?规模以上工业增加值")
RELEASE_PATH = re.compile(r"/sj/zxfb/20\d{4}/t20\d{6}_\d+\.html")
# Backfill stable URLs. The current release is also discovered from the index.
RELEASES = {
    (2025, 2): "202503/t20250317_1959012.html",
    (2025, 3): "202504/t20250416_1959320.html",
    (2025, 4): "202505/t20250519_1959862.html",
    (2025, 5): "202506/t20250616_1960172.html",
    (2025, 6): "202507/t20250715_1960413.html",
    (2025, 7): "202508/t20250815_1960790.html",
    (2025, 8): "202509/t20250915_1961180.html",
    (2025, 9): "202510/t20251020_1961611.html",
    (2025, 10): "202511/t20251114_1961856.html",
    (2025, 11): "202512/t20251215_1962074.html",
    (2025, 12): "202601/t20260119_1962329.html",
    (2026, 2): "202603/t20260316_1962782.html",
    (2026, 3): "202604/t20260416_1963329.html",
    (2026, 4): "202605/t20260518_1963731.html",
    (2026, 5): "202606/t20260616_1963953.html",
    (2026, 6): "202607/t20260715_1964123.html",
    (2026, 7): "202608/t20260817_1965055.html",
    (2026, 8): "202609/t20260915_1965308.html",
    (2026, 9): "202610/t20261019_1965617.html",
    (2026, 10): "202611/t20261116_1965842.html",
}
LEVEL = "规模以上工业太阳能发电量"
GROWTH = "规模以上工业太阳能发电量同比"
CELL_LEVEL = "规模以上工业太阳能电池（光伏电池）产量"
CELL_GROWTH = CELL_LEVEL + "同比"
INDICATORS = {
    "太阳能发电量（亿千瓦时）": (LEVEL, GROWTH, "亿千瓦时"),
    "太阳能电池（光伏电池）（万千瓦）": (CELL_LEVEL, CELL_GROWTH, "万千瓦"),
}
SCOPE = (
    "国家统计局规模以上工业月度表，范围为年主营业务收入2000万元及以上工业企业。"
    "1—2月合并发布。累计值读取同月原表，不能用已发布各月水平相加代替。"
    "同比为原表所列可比口径，不能用上年同期已公布的绝对量另算。"
)


def release_id(title):
    match = RELEASE_TITLE.match(re.sub(r"\s+", "", title))
    if match:
        return tuple(map(int, match.groups()))


def jobs(plan, published):
    releases = {key: INDEX + path for key, path in RELEASES.items()}
    for href, title in published:
        period = release_id(title)
        url = urljoin(INDEX, href)
        loc = urlsplit(url)
        if (
            period
            and loc.scheme == "https"
            and loc.netloc == "www.stats.gov.cn"
            and RELEASE_PATH.fullmatch(loc.path)
        ):
            releases[period] = url
    selected = []
    for (year, month), url in sorted(releases.items()):
        if plan["start"] <= year <= plan["end"]:
            period = "1—2月" if month == 2 else f"{month}月"
            title = f"{year} 年{period}规模以上工业生产主要数据"
            selected.append((url, title, "国家统计局", url, partial(rows, year=year, month=month), "nbs-products-v2"))
    return selected


def rows(raw, *, year, month):
    parser = TableRows()
    page = raw.decode("utf-8-sig")
    parser.feed(page)
    parser.close()
    first = "1—2月" if month == 2 else f"{month}月"
    periods = [first] if month == 2 else [first, f"1—{month}月"]
    metadata = re.search(r'<meta\s+name="ArticleTitle"\s+content="([^"]+)"', page)
    if not metadata or release_id(metadata[1]) != (year, month):
        raise ValueError("国家统计局发布标题的统计期无法核对")
    collected = {name: set() for name in INDICATORS}
    active = False
    for index, row in enumerate(parser.rows):
        if row and row[0] == "指标":
            active = row[1:] == periods and parser.rows[index + 1:index + 2] == [
                ["绝对量", "同比增长（%）"] * len(periods)
            ]
        if active and row and row[0] in collected:
            collected[row[0]].add(tuple(row[1:]))
    observations = []
    for label, (level, change, unit) in INDICATORS.items():
        if len(collected[label]) != 1:
            raise ValueError(f"国家统计局原表的{label}行、单位或重复表值无法核对")
        values = collected[label].pop()
        if len(values) != len(periods) * 2 or any(
            not re.fullmatch(r"-?\d+(?:\.\d+)?", value) for value in values
        ) or any(Decimal(value) < 0 for value in values[::2]):
            raise ValueError("国家统计局原表的绝对量或同比格式已更改")
        for period, value, growth in zip(periods, values[::2], values[1::2]):
            observations.extend(
                (("China", year, f"{level}（{period}）", unit, value),
                 ("China", year, f"{change}（{period}）", "%", growth))
            )
    return observations, [("规模以上工业生产主要数据 · 统计范围与同比", SCOPE)]
