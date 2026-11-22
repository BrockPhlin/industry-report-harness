"""Checked columns of NEA's image-only annual provincial PV grid-connection tables."""

import csv
from hashlib import sha256
from pathlib import Path

TABLE_DIR = Path(__file__).resolve().parents[1] / "data/nea"
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
}
ALIASES = dict(
    zip(
        "Beijing Tianjin Hebei Shanxi Shandong Inner-Mongolia Liaoning Jilin Heilongjiang Shanghai Jiangsu Zhejiang Anhui Fujian Jiangxi Henan Hubei Hunan Chongqing Sichuan Shaanxi Gansu Qinghai Ningxia Xinjiang Tibet Guangdong Guangxi Hainan Guizhou Yunnan".split(),
        "北京 天津 河北 山西 山东 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 河南 湖北 湖南 重庆 四川 陕西 甘肃 青海 宁夏 新疆 西藏 广东 广西 海南 贵州 云南".split(),
    )
)
REGIONS = {*ALIASES.values(), "新疆兵团"}


def region_name(region):
    cleaned = region.strip()
    for suffix in (" Province", "维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "省", "市"):
        cleaned = cleaned.removesuffix(suffix)
    return ALIASES.get(cleaned.replace(" ", "-"), cleaned)


def provincial_rows(raw, *, year):
    if sha256(raw).hexdigest() != TABLES[year][2]:
        raise ValueError("发布方已更换原表，待核对新版表格")
    rows = []
    with (TABLE_DIR / f"{year}.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            region = row.pop("地区")
            rows.extend((region, year, metric, "万千瓦", value) for metric, value in row.items() if value)
    return rows, []
