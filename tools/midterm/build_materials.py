"""Render midterm PDFs with the opening-stage fonts, margins and slide master."""
from pathlib import Path
from contextlib import closing
import io
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_pdfs import ROOT, build_slide_pdf, draw_items, register_fonts, render_report
from reportlab.pdfgen import canvas
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


def build():
    register_fonts()
    directory = ROOT / "presentations/02-midterm"
    slide_source = directory / "ppt/slides.json"
    deck = json.loads(slide_source.read_text(encoding="utf-8"))
    version = deck["version"]
    total = sum(slide["seconds"] for slide in deck["slides"])
    if not 0 < total <= 420:
        raise ValueError("中期讲稿须控制在7分钟以内")

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
    render_glm_excerpts(directory / "evidence")

    render_report(directory / "report/report.md", directory / f"report/第11组_系统设计报告_{version}.pdf",
                  "系统设计报告", 15, 10000, "# 参考资料与版本记录")
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
    build()
