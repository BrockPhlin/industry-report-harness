"""Render midterm PDFs with the opening-stage fonts, margins and slide master."""
from pathlib import Path
from contextlib import closing
import io
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_pdfs import ROOT, build_slide_pdf, register_fonts, render_report
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import pypdfium2 as pdfium


def render_glm_excerpts(evidence):
    # Crop the "发电新增装机" heading and its first data line from the two
    # recorded E7 samples. Coordinates are PDF points measured from the top.
    excerpts = [
        ("光伏简报_GLM完整资料.pdf", "glm-full-excerpt.png", 439, 490),
        ("光伏简报_GLM缺装机资料.pdf", "glm-missing-excerpt.png", 389, 440),
    ]
    for source, output, top, bottom in excerpts:
        with pdfium.PdfDocument(evidence / source) as document:
            with closing(document[0]) as page:
                width, height = page.get_size()
                with closing(page.render(scale=3, crop=(64, height - bottom, width - 394, top))) as bitmap:
                    bitmap.to_pil().save(evidence / output)


def render_report_figures(directory):
    """Draw report diagrams from the implemented modules and section graph."""
    def box(pdf, x, y, width, title, detail, height=90):
        pdf.setFillColor(colors.HexColor("#ECF3FA"))
        pdf.setStrokeColor(colors.HexColor("#003F88"))
        pdf.setLineWidth(1.5)
        pdf.roundRect(x, y, width, height, 5, fill=1, stroke=1)
        pdf.setFillColor(colors.HexColor("#003F88"))
        pdf.setFont("Strong", 28)
        pdf.drawCentredString(x + width / 2, y + height - 36, title)
        pdf.setFillColor(colors.HexColor("#233042"))
        pdf.setFont("Body", 24)
        pdf.drawCentredString(x + width / 2, y + 23, detail)

    def arrow(pdf, points):
        pdf.setStrokeColor(colors.HexColor("#60728C"))
        pdf.setFillColor(colors.HexColor("#60728C"))
        pdf.setLineWidth(2)
        path = pdf.beginPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        pdf.drawPath(path)
        x, y = points[-1]
        dx, dy = x - points[-2][0], y - points[-2][1]
        length = (dx * dx + dy * dy) ** .5
        ux, uy = dx / length, dy / length
        tip = pdf.beginPath()
        tip.moveTo(x, y)
        tip.lineTo(x - 10 * ux + 5 * uy, y - 10 * uy - 5 * ux)
        tip.lineTo(x - 10 * ux - 5 * uy, y - 10 * uy + 5 * ux)
        tip.close()
        pdf.drawPath(tip, fill=1, stroke=0)

    def save(buffer, filename):
        with pdfium.PdfDocument(buffer.getvalue()) as document:
            with closing(document[0]) as page:
                with closing(page.render(scale=2)) as bitmap:
                    bitmap.to_pil().save(directory / "report" / filename)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(1200, 300))
    box(pdf, 15, 185, 270, "JSON 输入", "章节模板 / 事实与来源")
    box(pdf, 330, 185, 360, "Python CLI + 章内编排", "pv_brief / pv_agent")
    box(pdf, 735, 185, 450, "人工审阅 → Typst 导出", "Markdown / PDF / 确认收据")
    box(pdf, 15, 15, 350, "只读证据检索", "pv_evidence")
    box(pdf, 425, 15, 350, "GLM 调用适配", "pv_model")
    box(pdf, 835, 15, 350, "检查点保存与恢复", "pv_checkpoint")
    arrow(pdf, [(285, 230), (330, 230)])
    arrow(pdf, [(690, 230), (735, 230)])
    for target in (190, 600, 1010):
        arrow(pdf, [(510, 185), (510, 145), (target, 145), (target, 105)])
    pdf.setFont("Body", 21)
    pdf.setFillColor(colors.HexColor("#60728C"))
    pdf.drawString(20, 150, "本地输入")
    pdf.drawString(850, 150, "生成成功后审阅")
    pdf.showPage()
    pdf.save()
    save(buffer, "system-architecture.png")

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(1200, 270))
    box(pdf, 15, 165, 260, "模型初查", "initial + 资料工具")
    box(pdf, 325, 165, 250, "比对必查指标", "required 与 hits")
    box(pdf, 865, 165, 320, "模型写作与校验", "draft → 保存完整章节")
    box(pdf, 575, 20, 260, "缺项补查一次", "supplement")
    arrow(pdf, [(275, 210), (325, 210)])
    arrow(pdf, [(575, 210), (865, 210)])
    arrow(pdf, [(450, 165), (450, 65), (575, 65)])
    arrow(pdf, [(835, 65), (1025, 65), (1025, 165)])
    pdf.setFont("Body", 25)
    pdf.setFillColor(colors.HexColor("#60728C"))
    pdf.drawCentredString(720, 226, "指标齐全")
    pdf.drawString(465, 95, "有缺项")
    pdf.showPage()
    pdf.save()
    save(buffer, "chapter-flow.png")


def build_report(directory):
    render_report_figures(directory)
    source = directory / "report/report.md"
    version = re.search(r"\*\*版本\*\*：(v\d+(?:\.\d+)+)", source.read_text(encoding="utf-8"))[1]
    render_report(source, directory / f"report/第11组_系统设计报告_{version}.pdf",
                  "系统设计报告", 15, 10000, "# 参考资料与版本记录",
                  framed_figures=True, show_character_count=False)


def build():
    register_fonts()
    directory = ROOT / "presentations/02-midterm"
    slide_source = directory / "ppt/slides.json"
    deck = json.loads(slide_source.read_text(encoding="utf-8"))
    version = deck["version"]
    total = sum(slide["seconds"] for slide in deck["slides"])
    if not 0 < total <= 420:
        raise ValueError("中期讲稿须控制在7分钟以内")

    render_glm_excerpts(directory / "evidence")

    build_report(directory)
    build_slide_pdf(slide_source, directory / f"ppt/第11组_中期展示_{version}.pdf", "中期展示")

    minutes, seconds = divmod(total, 60)
    speech = ["# 第11组中期展示讲稿", "",
              f"计划讲述{minutes}分{seconds}秒，另留{420-total}秒给翻页和停顿。"
              "演示样张已放入 PPT。操作提示留给讲述人。"]
    for index, slide in enumerate(deck["slides"], 1):
        speech.extend(["", f"## 第{index}页　{slide['title']}（约{slide['seconds']}秒）", "", slide["speech"]])
        if slide["cue"]:
            speech.extend(["", "操作提示：" + slide["cue"]])
    (directory / "ppt/讲稿.md").write_text("\n".join(speech) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true", help="只生成系统设计报告 PDF")
    if parser.parse_args().report_only:
        register_fonts()
        build_report(ROOT / "presentations/02-midterm")
    else:
        build()
