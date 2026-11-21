"""Render midterm PDFs with the opening-stage fonts, margins and slide master."""
from pathlib import Path
import io
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_pdfs import ROOT, build_slide_pdf, draw_items, register_fonts, render_report
from reportlab.pdfgen import canvas
import pypdfium2 as pdfium


def build():
    register_fonts()
    directory = ROOT / "presentations/02-midterm"
    slide_source = directory / "ppt/slides.json"
    deck = json.loads(slide_source.read_text(encoding="utf-8"))
    version = deck["version"]

    flow = next(slide for slide in deck["slides"] if slide.get("id") == "chapter-flow")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(1280, 720))
    draw_items(pdf, [item for item in flow["items"] if item["type"] == "flow"])
    pdf.showPage()
    pdf.save()
    document = pdfium.PdfDocument(buffer.getvalue())
    bitmap = document[0].render(scale=2, crop=(60, 411, 60, 188))
    bitmap.to_pil().save(directory / "report/chapter-flow.png")
    bitmap.close()
    document.close()

    render_report(directory / "report/report.md", directory / f"report/第11组_系统设计报告_{version}.pdf",
                  "系统设计报告", 15, 10000, "# 参考资料与版本记录")
    build_slide_pdf(slide_source, directory / f"ppt/第11组_中期展示_{version}.pdf", "中期展示")

    speech = ["# 第11组中期展示讲稿", "", "共7分钟，真实联调结果见中期验证记录。"]
    for index, slide in enumerate(deck["slides"], 1):
        speech.extend(["", f"## 第{index}页　{slide['title']}（约{slide['seconds']}秒）", "", slide["speech"]])
        if slide["cue"]:
            speech.extend(["", "操作提示：" + slide["cue"]])
    (directory / "ppt/讲稿.md").write_text("\n".join(speech) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
