"""Rebuild the editable midterm deck, PDF, and matching speaker materials."""
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from build_deck import build as build_pptx
from build_pdfs import ROOT, build_slide_pdf, register_fonts

STAGE = ROOT / "presentations/02-midterm"
PPT = STAGE / "ppt"


def material_links(slide, directory):
    links = []
    for source in slide["sources"]:
        if source.startswith("https://"):
            label = "PR #" + source.rsplit("/", 1)[1]
            links.append(f"[{label}]({source})")
        else:
            filename = ROOT / source
            if not filename.is_file():
                raise FileNotFoundError(filename)
            link = Path(os.path.relpath(filename, directory)).as_posix()
            links.append(f"[{filename.name}]({link})")
    return " · ".join(links)


def render_script(deck, target, introduction):
    text = [f"# {introduction}", "", "**展示人：程文博**。九页共 6 分 35 秒，其中第 3、4 页连续演示 90 秒。课程展示时限 7 分钟，余下 25 秒用于切屏和停顿。"]
    if target.parent.name == "briefing":
        text += ["", "彩排时打开本机工作台首页，准备一个可写入的下载目录。先用两份固定资料演示生成、核对、导出，再从第 5 页回到幻灯片。真实 GLM 试验的证据在第 6 页。"]
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
    synopsis = [
        "两句提问引出来源和缺项，程文博独讲。",
        "对比组件产量与电站新增装机的统计对象，说明怎样限定第一类报告。",
        "对照一次联网自定义研究，从本机首页生成离线固定简报。",
        "从装机栏点进来源，核对位置，确认后下载 PDF。",
        "对照 DeepSeek Harness、Pi CLI 的工具接法，再说明生产简报怎样按章取证。",
        "真实 GLM 样张的装机栏。相同模板、两种输入，直接看区别。",
        "从一条验收问题追到四份 PR，说明六名组员怎样交接。",
        "用错省例子解释 12 条定向评测，指出何时需要人工判断。",
        "三组负责人、三个拟定日期，拿到同题对照后再判断写作参考的收益。",
    ]
    lines = ["# 第 11 组中期展示框架", "", "正式展示 9 页，程文博主讲，使用开题的浙大蓝白版式。讲述与操作共 6 分 35 秒。", "",
             "| 页 | 内容 | 用时 | 展示重点 |", "| ---: | --- | ---: | --- |"]
    for i, (slide, purpose) in enumerate(zip(deck["slides"], synopsis), 1):
        lines.append(f"| {i} | {slide['title']} | {slide['seconds']} 秒 | {purpose} |")
    lines.extend(["", "老师提出的框架选型、主题范围和智能体分工分别在第 5、2、7 页回答。第 3、4 页的系统操作和第 6 页两份 PDF 是这三个决定的直接例子。",
        "", "[逐页讲稿](讲稿.md) · [组内彩排稿](../briefing/中期汇报完整讲稿.md) · [设计报告](../report/report.md) · [运行材料](../evidence/README.md)"])
    (PPT / "中期PPT框架.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build():
    source = PPT / "slides.json"
    deck = json.loads(source.read_text(encoding="utf-8"))
    slides = deck["slides"]
    if len(slides) != 9 or sum(s["seconds"] for s in slides) != 395:
        raise ValueError("本次正式稿共有九页、395 秒。")
    if sum(s["seconds"] for s in slides[2:4]) != 90:
        raise ValueError("第 3、4 页的现场演示应为 90 秒。")
    if any(s["speech"] not in s["notes"] for s in slides):
        raise ValueError("幻灯片备注与现场讲稿应一致。")
    register_fonts()
    build_slide_pdf(source, PPT / f"第11组_中期展示_{deck['version']}.pdf", "中期展示")
    build_pptx(midterm=True)
    render_script(deck, PPT / "讲稿.md", "第 11 组中期展示逐页讲稿")
    render_script(deck, STAGE / "briefing/中期汇报完整讲稿.md", "第 11 组中期汇报完整讲稿")
    render_outline(deck)


if __name__ == "__main__":
    build()
