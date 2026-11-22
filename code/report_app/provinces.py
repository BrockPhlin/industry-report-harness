"""NEA provincial grid-connection statistics with source-specific periods."""

import csv
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import re

TABLE_DIR = Path(__file__).resolve().parents[1] / "data/nea"
HTML_TABLES = {
    2021: "https://www.nea.gov.cn/2022-03/09/c_1310508114.htm",
    2022: "https://www.nea.gov.cn/2023-02/17/c_1310698128.htm",
    2023: "https://www.nea.gov.cn/2024-02/28/c_1310765696.htm",
}
HTML_QUARTER_TABLES = {
    2025: "https://www.nea.gov.cn/20251112/35126d06a151461882b61d0a2e5706a6/c.html",
}
TABLES = {
    2024: (
        "https://www.nea.gov.cn/20250221/f04452701c914d51a89d0c0ea6f4acd1/c.html",
        "20250221f04452701c914d51a89d0c0ea6f4acd1_202502211d5ac93ba86a4a7db188d1a8601fe72f.jpeg",
        "12ce026ce5ac9e3444cfce47f5d90996b9e3a8cc049fdaa4208ab08b03bbbbe5",
    ),
    2025: (
        "https://www.nea.gov.cn/20260305/4216fa1274bd4b7f8da92090ba3999aa/c.html",
        "202603054216fa1274bd4b7f8da92090ba3999aa_202603053183d20fabdf4909a6f2711097ce52a0.png",
        "29ef7af2339895126a7a673e9845508c5676cb4914768d349257cde59412bbd9",
    ),
    2026: (
        "https://www.nea.gov.cn/20261116/f5a85af49499420598ce8e0adfdbba9f/c.html",
        "20261116f5a85af49499420598ce8e0adfdbba9f_20261116c4db727facbe431185283d161f33f239.png",
        "70824fc8927b011e967a64d90584b96ff8c21f70028af2e477c90672d08cd93e",
    ),
}
ALIASES = dict(
    zip(
        "Beijing Tianjin Hebei Shanxi Shandong Inner-Mongolia Liaoning Jilin Heilongjiang Shanghai Jiangsu Zhejiang Anhui Fujian Jiangxi Henan Hubei Hunan Chongqing Sichuan Shaanxi Gansu Qinghai Ningxia Xinjiang Tibet Guangdong Guangxi Hainan Guizhou Yunnan".split(),
        "北京 天津 河北 山西 山东 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 河南 湖北 湖南 重庆 四川 陕西 甘肃 青海 宁夏 新疆 西藏 广东 广西 海南 贵州 云南".split(),
    )
)
REGIONS = {*ALIASES.values(), "新疆兵团"}
ADDITIONS = ("光伏新增并网容量", "集中式光伏新增并网容量", "分布式光伏新增并网容量")
STOCK = ("光伏年末累计并网容量", "集中式光伏年末累计并网容量", "分布式光伏年末累计并网容量")
HOUSEHOLD_NEW = "户用光伏新增并网容量"
HOUSEHOLD_STOCK = "户用光伏年末累计并网容量"
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def region_name(region):
    cleaned = region.strip()
    for suffix in (" Province", "维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "省", "市"):
        cleaned = cleaned.removesuffix(suffix)
    return ALIASES.get(cleaned.replace(" ", "-"), cleaned)


def provincial_rows(raw, *, year):
    if sha256(raw).hexdigest() != TABLES[year][2]:
        raise ValueError("发布方已更换原表，待核对新版表格")
    rows = []
    filename = "2026-q3.csv" if year == 2026 else f"{year}.csv"
    with (TABLE_DIR / filename).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            region = row.pop("地区")
            rows.extend((region, year, metric, "万千瓦", value) for metric, value in row.items() if value)
    return rows, []


class TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(re.sub(r"\s+", "", "".join(self.cell)))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def html_provincial_rows(raw, *, year, quarter=False):
    """Read the published row values, checking the explicit header and row shape."""
    page = raw.decode("utf-8-sig")
    if not re.search(r"单位\s*[:：]\s*万千瓦", page):
        raise ValueError("分省表的计量单位已更改")
    parser = TableRows()
    parser.feed(page)
    parser.close()
    cells_text = " ".join(cell for row in parser.rows for cell in row)
    addition_period = "年前三季度" if quarter else "年"
    stock_period = "年9月底" if quarter else "年底"
    if (
        f"{year}{addition_period}新增并网容量" not in cells_text
        or f"{year}{stock_period}累计并网容量" not in cells_text
    ):
        raise ValueError("分省表的年份或指标口径已更改")

    columns = [*ADDITIONS]
    if year >= 2022:
        columns.append(HOUSEHOLD_NEW)
    columns.extend(STOCK)
    if year >= 2023:
        columns.append(HOUSEHOLD_STOCK)
    if quarter:
        columns = [
            label.replace("新增并网容量", "前三季度新增并网容量").replace("年末累计", "截至九月底累计")
            for label in columns
        ]

    results, seen = [], set()
    for group in parser.rows:
        if not group:
            continue
        region = "China" if group[0] == "总计" else region_name(group[0])
        if region not in REGIONS and region != "China":
            continue
        values = group[1:]
        if (
            region in seen
            or len(values) != len(columns)
            or any(val and not NUMBER.fullmatch(val) for val in values)
        ):
            raise ValueError(f"分省表的 {region} 行格式已更改")
        seen.add(region)
        results.extend((region, year, metric, "万千瓦", val) for metric, val in zip(columns, values) if val)
    expected = (REGIONS | {"China"}) - ({"新疆兵团"} if quarter else set())
    if seen != expected:
        raise ValueError("分省表的地区行有缺失，待核对原表")
    return results, []


def table_caveat(region, year, *, quarter=False):
    notes = []
    if quarter:
        notes.append("新增只统计前三季度，累计值截至九月底。")
        if year == 2026:
            notes.append("原表注明江西等部分省份有统计数据修正。")
    if region in {"新疆", "新疆兵团"}:
        notes.append(
            "2021 至 2024 年表另列新疆兵团，2025 年和 2026 年前三季度表只列新疆，跨期比较须核对范围。"
        )
    if year <= 2022:
        notes.append("原表注释说明部分省份存在退运减容，期末累计以发布值为准。")
    return "".join(notes)
