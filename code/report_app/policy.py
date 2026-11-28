"""Targeted retrieval of dated official policy documents for the report."""

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
import re


TAX_TOPICS = ("出口退税", "消费税")


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
    document_url: str = ""


POLICIES = (
    Policy(
        2025,
        "China",
        "分布式光伏发电开发建设管理办法（7号）",
        "国家能源局",
        "https://www.nea.gov.cn/20250123/112c5b199c5f45dd8e7ac93c9f5e4eaf/c.html",
        ("分布式管理", "户用备案", "接网", "上网模式", "工商业", "政策"),
        "国能发新能规〔2025〕7号",
        "9e05e863abc95b99b68409df4f8e482d85541204e8c427c89a2c1efdd7675a03",
        (
            (
                "China · 附件第四条",
                "办法将分布式光伏分为自然人户用、非自然人户用、一般工商业和大型工商业四类。",
            ),
            (
                "China · 附件第五条",
                "一般工商业项目可全部自发自用或自发自用余电上网，余电上网项目的年自用比例由省级能源主管部门确定。"
                "大型工商业项目原则上全部自用，现货市场连续运行地区可自用余电上网并参与现货市场。"
                "涉及自用的用户和发电项目须在同一用地红线范围。",
            ),
            (
                "China · 附件第十二条",
                "备案按投资主体确定，自然人户用可自行备案或由电网企业代理。"
                "非自然人户用、一般工商业和大型工商业由投资主体备案。",
            ),
            (
                "China · 附件第二十三条",
                "省级能源主管部门组织承载力评估，建立配电网可开放容量按季度发布和预警机制。"
                "评估考虑分布式装机规模、负荷、系统运行、灵活调节能力和设备容量等因素。",
            ),
        ),
        "https://www.nea.gov.cn/20250123/112c5b199c5f45dd8e7ac93c9f5e4eaf/"
        "20250123112c5b199c5f45dd8e7ac93c9f5e4eaf_010446cd75b7d649969599bba99df7d0dd.doc",
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
        2026,
        "江苏",
        "江苏省分布式光伏发展实施方案（2026—2030年，695号）",
        "江苏省发展改革委",
        "https://fzggw.jiangsu.gov.cn/art/2026/7/29/art_84097_11809969.html",
        ("分布式光伏", "江苏", "园区", "绿电直连", "配网", "集中汇流"),
        "苏发改能源发〔2026〕695号",
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
    Policy(
        2026,
        "China",
        "光伏等产品出口退税公告（2026年第2号）",
        "财政部、税务总局",
        "https://szs.mof.gov.cn/zhengcefabu/202601/t20260109_3981637.htm",
        ("出口退税", "关税", "贸易政策"),
        "财政部税务总局公告2026年第2号",
    ),
    Policy(
        2026,
        "China",
        "光伏出口退税公告附件1产品清单",
        "财政部、税务总局",
        "https://szs.mof.gov.cn/zhengcefabu/202601/t20260109_3981637.htm",
        ("出口退税", "关税", "贸易政策"),
        "光伏等产品清单",
        "1276198b41d98cb7de7b21ab7ef3141ff21fa0deb118d3376db86379a4422be9",
        (
            (
                "China · PDF 第10页第247、248项",
                "公告附件1列出未装配光电池（85414200）和已装在组件内或组装成块的光电池（85414300）。"
                "这两项属于附件1光伏产品清单。实施日期与税种以公告正文为准。",
            ),
        ),
        "https://szs.mof.gov.cn/zhengcefabu/202601/P020260109557339206884.pdf",
    ),
    Policy(
        2026,
        "China",
        "光伏电池消费税公告（2026年第20号）",
        "财政部、海关总署、税务总局",
        "https://szs.mof.gov.cn/zhengcefabu/202607/t20260717_3993743.htm",
        ("消费税",),
        "财政部海关总署税务总局公告2026年第20号",
    ),
)

MARKERS = (
    "光伏",
    "出口退税",
    "单一电力用户",
    "多个不同法人",
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
    minimum_length = 28 if set(TAX_TOPICS).intersection(policy.topics) else 48
    markers = ("光伏电池", "国家标准", "应税电池") if "消费税" in policy.topics else MARKERS
    selected = [
        (f"{policy.region} · 正文第 {index} 段", line)
        for index, line in enumerate(parser.blocks, 1)
        if minimum_length <= len(line) <= 1800
        and any(key in line for key in markers)
        and not line.startswith(("各省、", "各省（", "各设区市", "为贯彻落实"))
    ]
    if not selected:
        raise ValueError("发布网页未提供可定位的政策正文")
    return [], selected
