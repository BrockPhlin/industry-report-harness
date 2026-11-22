"""Official European monthly imports from China, in current euros."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from itertools import product
import json
import re
from urllib.parse import urlencode

LANDING = "https://ec.europa.eu/eurostat/databrowser/view/ds-045409/default/table?lang=en"
API = "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409"
REPORTERS = {
    "European Union": "EU27_2020",
    "Netherlands": "NL",
    "Germany": "DE",
    "France": "FR",
    "Spain": "ES",
    "Italy": "IT",
    "Poland": "PL",
    "Belgium": "BE",
    "Portugal": "PT",
}
DIMENSIONS = ("freq", "reporter", "partner", "product", "flow", "indicators", "time")
PRODUCTS = {"85414300": "光伏组件", "85414200": "未组装光伏电池片"}
ALIASES = {
    "欧盟": "European Union",
    "EU": "European Union",
    "EU27": "European Union",
    "European Union (27)": "European Union",
}


def jobs(plan):
    last = date.today().replace(day=1) - timedelta(days=1)
    first_year = max(2022, plan["start"])
    if min(last.year, plan["end"]) < first_year:
        return []
    through = min(last, date(plan["end"], 12, 31))
    reporters = [name for name in plan["regions"] if name in REPORTERS]
    if not reporters:
        return []
    subjects = ["85414300"]
    if plan.get("trade_products") and "854142" in plan["trade_products"]:
        subjects = [key + "00" for key in plan["trade_products"] if key + "00" in PRODUCTS]
    jobs = []
    for code in subjects:
        params = [
            ("lang", "EN"),
            ("freq", "M"),
            ("partner", "CN"),
            ("product", code),
            ("flow", "1"),
            ("indicators", "VALUE_IN_EUROS"),
            ("sinceTimePeriod", f"{first_year}-01"),
            ("untilTimePeriod", through.strftime("%Y-%m")),
        ]
        params.extend(("reporter", REPORTERS[name]) for name in reporters)
        url = API + "?" + urlencode(params)
        title = f"Eurostat {first_year}—{through.year} 年欧洲自中国进口{PRODUCTS[code]}统计"
        parser = partial(
            rows,
            expected_reporters={REPORTERS[name]: name for name in reporters},
            code=code,
            start_year=first_year,
            through=through,
            months=plan.get("trade_months", 9),
        )
        jobs.append(
            (url, title, "Eurostat", LANDING, parser, f"comext-months-{plan.get('trade_months', 9)}")
        )
    return jobs


def rows(raw, *, expected_reporters, code, start_year, through, months):
    data = json.loads(raw, parse_float=Decimal)
    if set(data.get("id", [])) != set(DIMENSIONS) or data.get("source") != "ESTAT":
        raise ValueError("Eurostat 返回了不同的统计维度或来源")
    dimensions = data["dimension"]
    disaggregated = {}
    for dim in data["id"]:
        idx = dimensions[dim]["category"]["index"]
        disaggregated[dim] = sorted(idx, key=idx.get)
    bounded = {
        "freq": ["M"],
        "partner": ["CN"],
        "product": [code],
        "flow": ["1"],
        "indicators": ["VALUE_IN_EUROS"],
    }
    if any(disaggregated[dim] != expected for dim, expected in bounded.items()):
        raise ValueError("Eurostat 返回了不同的贸易流向、产品或货币")
    if set(disaggregated["reporter"]) - expected_reporters.keys():
        raise ValueError("Eurostat 返回了未请求的报告地区")
    expected_size = [len(disaggregated[d]) for d in data["id"]]
    if expected_size != data.get("size"):
        raise ValueError("Eurostat 数据维度长度不一致")

    values = data["value"]
    period_values = defaultdict(dict)
    for offset, keys in enumerate(product(*(disaggregated[dim] for dim in data["id"]))):
        axes = dict(zip(data["id"], keys))
        value = values[offset] if isinstance(values, list) else values.get(str(offset))
        if value is None:
            continue
        if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", axes["time"]):
            raise ValueError("Eurostat 月度时间码无效")
        year, month = map(int, axes["time"].split("-"))
        if not start_year <= year <= through.year or (year == through.year and month > through.month):
            raise ValueError("Eurostat 返回了日期范围外的观测")
        price = Decimal(value) / 100_000_000
        if not price.is_finite() or price < 0:
            raise ValueError("Eurostat 返回了无效进口额")
        period_values[expected_reporters[axes["reporter"]], year][month] = price

    label = PRODUCTS[code]
    observed = []
    notes = [
        (
            "计量口径",
            f"Eurostat 发布欧洲报告方自中国进口{label}的名义欧元金额（CN {code}）。"
            "月度累加仅在窗口内各月都有观测时进行。数据按进口申报的原产地归类。",
        )
    ]
    for (region, year), values in period_values.items():
        for month, amount in values.items():
            observed.append(
                (region, year, f"自中国进口{label}额（Eurostat，{month}月）", "亿欧元", str(amount))
            )
        windows = {months: f"1—{months}月", 12: "全年"}
        for length, name in windows.items():
            missing = [str(month) for month in range(1, length + 1) if month not in values]
            if missing:
                if length == months:
                    notes.append(
                        (
                            f"{region} · {year}年窗口缺项",
                            f"{region} {year}年缺少{'、'.join(missing)}月的进口额，未计算{name}累计金额。",
                        )
                    )
                continue
            amount = sum(values[month] for month in range(1, length + 1))
            observed.append(
                (region, year, f"自中国进口{label}额（Eurostat，{name}）", "亿欧元", str(amount))
            )
    if not observed:
        raise ValueError("Eurostat 没有返回该月度范围内的可用数据")
    return observed, notes
