"""Fixed observations from the publishers' own market and cost studies."""

import csv
from dataclasses import dataclass
from functools import partial
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class Study:
    key: str
    title: str
    publisher: str
    landing: str
    url: str
    digest: str
    start: int
    end: int
    countries: frozenset
    location: str
    scope: str


PVPS = "https://iea-pvps.org"
IRENA = "https://www.irena.org"
STUDIES = (
    Study(
        "pvps-trends-2026",
        "IEA PVPS《2026 年光伏应用趋势》",
        "IEA PVPS",
        PVPS + "/trends_reports/trends-2026/",
        PVPS + "/wp-content/uploads/2026/09/Trends-In-PV-Applications-2026.pdf",
        "7c2470b6ee1e698de8ec78b22b7dbb74c4ef24cd69349cd106dfd022fe148c8c",
        2021,
        2025,
        frozenset(("Australia", "Brazil", "China", "France", "Germany", "India", "Netherlands",
                   "Pakistan", "United States", "World")),
        "PDF 第91—92页附录表，方法见第13页及第85—86页",
        "全球趋势报告以组件直流侧标称容量为统一口径。部分国家根据本国资料从交流侧换算，"
        "换算比随系统和市场变化。全球值是报告估计，表中四舍五入可能使逐国加总不同于原表合计。",
    ),
    Study(
        "pvps-china-2025",
        "IEA PVPS《2025 年中国光伏应用调查》",
        "IEA PVPS",
        PVPS + "/national_survey/nsr-china-2025/",
        PVPS + "/wp-content/uploads/2026/11/IEA-PVPS-NSR-China-2025.pdf",
        "70088a7636359e191970015f46bd42dd0b2d04ddf3a2a0acdf4a11535e9e237f",
        2021,
        2025,
        frozenset(("China",)),
        "PDF 第10页表1和表2、第11页表3",
        "中国调查按交流侧发布并网容量，年度新增和年末累计分开。"
        "全球趋势报告的直流估计另有处理，不能拿项目级或单一换算比调成同一序列。"
        "国内调查的全球比较需要统一接网统计与覆盖范围。",
    ),
    Study(
        "irena-cost-2025",
        "IRENA《2025 年可再生能源发电成本》",
        "IRENA",
        IRENA + "/Publications/2026/Jul/Renewable-Power-Generation-Costs-in-2025",
        IRENA + "/-/media/Files/IRENA/Agency/Publication/2026/Jul/IRENA_TEC_RPGC_2025_Executive_summary_2026.pdf",
        "2046b4146b69197a6d62f769a50fd76b87c31f558fbc8b8c4f621339e8b46905",
        2025,
        2025,
        frozenset(("Brazil", "China", "Germany", "India", "United States", "World")),
        "报告摘要 PDF 第8页图S3",
        "IRENA 发布的是新投运公用事业级光伏平准化发电成本，图S3按2025年美元每兆瓦时计。"
        "它体现项目成本口径，不能代替上网结算价格、组件成交价格或工商业屋顶报价。",
    ),
)


def rows(raw, *, study):
    if not raw.startswith(b"%PDF-") or sha256(raw).hexdigest() != study.digest:
        raise ValueError("报告版本已改变，待核对原始页码与入库观测")
    file = Path(__file__).resolve().parents[1] / "data" / "studies" / (study.key + ".csv")
    with file.open(encoding="utf-8", newline="") as stream:
        records = [
            (r["region"], int(r["year"]), r["metric"], r["unit"], r["value"])
            for r in csv.DictReader(stream)
        ]
    return records, [(study.location, study.scope)]


def jobs(plan, *, force=False):
    sections = " ".join([plan["title"], *plan["keywords"], *plan.get("sections", [])])
    selected = set(plan.get("industry_reference_ids", []))
    capacity = any(word in sections for word in ("装机", "并网", "直流", "交流", "PVPS"))
    cost = any(word in sections for word in ("成本", "平准化", "LCOE"))
    return [
        (study.url, study.title, study.publisher, study.landing, partial(rows, study=study))
        for study in STUDIES
        if study.start <= plan["end"] and study.end >= plan["start"]
        and study.countries.intersection(plan["regions"])
        and (force or study.key in selected or (cost if study.publisher == "IRENA" else capacity))
    ]
