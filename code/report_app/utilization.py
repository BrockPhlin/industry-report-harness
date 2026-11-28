"""Published provincial PV utilization rates, keyed by checked original release."""

import csv
from hashlib import sha256
from pathlib import Path

# The first report gives both its current year and the previous year.
SOURCES = (
    (
        (2021, 2022),
        "国家能源局",
        "https://zfxxgk.nea.gov.cn/2023-09/07/c_1310741874.htm",
        "https://zfxxgk.nea.gov.cn/1310741874_16950245781111n.docx",
        "04177becaaf4df6ce3c4ffe64881243ea4da250b7cffb75aa9ab3f2c168902a5",
        "表6",
    ),
    (
        (2023,),
        "国家能源局",
        "https://zfxxgk.nea.gov.cn/2024-10/10/c_1310787115.htm",
        "https://zfxxgk.nea.gov.cn/1310787115_17307953361061n.doc",
        "5bda0829d9f0d94397719715b57ad9b7c2d306709da004791403ef2e39205053",
        "表4",
    ),
    (
        (2024,),
        "国家能源局",
        "https://www.nea.gov.cn/20251113/cc1fb0298a2944f8bd5441f67c9be9b3/c.html",
        "https://www.nea.gov.cn/20251113/cc1fb0298a2944f8bd5441f67c9be9b3/20251113cc1fb0298a2944f8bd5441f67c9be9b3_54b6e6c1674e9c4bdca1cdfb4cbb16b477.doc",
        "b2c460a50a2bcd379b1a8c18b0b4c992fffff047dc8c5bb775aa7845ccd62449",
        "表4",
    ),
    (
        (2025,),
        "电力行业规划研究与监测预警中心",
        "https://www.piinfo.com.cn/news/show-12450.html",
        "https://public.solarbe.com/webupload/image/News/20260206/3e1794b36800c66.png",
        "75866bd5d992d8e81e03a3b1010f0b5e83fc60c65ae0f3069a2ded2c0fc8e582",
        "2025年列",
    ),
)
METRIC = "光伏发电利用率"
AREAS = {"蒙东", "蒙西"}


def utilization_rows(raw, *, years, fingerprint, location):
    if sha256(raw).hexdigest() != fingerprint:
        raise ValueError("消纳统计资料已换版，待核对对应表格")
    path = Path(__file__).resolve().parents[1] / "data/nea/utilization-annual.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = [
            (rec["地区"], year, METRIC, "%", rec[str(year)])
            for rec in csv.DictReader(stream)
            for year in years
        ]
    note = "蒙东、蒙西是分开发布的统计区域。合并全区需要可用发电量作为权重。"
    if max(years) >= 2024:
        note += "按国能发电力〔2024〕44号，新能源利用率计算只计系统原因受限电量。"
    return rows, [(location + " · 指标口径", note)]
