"""Annual UN Comtrade data for photovoltaic modules and unassembled cells."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import partial
import json
from urllib.parse import urlencode

TRADE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
PRODUCTS = {"854143": "光伏组件", "854142": "未组装光伏电池片"}
COUNTRIES = {
    "China": (156, "中国"),
    "Germany": (276, "德国"),
    "United States": (842, "美国"),
    "India": (699, "印度"),
    "Japan": (392, "日本"),
    "Netherlands": (528, "荷兰"),
    "Brazil": (76, "巴西"),
    "France": (251, "法国"),
    "Australia": (36, "澳大利亚"),
    "Spain": (724, "西班牙"),
    "Vietnam": (704, "越南"),
    "Malaysia": (458, "马来西亚"),
    "South Korea": (410, "韩国"),
    "United Kingdom": (826, "英国"),
    "Pakistan": (586, "巴基斯坦"),
    "Saudi Arabia": (682, "沙特阿拉伯"),
    "United Arab Emirates": (784, "阿联酋"),
    "Indonesia": (360, "印度尼西亚"),
    "Thailand": (764, "泰国"),
    "South Africa": (710, "南非"),
    "Mexico": (484, "墨西哥"),
    "Chile": (152, "智利"),
    "Italy": (380, "意大利"),
    "Poland": (616, "波兰"),
    "Canada": (124, "加拿大"),
    "Turkey": (792, "土耳其"),
    "Singapore": (702, "新加坡"),
}
PARTNER_LABELS = {code: name for code, name in COUNTRIES.values()} | {0: "世界"}
ALIASES = {local: english for english, (_, local) in COUNTRIES.items()}
ALIASES.update(
    {
        "沙特": "Saudi Arabia",
        "印尼": "Indonesia",
        "Türkiye": "Turkey",
        "World": "World",
        "全球": "World",
        "世界": "World",
    }
)


def trade_country(label):
    return ALIASES.get(label, label)


def trade_jobs(plan):
    topic = plan["title"] + " " + " ".join(plan["keywords"])
    if not any(w in topic for w in ("贸易", "出口", "进口", "进出口", "海关")):
        return []
    flows = []
    if any(w in topic for w in ("进口", "进出口")):
        flows.append(("M", "进口"))
    if "出口" in topic or not flows:
        flows.append(("X", "出口"))
    products = tuple(p for p in PRODUCTS if p in plan.get("trade_products", ["854143"])) or ("854143",)
    jobs = []
    for raw_name in plan.get("trade_regions", plan["regions"]):
        region = trade_country(raw_name)
        if region not in COUNTRIES:
            continue
        reporter = COUNTRIES[region][0]
        requested = (trade_country(p) for p in plan.get("trade_partners", []))
        partners = (0, *sorted({COUNTRIES[p][0] for p in requested if p in COUNTRIES and p != region}))
        for year in range(max(2022, plan["start"]), min(date.today().year - 1, plan["end"]) + 1):
            for flow, label in flows:
                params = dict(
                    period=year,
                    reporterCode=reporter,
                    cmdCode=",".join(products),
                    flowCode=flow,
                    partnerCode=",".join(map(str, partners)),
                    partner2Code=0,
                    customsCode="C00",
                    motCode=0,
                    maxRecords=max(5, len(partners) * len(products)),
                )
                url = TRADE + "?" + urlencode(params)
                if len(partners) == len(products) == 1:
                    title = f"{year} 年 {region} {PRODUCTS[products[0]]}{label}额"
                else:
                    title = f"{year} 年 {region} 光伏产品{label}额分市场统计"
                parser = partial(
                    trade_rows,
                    year=year,
                    region=region,
                    flow=flow,
                    label=label,
                    products=products,
                    partners=partners,
                )
                jobs.append((url, title, "联合国 Comtrade", url, parser))
    return jobs


def trade_rows(raw, *, year, region, flow, label, products=("854143",), partners=(0,)):
    reporter = COUNTRIES[region][0]
    returned = {}
    for row in json.loads(raw, parse_float=Decimal)["data"]:
        product, partner = row.get("cmdCode"), row.get("partnerCode")
        if (
            str(row.get("period")) != str(year)
            or row.get("reporterCode") != reporter
            or product not in products
            or row.get("flowCode") != flow
            or partner not in partners
            or row.get("partner2Code") != 0
            or row.get("motCode") != 0
            or row.get("customsCode") != "C00"
            or row.get("primaryValue") is None
        ):
            continue
        key = (product, partner)
        try:
            value = Decimal(str(row["primaryValue"])) / 100_000_000
        except InvalidOperation:
            raise ValueError("接口返回无效贸易金额") from None
        if key in returned or not value.is_finite() or value < 0:
            raise ValueError("接口返回重复或无效的商品与伙伴记录")
        returned[key] = value
    if not returned:
        raise ValueError("没有可用的年度商品与伙伴记录")

    observed, notes = [], []
    missing = []
    for product in products:
        total = returned.get((product, 0))
        for partner in partners:
            market = PARTNER_LABELS[partner]
            value = returned.get((product, partner))
            if value is None:
                missing.append(f"{PRODUCTS[product]}对{market}")
                continue
            observed.append(
                (
                    region,
                    year,
                    f"{PRODUCTS[product]}{label}额（HS {product}，对{market}，现价）",
                    "亿美元",
                    str(value),
                )
            )
            if partner and total and value <= total:
                share = (100 * value / total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                reporter_name = COUNTRIES[region][1]
                notes.append(
                    (
                        f"{product} · {label} · {market}",
                        f"{year}年，{reporter_name}{PRODUCTS[product]}对{market}{label}额"
                        f"占该类商品对世界{label}额的{share}%。分母是同年、同一报告方、同商品和同流向的世界合计。",
                    )
                )
    if missing:
        notes.append(
            ("接口缺项", f"{year}年下列项目没有返回记录，不能填为零：" + "、".join(missing) + "。")
        )
    return observed, notes
