"""Build the report PDF and selectable slide PDF from repository sources.

Data flow: Markdown page sections -> ReportLab flowables -> PDF.
This is deliberately a small Markdown subset. It rejects malformed tables,
unsupported syntax and page overflow rather than silently clipping or adding
pages. Slide PDF uses the same geometry and fonts as the editable PPTX; inspect both after edits.
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
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

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
    value = re.sub(r'\[([^\]]+)\]\((https://[^\s)]+)\)', r'<link href="\2" color="#003F88">\1</link>', value)
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
        widths = [.15, .55, .30]
    elif rows[0][0].startswith("风险"):
        widths = [.24, .28, .48]
    elif rows[0][0] == "成员" and ncols == 3:
        widths = [.14, .25, .61]
    elif rows[0][0].startswith("工作包"):
        widths = [.24, .61, .15]
    elif rows[0][0] == '章节':
        widths = [.12, .76, .12]
    elif rows[0][0] == "时间":
        widths = [.23, .43, .34]
    elif rows[0][0] == "项目":
        widths = [.21, .29, .50]
    style = ParagraphStyle("cell", fontName="Body", fontSize=10.8, leading=16,
                           textColor=colors.HexColor(INK), wordWrap="CJK")
    strong = ParagraphStyle("header", parent=style, fontName="Strong", textColor=colors.HexColor(BLUE))
    data = []
    for i, row in enumerate(values):
        cells = []
        for j, value in enumerate(row):
            content = inline(value)
            if rows[0][0] == '章节' and i > 0 and j == 2:
                if not value.isdigit() or not 1 <= int(value) <= 10:
                    raise ValueError('Contents page must target report page 1 to 10')
                content = f'<link href="#report-page-{value}" color="{BLUE}">{value}</link>'
            cells.append(Paragraph(content, strong if i == 0 else style))
        data.append(cells)
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


def report_blocks(section, width, cover=False):
    styles = {
        "body": ParagraphStyle("body", fontName="Body", fontSize=12, leading=18.5,
                               textColor=colors.HexColor(INK), wordWrap="CJK", spaceAfter=8),
        "h1": ParagraphStyle("h1", fontName="Strong", fontSize=20, leading=27,
                             textColor=colors.HexColor(BLUE), spaceAfter=13),
        "h2": ParagraphStyle("h2", fontName="Strong", fontSize=14, leading=21,
                             textColor=colors.HexColor(BLUE), spaceBefore=8, spaceAfter=7),
        "h3": ParagraphStyle("h3", fontName="Strong", fontSize=12, leading=19,
                             textColor=colors.HexColor(BLUE), spaceBefore=7, spaceAfter=5),
    }
    if cover:
        styles['h1'].fontSize = 26
        styles['h1'].leading = 36
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
        image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)(?:\{width=(\d{1,3})%\})?", line)
        if image:
            from PIL import Image as PILImage
            file = (PROPOSAL / 'report' / image.group(2)).resolve()
            with PILImage.open(file) as original:
                iw, ih = original.size
            factor = int(image.group(3) or '100') / 100
            if not .25 <= factor <= 1:
                raise ValueError('Report image width must be 25 to 100 percent')
            yield Image(str(file), width=width*factor, height=width*factor*ih/iw, hAlign='CENTER')
            yield Paragraph(inline(image.group(1)), ParagraphStyle('caption', fontName='Body', fontSize=9, leading=13, textColor=colors.HexColor(MUTED), spaceAfter=9, wordWrap='CJK'))
            i += 1
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
    source = re.sub(r'\{width=\d{1,3}%\}', '', source)
    source = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", source)
    source = re.sub(r"^\|[\s|:\-]+\|\s*$", "", source, flags=re.M)
    source = re.sub(r"^[#]+\s+", "", source, flags=re.M)
    source = source.replace("**", "").replace("|", "").replace("`", "")
    return len(re.sub(r"\s", "", source))


def build_report():
    source = (PROPOSAL / "report/report.md").read_text(encoding="utf-8")
    sections = re.split(r"<!--\s*pagebreak\s*-->", source)
    if not 1 <= len(sections) <= 10:
        raise ValueError("Report must contain 1 to 10 explicitly paginated pages")
    version = re.search(r"\*\*版本\*\*：([^\s]+)", source).group(1)
    date = re.search(r"\*\*日期\*\*：([0-9-]+)", source).group(1)
    count = visible_character_count(source)
    if count > 6000:
        raise ValueError(f"Conservative visible-character count {count} exceeds 6000")
    buf = io.BytesIO()
    w, h = A4
    margin = 56
    width = w - 2 * margin
    pdf = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
    pdf.setTitle(f"第11组产业智能报告生成系统项目计划书 {version}")
    pdf.setAuthor("Team 11")
    remaining = []
    for i, section in enumerate(sections, 1):
        pdf.bookmarkPage(f'report-page-{i}')
        pdf.setFillColor(colors.HexColor(MUTED)); pdf.setFont("Body", 8.5)
        pdf.drawString(margin, h-32, f"软件工程管理 / 项目计划书 / {version}")
        pdf.drawRightString(w-margin, h-32, f"第11组 · {date}")
        pdf.setStrokeColor(colors.HexColor(BLUE)); pdf.setLineWidth(.6)
        pdf.line(margin, h-43, w-margin, h-43)
        y = h-65
        blocks = list(report_blocks(section, width, cover=i == 1))
        if i == len(sections):
            note = f"可见非空白字符计数：{count}（含表格；提交前按课程统计口径复核）。"
            blocks.append(Paragraph(note, ParagraphStyle("count", fontName="Body", fontSize=8.5,
                                                        leading=12, wordWrap="CJK", textColor=colors.HexColor(MUTED))))
        for flowable in blocks:
            y -= getattr(flowable, "spaceBefore", 0)
            fw, fh = flowable.wrap(width, h)
            if y-fh < 51:
                raise ValueError(f"Report page {i} overflows by {51-(y-fh):.1f}pt")
            left = margin + (width-fw)/2 if isinstance(flowable, Image) else margin
            flowable.drawOn(pdf, left, y-fh)
            y -= fh + getattr(flowable, "spaceAfter", 0)
        remaining.append(round(y-51, 1))
        pdf.setFont("Body", 8.5); pdf.setFillColor(colors.HexColor(MUTED))
        pdf.drawString(margin, 29, "第11组产业智能报告生成系统项目计划书")
        pdf.drawRightString(w-margin, 29, f"{i} / {len(sections)}")
        pdf.showPage()
    pdf.save()
    output = PROPOSAL / 'report/第11组_项目计划书.pdf'
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
    vals = [[Paragraph(html.escape(str(cell)).replace("\n", "<br/>"), strong if i==0 else base) for cell in row]
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
    pdf.setTitle(deck["title"]+" 开题展示 "+deck["version"])
    for idx,slide in enumerate(deck["slides"]):
        if idx == 0:
            pdf.setFillColor(colors.HexColor(PALE)); pdf.rect(65,720-330-90,1150,90,fill=1,stroke=0)
        else:
            slide_text(pdf,dict(type="text",text=slide["title"],x=60,y=27,w=1040,h=58,size=40,font="title",color=BLUE))
            slide_text(pdf,dict(type="text",text=slide["subtitle"],x=65,y=100,w=1100,h=40,size=23,color=MUTED))
            pdf.setStrokeColor(colors.HexColor(BLUE));pdf.setLineWidth(3)
            pdf.line(60,720-90,1220,720-90)
            pdf.drawImage(str(ROOT/'assets/brand/char_blue.png'),1100,720-30-39,width=115,height=39,
                          preserveAspectRatio=True,mask='auto')
        draw_items(pdf, slide['items'])
        slide_text(pdf,dict(text=f"第11组 · 开题展示 {deck['version']}",x=65,y=682,w=1040,h=25,size=17,color=MUTED))
        slide_text(pdf,dict(text=f"{idx+1:02d} / {len(deck['slides']):02d}",x=1135,y=682,w=100,h=25,size=17,color=MUTED))
        pdf.showPage()
    pdf.save()
    (PROPOSAL / 'ppt/第11组_开题展示.pdf').write_bytes(buf.getvalue())
    print(f"Slide PDF: {len(deck['slides'])} pages, selectable text")


def draw_chart(pdf, item):
    """Same literal fractions as native PPTX; axes are explicitly percentages."""
    data=json.loads((ROOT/item['data_path']).read_text())['chart']
    x,y,w,h=item['x'],item['y'],item['w'],item['h']
    left=x+66; right=x+w-24; top=y+32; bottom=y+h-55
    yy=lambda v: top+(.2-v)/.6*(bottom-top)
    for n in range(-4,3):
        value=n/10; py=yy(value)
        pdf.setStrokeColor(colors.HexColor('#D9E1EB'));pdf.setLineWidth(.8)
        pdf.line(left,720-py,right,720-py)
        slide_text(pdf,dict(text=f'{n*10}%',x=x,y=py-12,w=60,h=28,size=19,color=MUTED))
    for i,(label,value) in enumerate(zip(data['categories'],data['values'])):
        cx=left+(right-left)*(i+.5)/2; zero=yy(0); end=yy(value)
        pdf.setFillColor(colors.HexColor(BLUE if value>=0 else '#AD5D23'))
        pdf.rect(cx-62,720-max(zero,end),124,abs(end-zero),fill=1,stroke=0)
        slide_text(pdf,dict(text=f'{value:+.1%}',x=cx-90,y=end-34 if value>=0 else end+4,w=180,h=34,size=26,color=INK,bold=True))
        slide_text(pdf,dict(text=label,x=cx-110,y=bottom+17,w=220,h=34,size=23,color=INK))


def draw_items(pdf, items):
    for item in items:
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
        elif item['type'] == 'box':
            pdf.setFillColor(colors.HexColor(item['fill']))
            pdf.rect(item['x'],720-item['y']-item['h'],item['w'],item['h'],fill=1,stroke=0)
        elif item['type'] == 'chart':
            draw_chart(pdf,item)
        else:
            raise ValueError(f"Unknown slide item: {item['type']}")


def build_figures():
    """Technical report figures reuse slide source; no separate copied numbers."""
    import pypdfium2 as pdfium
    deck=json.loads((PROPOSAL/'ppt/slides.json').read_text())
    figures=[('pv-example',(60,155,1150,450)),('harness-plan',(60,170,1150,440)),('semester-timeline',(60,170,1150,450)),('core-schedule',(60,195,1150,410))]
    folder=ROOT/'assets/opening'
    for name,(x,y,w,h) in figures:
        slide=next(row for row in deck['slides'] if row.get('id')==name)
        buf=io.BytesIO();pdf=canvas.Canvas(buf,pagesize=(1280,720))
        draw_items(pdf,slide['items']);pdf.showPage();pdf.save()
        doc=pdfium.PdfDocument(buf.getvalue())
        # PDFium crop is measured from left, bottom, right, top in PDF points.
        bitmap=doc[0].render(scale=2,crop=(x,720-y-h,1280-x-w,y))
        bitmap.to_pil().save(folder/f'{name}.png')
        bitmap.close();doc.close()


if __name__ == "__main__":
    register_fonts()
    build_figures()
    build_report()
    build_slide_pdf()
