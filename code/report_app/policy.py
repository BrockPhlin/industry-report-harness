"""Targeted retrieval of dated official policy documents for the report."""

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
import re


@dataclass(frozen=True)
class Policy:
    year: int
    region: str
    title: str
    issuer: str
    url: str
    topics: tuple[str, ...]
    identifier: str
    fingerprint: str = ""
    notes: tuple[tuple[str, str], ...] = ()


POLICIES = (
    Policy(
        2025,
        "China",
        "分布式光伏发电开发建设管理办法解读",
        "国家能源局",
        "https://www.nea.gov.cn/20250123/d38e5436b4d04159863ddbc10a6ede10/c.html",
        ("分布式管理", "户用备案", "接网", "上网模式", "工商业", "政策"),
        "管理办法",
    ),
    Policy(
        2025,
        "China",
        "新能源上网电价市场化改革（136号）",
        "国家发展改革委、国家能源局",
        "https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=20482",
        ("市场化", "上网电价", "机制电价", "价格改革", "电价改革"),
        "136号",
    ),
    Policy(
        2025,
        "China",
        "单用户绿电直连（650号）",
        "国家发展改革委、国家能源局",
        "https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=20511",
        ("绿电直连", "以荷定源", "消纳", "源荷"),
        "650号",
    ),
    Policy(
        2026,
        "China",
        "多用户绿电直连（688号）",
        "国家发展改革委、国家能源局",
        "https://www.ndrc.gov.cn/xxgk/zcfb/tz/202605/t20260520_1405313.html",
        ("绿电直连", "以荷定源", "源荷", "多用户"),
        "688号",
    ),
    Policy(
        2025,
        "江苏",
        "江苏省新能源上网电价改革实施方案（苏发改规发5号）",
        "江苏省发展改革委",
        "https://fzggw.jiangsu.gov.cn/art/2025/10/21/art_51007_11659583.html",
        ("市场化", "上网电价", "机制电价", "电价改革", "政策"),
        "苏发改规发〔2025〕5号",
    ),
    Policy(
        2025,
        "浙江",
        "浙江省新能源上网电价市场化改革实施方案（浙发改能源250号）",
        "浙江省发展改革委、浙江省能源局",
        "https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web2792/site/attach/0/3ba0c545a1724b23b7102dd6f7e3e250.pdf",
        ("市场化", "上网电价", "机制电价", "电价改革", "政策"),
        "浙发改能源〔2025〕250号",
        "0be9003dbe1877cf574d06810e4d6b7b22d9e64647c570a924dc6de0b364639a",
        (
            (
                "浙江 · PDF 第3页（一）",
                "浙江方案要求风电和光伏上网电量进入电力市场。统调项目按规则报量报价，其他项目通常作为价格接受者，根据同类项目的月度市场均价结算。",
            ),
            (
                "浙江 · PDF 第4页（四）",
                "浙江方案把适用的新能源存量项目机制电价定为0.4153 元/千瓦时。经竞争配置取得上网电价的项目沿用既有价格。机制电量按比例乘以实际上网电量确定。",
            ),
            (
                "浙江 · PDF 第10页第一条",
                "配套细则按全容量投产时间区分存量与增量。2025年6月1日之前投产为存量，2025年6月1日及以后投产为增量。具体投产时点的认定依据配套竞价细则。",
            ),
        ),
    ),
    Policy(
        2024,
        "China",
        "新能源消纳统计政策（国能发电力44号）",
        "国家能源局",
        "https://zfxxgk.nea.gov.cn/2024-05/28/c_1310777105.htm",
        ("光伏利用率", "受限电量", "弃光", "消纳工作", "消纳口径"),
        "国能发电力〔2024〕44号",
    ),
)

MARKERS = (
    "光伏",
    "适用范围",
    "绿电直连",
    "接网",
    "建设规模",
    "退运",
    "上网电量",
    "市场交易",
    "机制电价",
    "发电量",
    "可用发电量",
    "受限电量",
    "2026年1月1日",
    "2025年6月1日",
)


class LeafBlocks(HTMLParser):
    """Capture article text in leaf paragraphs and divs without page-level concatenation."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.blocks = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignored += 1
        if tag in ("div", "p", "td", "h1", "h2", "h3"):
            if self.stack:
                self.stack[-1]["children"] = True
            self.stack.append({"tag": tag, "text": [], "children": False})
        if tag == "br" and self.stack and not self.ignored:
            self.emit(self.stack[-1])

    def handle_data(self, data):
        if self.stack and not self.ignored:
            self.stack[-1]["text"].append(data)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignored = max(0, self.ignored - 1)
        if self.stack and self.stack[-1]["tag"] == tag:
            block = self.stack.pop()
            if not block["children"]:
                self.emit(block)

    def emit(self, block):
        line = " ".join("".join(block["text"]).split())
        if line:
            self.blocks.append(line)
        block["text"].clear()


def parse_policy(raw, *, policy):
    if policy.fingerprint:
        if sha256(raw).hexdigest() != policy.fingerprint:
            raise ValueError("政策文件已改版，待复核原文页码和摘记")
        return [], [(locator, text + "（项目组核对的原文摘记）") for locator, text in policy.notes]
    article = raw.decode("utf-8-sig")
    if policy.identifier not in re.sub(r"\s+", "", article):
        raise ValueError("政策文号或标题未匹配")
    parser = LeafBlocks()
    parser.feed(article)
    parser.close()
    selected = [
        (f"{policy.region} · 正文第 {index} 段", line)
        for index, line in enumerate(parser.blocks, 1)
        if 48 <= len(line) <= 1800
        and any(key in line for key in MARKERS)
        and not line.startswith(("各省、", "各省（", "各设区市", "为贯彻落实"))
    ]
    if not selected:
        raise ValueError("发布网页未提供可定位的政策正文")
    return [], selected
