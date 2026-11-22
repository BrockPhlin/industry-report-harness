"""Extract manufacturing series while keeping each publisher's statistical scope."""

import re

# Readers can open the original release even when a reprint supplies the bytes.
# The URLs are fixed so the parser has a known document layout for each year.
RELEASES = {
    2022: (
        "工信部电子信息司",
        "https://www.miit.gov.cn/jgsj/dzs/gzdt/art/2023/art_fa9613fe209e4788a55ae39b85b6c287.html",
        "https://www.cpem.org.cn/list40/59077.html",
    ),
    2023: (
        "工信部电子信息司",
        "https://wap.miit.gov.cn/jgsj/dzs/gzdt/art/2024/art_23c220a8b3b34340851632dfae47a34e.html",
        "https://www.ciaps.org.cn/news/show-htm-itemid-39596.html",
    ),
    2024: (
        "工信部电子信息司",
        "https://www.miit.gov.cn/gyhxxhb/jgsj/dzxxsnew/xyyx/art/2025/art_1717bf6fa0a34311a2c347fb9623e607.html",
        None,
    ),
    2025: (
        "中国机电产品进出口商会",
        "https://www.cccme.org.cn/model5-1/news/details.aspx?classid=7685F2FA1E54A7F5&id=B31FE14D32F9104E20D30B61AB70D332&xgid=F868932F64EB7AAF",
        None,
    ),
}

SECTORS = ("多晶硅", "硅片", "电池", "组件")
NUM = r"\d+(?:\.\d+)?"
POWER = r"(?:GW|吉瓦(?:\s*[（(]GW[）)])?)"


def manufacturing_observations(passages, year):
    """Use publisher-specific headers and require all four values before import."""
    values = []
    if year in (2022, 2025):
        prefix = "全国" if year == 2022 else "国内"
        battery = "电池" if year == 2022 else "电池片"
        form = "达到" if year == 2022 else "为"
        phrase = rf"{prefix}多晶硅、硅片、{battery}、组件产量分别{form}({NUM})万吨、({NUM}){POWER}、({NUM}){POWER}、({NUM}){POWER}"
        matches = [match for text in passages for match in re.findall(phrase, text)]
        if len(matches) == 1:
            values = [("", value) for value in matches[0]]
    else:
        for sector in SECTORS:
            phrase = rf"^{sector}环节，1[—－–-]12月全国(晶硅)?(?:{sector})?产量(达到|超过)({NUM})(?:万吨|{POWER})"
            matches = [match for text in passages for match in re.findall(phrase, text)]
            if len(matches) != 1:
                raise ValueError(f"{year} 年{sector}产量段的格式已更改")
            subset, predicate, value = matches[0]
            note = (["晶硅"] if subset else []) + (["发布下限"] if predicate == "超过" else [])
            values.append(("，".join(note), value))
    if len(values) != len(SECTORS):
        raise ValueError(f"{year} 年制造产量段的格式已更改")

    publisher = "机电商会" if year == 2025 else "工信部"
    return [
        ("China", year, f"光伏{sector}产量（{publisher}{'，' + scope if scope else ''}）", unit, value)
        for sector, (scope, value), unit in zip(SECTORS, values, ("万吨", "GW", "GW", "GW"))
    ]
