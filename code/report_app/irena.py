"""IRENASTAT annual photovoltaic capacity, with separate connection types."""

import csv
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from urllib.parse import quote

DIRECTORY = "https://pxweb.irena.org/api/v1/en/IRENASTAT/Power%20Capacity%20and%20Generation"
LANDING = "https://www.irena.org/Data/Downloads/IRENASTAT"
REGIONAL_REPORT = "https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2026/Mar/IRENA_DAT_RE_Capacity_Statistics_2026.pdf"
REGIONAL_DIGEST = "fc580bd4f4ee39ef20de6b1ce3926005a4e3e3b8e2c92fd6a16d175a52515921"
REGIONS = {
    "World",
    "Africa",
    "Asia",
    "Europe",
    "Eurasia",
    "Middle East",
    "Oceania",
    "North America",
    "South America",
    "Central America and Caribbean",
}
CAPACITY_CODE = "Electrical Installed Capacity (MW)"
PV_CODE = "Solar photovoltaic"
DIMENSIONS = ("Country/area", "Technology", "Data Type", "Grid connection", "Year")
METRICS = {
    "All": "光伏年末累计装机（IRENA，全部接网类型）",
    "On-grid": "并网光伏年末累计装机（IRENA）",
    "Off-grid": "离网光伏年末累计装机（IRENA）",
}
COUNTRY_LABELS = {
    "USA": "United States",
    "UK": "United Kingdom",
    "Viet Nam": "Vietnam",
    "Korea Rep": "South Korea",
    "United Arab Em": "United Arab Emirates",
    "Türkiye": "Turkey",
    "Dem Rep Congo": "Democratic Republic of Congo",
    "Lao PDR": "Laos",
    "Cote d'Ivoire": "Côte d'Ivoire",
}


def latest_country_table(raw):
    tables = [
        row
        for row in json.loads(raw)
        if row.get("type") == "t"
        and row.get("id", "").startswith("Country_ELECSTAT_")
        and row["id"].endswith(".px")
    ]
    if not tables:
        raise ValueError("IRENASTAT 未找到最新国家装机数据表")
    return DIRECTORY + "/" + quote(max(tables, key=lambda item: item.get("updated", ""))["id"], safe="")


def capacity_query(raw):
    doc = json.loads(raw)
    variables = {row["code"]: dict(zip(row["valueTexts"], row["values"])) for row in doc["variables"]}
    if set(variables) != set(DIMENSIONS):
        raise ValueError("IRENASTAT 国家统计维度已改变")
    filters = []
    for dimension in DIMENSIONS:
        options = variables[dimension]
        expected = {"Technology": PV_CODE, "Data Type": CAPACITY_CODE}.get(dimension)
        if expected and expected not in options:
            raise ValueError("IRENASTAT 光伏技术分类或装机计量单位已改变")
        picked = [options[expected]] if expected else list(options.values())
        filters.append({"code": dimension, "selection": {"filter": "item", "values": picked}})
    return json.dumps({"query": filters, "response": {"format": "json-stat2"}}).encode()


def capacity_rows(raw):
    data = json.loads(raw, parse_float=Decimal)
    if data.get("id") != list(DIMENSIONS) or "IRENA" not in data.get("source", ""):
        raise ValueError("IRENASTAT 国家统计响应的维度或来源无效")
    order = []
    for name in DIMENSIONS:
        category = data["dimension"][name]["category"]
        keys = sorted(category["index"], key=category["index"].get)
        order.append([category["label"][key] for key in keys])
    if order[1] != [PV_CODE] or order[2] != [CAPACITY_CODE] or set(order[3]) != set(METRICS):
        raise ValueError("IRENASTAT 返回了不同的技术或单位")
    values = data["value"]
    if not isinstance(values, list) or len(values) != len(order[0]) * len(order[3]) * len(order[4]):
        raise ValueError("IRENASTAT 返回的装机观测数量与维度不一致")
    rows = []
    for (region, _, _, connection, year), value in zip(product(*order), values):
        if value is None:
            continue
        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError):
            raise ValueError("IRENASTAT 装机数值格式错误") from None
        if not amount.is_finite() or amount < 0:
            raise ValueError("IRENASTAT 装机数值超出容量范围")
        rows.append(
            (COUNTRY_LABELS.get(region, region), int(year), METRICS[connection], "GW", str(amount / 1000))
        )
    return rows, [
        (
            "指标口径",
            "IRENASTAT 光伏累计装机只统计光伏技术，原单位为 MW。所有接网类型、并网和离网分别使用数据库直接发布值。空白代表未报告。",
        )
    ]


def regional_capacity_rows(raw):
    if sha256(raw).hexdigest() != REGIONAL_DIGEST:
        raise ValueError("IRENA 年度统计版本已改变，待核对全球与各区数据")
    file = Path(__file__).resolve().parents[1] / "data/irena/region-pv-2026.csv"
    aliases = {
        "N America": "North America",
        "S America": "South America",
        "C America + Carib": "Central America and Caribbean",
    }
    observations, notes = [], []
    metric = "光伏年末累计装机（IRENA 2026年3月年度版）"
    with file.open(encoding="utf-8", newline="") as stream:
        for columns in csv.DictReader(stream):
            name, page = columns.pop("region"), columns.pop("page")
            name = aliases.get(name, name)
            observations.extend(
                (name, int(year), metric, "GW", str(Decimal(value) / 1000))
                for year, value in columns.items()
            )
            notes.append(
                (
                    f"PDF 第{page}页 · {name}",
                    f"{name} 为 IRENA 年度报告直接发布的汇总，统计期为 2016—2025 年，原表单位为 MW。",
                )
            )
    return observations, notes
