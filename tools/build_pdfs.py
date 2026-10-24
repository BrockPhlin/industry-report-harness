"""Build the paginated report and slide PDF from repository sources.

Data flow: Markdown page sections or slide JSON -> ReportLab flowables -> PDF.
This is deliberately a small Markdown subset. It rejects malformed tables,
unsupported syntax and page overflow rather than silently clipping or adding
pages. The slide PDF uses the same content/coordinates as the editable PPTX.
It is not a PDF converter for arbitrary PowerPoint files.
"""
from __future__ import annotations

import html
import io
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "presentations/01-opening"
BLUE = "#003F88"
INK = "#233042"
PALE = "#ECF3FA"
MUTED = "#60728C"


def register_fonts():
    for alias, filename in [("Body", "LXGWWenKai-Regular.ttf"),
                            ("Strong", "LXGWWenKai-Medium.ttf"),
                            ("Title", "SmileySans-Oblique.ttf")]:
        pdfmetrics.registerFont(TTFont(alias, str(ROOT / "assets/fonts" / filename)))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Strong", italic="Body", boldItalic="Strong")


def inline(value):
    value = html.escape(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    return re.sub(r"`([^`]+)`", r"\1", value)


def make_table(lines, width):
    rows = [[x.strip() for x in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) < 2 or any(not re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]):
        raise ValueError("Invalid Markdown table separator")
    values = [rows[0]] + rows[2:]
    ncols = len(rows[0])
    if any(len(row) != ncols for row in values):
        raise ValueError("Inconsistent table columns")
    widths = {2: [.22, .78], 3: [.22, .30, .48], 4: [.10, .62, .16, .12]}[ncols]
    if rows[0][0] == "成员" and ncols == 4:
        widths = [.14, .57, .17, .12]
    elif rows[0][0].startswith("编号"):
        widths = [.19, .27, .54]
    elif rows[0][0].startswith("风险"):
        widths = [.24, .28, .48]
    elif rows[0][0] == "成员" and ncols == 3:
        widths = [.14, .45, .41]
    elif rows[0][0] == "时间":
        widths = [.23, .43, .34]
    elif rows[0][0] == "项目":
        widths = [.21, .29, .50]
    style = ParagraphStyle("cell", fontName="Body", fontSize=10.1, leading=14.5,
                           textColor=colors.HexColor(INK), wordWrap="CJK")
    strong = ParagraphStyle("header", parent=style, fontName="Strong", textColor=colors.HexColor(BLUE))
    data = [[Paragraph(inline(c), strong if i == 0 else style) for c in row] for i, row in enumerate(values)]
    result = Table(data, colWidths=[width * f for f in widths], hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PALE)),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#D9D9D9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return result


def report_blocks(section, width):
    styles = {
        "body": ParagraphStyle("body", fontName="Body", fontSize=11.1, leading=17,
                               textColor=colors.HexColor(INK), wordWrap="CJK", spaceAfter=8),
        "h1": ParagraphStyle("h1", fontName="Strong", fontSize=18, leading=25,
                             textColor=colors.HexColor(BLUE), spaceAfter=13),
        "h2": ParagraphStyle("h2", fontName="Strong", fontSize=13, leading=20,
                             textColor=colors.HexColor(BLUE), spaceBefore=8, spaceAfter=7),
        "h3": ParagraphStyle("h3", fontName="Strong", fontSize=11.5, leading=18,
                             textColor=colors.HexColor(BLUE), spaceBefore=7, spaceAfter=5),
    }
    lines = section.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i]); i += 1
            yield make_table(block, width)
            yield Spacer(1, 9)
            continue
        heading = re.match(r"^(#{1,3}) (.+)$", line)
        if heading:
            yield Paragraph(inline(heading.group(2)), styles[f"h{len(heading.group(1))}"])
            i += 1
            continue
        if line.startswith(("```", "<", "####")):
            raise ValueError(f"Unsupported report block: {line[:50]}")
        yield Paragraph(inline(line), styles["body"])
        i += 1


