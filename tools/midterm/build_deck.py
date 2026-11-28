"""Rebuild the editable midterm deck, PDF, and matching speaker materials."""
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from build_deck import build as build_pptx
from build_pdfs import ROOT, build_slide_pdf, register_fonts
from slide_diagrams import svg_diagram

STAGE = ROOT / "presentations/02-midterm"
PPT = STAGE / "ppt"


def material_links(slide, directory):
    links = []
    for source in slide["sources"]:
        if source.startswith("https://"):
            label = ("PR #" + source.rsplit("/", 1)[1] if "/pull/" in source
                     else source.rsplit("/", 1)[1].split("#", 1)[0])
            links.append(f"[{label}]({source})")
        else:
            filename = ROOT / source
            if not filename.is_file():
                raise FileNotFoundError(filename)
            link = Path(os.path.relpath(filename, directory)).as_posix()
            links.append(f"[{filename.name}]({link})")
    return " · ".join(links)


def time_plan(deck):
    total = sum(slide["seconds"] for slide in deck["slides"])
    minutes, seconds = divmod(total, 60)
    return f"{len(deck['slides'])} 页共 {minutes} 分 {seconds} 秒，含第 3 页现场演示 90 秒。另留 {420-total} 秒用于切屏和停顿。"


def render_script(deck, target, introduction):
    text = [f"# {introduction}", "", "**展示人：程文博**。" + time_plan(deck)]
    if target.parent.name == "briefing":
        text += ["", "彩排时打开本机工作台首页，准备一个可写入的下载目录。先用两份固定资料演示生成、核对、导出，回到第 4 页解释框架。第 6 页走读实际运行路径，第 7 页核对真实 GLM 试验样张。"]
    elapsed = 0
    for idx, slide in enumerate(deck["slides"], 1):
        start, elapsed = elapsed, elapsed + slide["seconds"]
        interval = f"{start//60}:{start%60:02d}–{elapsed//60}:{elapsed%60:02d}"
        text += ["", f"## {idx}　{slide['title']}", "", f"{interval}　｜　{slide['seconds']} 秒", "", slide["speech"]]
        if slide["cue"]:
            text += ["", f"**操作提示**　{slide['cue']}"]
        if slide["sources"]:
            text += ["", "**核对材料**　" + material_links(slide, target.parent)]
    target.write_text("\n".join(text) + "\n", encoding="utf-8")


def render_outline(deck):
    lines = ["# 第 11 组中期展示框架", "", "程文博主讲，使用开题的浙大蓝白版式。" + time_plan(deck), "",
             "| 页 | 内容 | 用时 | 展示重点 |", "| ---: | --- | ---: | --- |"]
    for i, slide in enumerate(deck["slides"], 1):
        purpose = slide["summary"]
        lines.append(f"| {i} | {slide['title']} | {slide['seconds']} 秒 | {purpose} |")
    lines.extend(["", "老师提出的范围、框架选型、智能体分工分别见第 2、4–6、9 页。第 3 页可现场操作；第 7、8 页分别以删源样张、联网成稿及错误句检验交付行为。",
        "", "[DeepSeek Harness 工具往返图](media/deepseek-harness-mcp.svg) · [Pi CLI 事件图](media/pi-cli-events.svg) · [项目双路径图](media/report-runtime.svg)", "", "[逐页讲稿](讲稿.md) · [组内彩排稿](../briefing/中期汇报完整讲稿.md) · [设计报告](../report/report.md) · [运行材料](../evidence/README.md)"])
    (PPT / "中期PPT框架.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build():
    source = PPT / "slides.json"
    deck = json.loads(source.read_text(encoding="utf-8"))
    slides = deck["slides"]
    if len(slides) != deck["formal_slides"] or not 0 < sum(s["seconds"] for s in slides) <= 420:
        raise ValueError("请核对正式页数及各页用时；演示与讲述总共不超过 7 分钟。")
    if slides[2]["id"] != "demo" or slides[2]["seconds"] != 90:
        raise ValueError("第 3 页的现场演示应为 90 秒。")
    if any(s["speech"] not in s["notes"] for s in slides):
        raise ValueError("幻灯片备注与现场讲稿应一致。")
    for slide in slides:
        for item in slide["items"]:
            if item["type"] == "diagram":
                svg_diagram(item, PPT / "media" / (item["name"] + ".svg"))
    register_fonts()
    build_slide_pdf(source, PPT / f"第11组_中期展示_{deck['version']}.pdf", "中期展示")
    build_pptx(midterm=True)
    render_script(deck, PPT / "讲稿.md", "第 11 组中期展示逐页讲稿")
    render_script(deck, STAGE / "briefing/中期汇报完整讲稿.md", "第 11 组中期汇报完整讲稿")
    render_outline(deck)


if __name__ == "__main__":
    build()