def visible_character_count(source):
    """Conservative visible-character count, NOT an editor word-count substitute."""
    source = re.sub(r"<!--.*?-->", "", source, flags=re.S)
    source = re.sub(r"^\|[\s|:\-]+\|\s*$", "", source, flags=re.M)
    source = re.sub(r"^[#]+\s+", "", source, flags=re.M)
    source = source.replace("**", "").replace("|", "").replace("`", "")
    return len(re.sub(r"\s", "", source))


def build_report():
    source = (PROPOSAL / "report/report.md").read_text(encoding="utf-8")
    sections = re.split(r"<!--\s*pagebreak\s*-->", source)
    if len(sections) != 7:
        raise ValueError("Expected seven explicitly paginated report sections")
    count = visible_character_count(source)
    if count > 6000:
        raise ValueError(f"Conservative visible-character count {count} exceeds 6000")
    buf = io.BytesIO()
    w, h = A4
    margin = 48
    width = w - 2 * margin
    pdf = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
    pdf.setTitle("Industry Report Generation System Project Plan v0.8")
    pdf.setAuthor("Team 11")
    remaining = []
    for i, section in enumerate(sections, 1):
        pdf.setFillColor(colors.HexColor(MUTED)); pdf.setFont("Body", 8.5)
        pdf.drawString(margin, h-32, "软件工程管理 / 项目计划书 / v0.8")
        pdf.drawRightString(w-margin, h-32, "第11组 · 2026-10-23")
        pdf.setStrokeColor(colors.HexColor(BLUE)); pdf.setLineWidth(.6)
        pdf.line(margin, h-43, w-margin, h-43)
        y = h-65
        blocks = list(report_blocks(section, width))
        if i == len(sections):
            note = f"源文件：Markdown；编辑工具：Codex；生成器可见非空白字符计数：{count}。"
            blocks.append(Paragraph(note, ParagraphStyle("count", fontName="Body", fontSize=8.5,
                                                        leading=12, wordWrap="CJK", textColor=colors.HexColor(MUTED))))
        for flowable in blocks:
            y -= getattr(flowable, "spaceBefore", 0)
            _, fh = flowable.wrap(width, h)
            if y-fh < 51:
                raise ValueError(f"Report page {i} overflows by {51-(y-fh):.1f}pt")
            flowable.drawOn(pdf, margin, y-fh)
            y -= fh + getattr(flowable, "spaceAfter", 0)
        remaining.append(round(y-51, 1))
        pdf.setFont("Body", 8.5); pdf.setFillColor(colors.HexColor(MUTED))
        pdf.drawString(margin, 29, "第11组产业智能报告生成系统项目计划书")
        pdf.drawRightString(w-margin, 29, f"{i} / {len(sections)}")
        pdf.showPage()
    pdf.save()
    output = PROPOSAL / "report/第11组_项目计划书_v0.8.pdf"
    output.write_bytes(buf.getvalue())
    print(json.dumps({"report_pages": len(sections), "visible_character_count": count,
                      "page_remaining_pt": remaining}, ensure_ascii=False))


def slide_text(pdf, item):
    font = "Title" if item.get("font") == "title" else ("Strong" if item.get("bold") else "Body")
    size = item["size"]
    style = ParagraphStyle("slide-text", fontName=font, fontSize=size, leading=size*1.24,
                           wordWrap="CJK", textColor=colors.HexColor(item.get("color", INK)))
    p = Paragraph(html.escape(item["text"]).replace("\n", "<br/>"), style)
    _, ph = p.wrap(item["w"], item["h"])
    if ph > item["h"] + 2:
        raise ValueError(f"Slide text overflows: {item['text'][:30]} ({ph}>{item['h']})")
    p.drawOn(pdf, item["x"], 720-item["y"]-ph)


def slide_table(pdf, item):
    rows = item["rows"]
    base = ParagraphStyle("slide-cell", fontName="Body", fontSize=item["size"],
                          leading=item["size"]*1.2, wordWrap="CJK", textColor=colors.HexColor(INK))
    strong = ParagraphStyle("slide-th", parent=base, fontName="Strong", textColor=colors.HexColor(BLUE))
    vals = [[Paragraph(html.escape(str(cell)), strong if i==0 else base) for cell in row]
            for i,row in enumerate(rows)]
    row_h = item["h"] / len(rows)
    widths = [item["w"]*f for f in item["widths"]]
    for i,row in enumerate(vals):
        for j,cell in enumerate(row):
            _,ph = cell.wrap(widths[j]-20, row_h)
            if ph > row_h-12:
                raise ValueError(f"Slide table overflow row {i}, col {j}: {rows[i][j]}")
    t = Table(vals, colWidths=widths, rowHeights=[row_h]*len(rows))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor(PALE)),
        ("GRID", (0,0), (-1,-1), .6, colors.HexColor("#D9E1EB")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
    ]))
    t.wrap(item["w"],item["h"])
    t.drawOn(pdf,item["x"],720-item["y"]-item["h"])


def build_slide_pdf():
    deck = json.loads((PROPOSAL / "ppt/slides.json").read_text())
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(1280,720), pageCompression=1)
    pdf.setTitle(deck["title"]+" 开题展示 v0.4")
    for idx,slide in enumerate(deck["slides"]):
        if idx == 0:
            pdf.setFillColor(colors.HexColor(PALE)); pdf.rect(65,720-330-90,1150,90,fill=1,stroke=0)
        else:
            slide_text(pdf,dict(type="text",text=slide["title"],x=60,y=27,w=1040,h=58,size=40,font="title",color=BLUE))
            slide_text(pdf,dict(type="text",text=slide["subtitle"],x=65,y=100,w=1100,h=40,size=23,color=MUTED))
            pdf.setStrokeColor(colors.HexColor(BLUE));pdf.setLineWidth(3)
            pdf.line(60,720-90,1220,720-90)
            pdf.drawImage(str(ROOT/'assets/brand/char_blue.png'),1100,720-30-45,width=115,height=39,
                          preserveAspectRatio=True,mask='auto')
        for item in slide["items"]:
            if item["type"] == "text":
                slide_text(pdf,item)
            elif item["type"] == "table":
                slide_table(pdf,item)
            elif item["type"] == "image":
                pdf.drawImage(str(ROOT/item["path"]),item["x"],720-item["y"]-item["h"],
                              width=item["w"],height=item["h"],preserveAspectRatio=True,mask='auto')
            elif item["type"] == "flow":
                pdf.setStrokeColor(colors.HexColor(BLUE));pdf.setLineWidth(1.5)
                for x1,y1,x2,y2 in item["edges"]:
                    pdf.line(x1,720-y1,x2,720-y2)
                for title,body,x,y,w,h in item["nodes"]:
                    pdf.setFillColor(colors.HexColor(PALE));pdf.rect(x,720-y-h,w,h,stroke=1,fill=1)
                    slide_text(pdf,dict(text=title,x=x+15,y=y+13,w=w-30,h=40,size=30,bold=True,color=BLUE))
                    slide_text(pdf,dict(text=body,x=x+15,y=y+63,w=w-30,h=35,size=23,color=INK))
        slide_text(pdf,dict(text="开题草案 v0.4 / 计划与实际分开记录",x=65,y=682,w=1040,h=25,size=17,color=MUTED))
        slide_text(pdf,dict(text=f"{idx+1:02d} / {len(deck['slides']):02d}",x=1135,y=682,w=100,h=25,size=17,color=MUTED))
        pdf.showPage()
    pdf.save()
    (PROPOSAL / "ppt/第11组_开题展示_模板_v0.4.pdf").write_bytes(buf.getvalue())
    print(f"Slide PDF: {len(deck['slides'])} pages, selectable text")


if __name__ == "__main__":
    register_fonts()
    build_report()
    build_slide_pdf()
