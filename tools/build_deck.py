#!/usr/bin/env python3
"""Build the opening PPTX from presentations/01-opening/ppt/slides.json.

A portable alternative to build_slides.mjs (which needs Codex's private
@oai/artifact-tool runtime). This script uses only python-pptx and renders
the same layout: 1280x720 canvas, Microsoft YaHei typography,
blue accent #003F88, pale table header #ECF3FA.

Usage:
    py -3.11 tools/build_deck.py
Writes:
    presentations/01-opening/ppt/<title>_v<version>.pptx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Pt

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "presentations" / "01-opening" / "ppt" / "slides.json"

BLUE = RGBColor(0x00, 0x3F, 0x88)
INK = RGBColor(0x23, 0x30, 0x42)
MUTED = RGBColor(0x60, 0x72, 0x8C)
PALE = RGBColor(0xEC, 0xF3, 0xFA)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRID = RGBColor(0xD9, 0xE1, 0xEB)

TITLE_FONT = "Microsoft YaHei"
BODY_FONT = "Microsoft YaHei"

SIZE_SCALE = 0.92

PX = 9525


def px(v: float) -> Emu:
    return Emu(int(v * PX))


def scaled(size: float) -> float:
    return round(size * SIZE_SCALE, 1)


def set_run(run, *, size, bold, color, font):
    run.font.size = Pt(scaled(size))
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font


def add_text(slide, item):
    box = slide.shapes.add_textbox(px(item["x"]), px(item["y"]), px(item["w"]), px(item["h"]))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    lines = item["text"].split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = line
        set_run(
            run,
            size=item.get("size", 20),
            bold=item.get("bold", False),
            color=RGBColor.from_string(item.get("color", "233042").lstrip("#")),
            font=TITLE_FONT if item.get("font") == "title" else BODY_FONT,
        )
    return box


def add_rect(slide, x, y, w, h, fill, line=None, line_w=0):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, px(x), px(y), px(w), px(h))
    shp.shadow.inherit = False
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w)
    return shp


def add_image(slide, item):
    p = ROOT / item["path"]
    slide.shapes.add_picture(str(p), px(item["x"]), px(item["y"]), px(item["w"]), px(item["h"]))


def add_table(slide, item):
    rows, cols = len(item["rows"]), len(item["rows"][0])
    gfx = slide.shapes.add_table(rows, cols, px(item["x"]), px(item["y"]), px(item["w"]), px(item["h"]))
    tbl = gfx.table
    widths = item.get("widths")
    if widths:
        total = sum(widths)
        for i, w in enumerate(widths):
            tbl.columns[i].width = Emu(int(item["w"] * PX * w / total))
    row_h = item["h"] / rows
    for r in range(rows):
        tbl.rows[r].height = px(row_h)
        for c in range(cols):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Emu(95250)
            cell.margin_top = cell.margin_bottom = Emu(57150)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = PALE if r == 0 else WHITE
            tf = cell.text_frame
            tf.word_wrap = True
            tf.text = ""
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            run = p.add_run()
            run.text = item["rows"][r][c]
            set_run(
                run,
                size=item.get("size", 20),
                bold=(r == 0),
                color=BLUE if r == 0 else INK,
                font=BODY_FONT,
            )
    return tbl


def add_flow(slide, item):
    for x1, y1, x2, y2 in item["edges"]:
        left = min(x1, x2)
        top = min(y1, y2)
        w = max(1.5, abs(x2 - x1))
        h = max(1.5, abs(y2 - y1))
        add_rect(slide, left, top, w, h, BLUE)
    for title, body, x, y, w, h in item["nodes"]:
        add_rect(slide, x, y, w, h, PALE, BLUE, 1)
        tbox = slide.shapes.add_textbox(px(x + 15), px(y + 13), px(w - 30), px(40))
        tf = tbox.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = title
        set_run(run, size=30, bold=True, color=BLUE, font=BODY_FONT)
        bbox = slide.shapes.add_textbox(px(x + 15), px(y + 63), px(w - 30), px(35))
        tf = bbox.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = body
        set_run(run, size=23, bold=False, color=INK, font=BODY_FONT)


def build():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    prs = Presentation()
    prs.slide_width = px(1280)
    prs.slide_height = px(720)
    blank = prs.slide_layouts[6]

    total = len(spec["slides"])
    for idx, s in enumerate(spec["slides"]):
        slide = prs.slides.add_slide(blank)
        add_rect(slide, 0, 0, 1280, 720, WHITE)

        if idx == 0:
            add_rect(slide, 65, 330, 1150, 90, PALE)
        else:
            t = slide.shapes.add_textbox(px(60), px(27), px(1040), px(58))
            tf = t.text_frame
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = s["title"]
            set_run(run, size=40, bold=True, color=BLUE, font=TITLE_FONT)
            add_rect(slide, 60, 89, 1160, 3, BLUE)
            sub = slide.shapes.add_textbox(px(65), px(100), px(1100), px(40))
            tf = sub.text_frame
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = s["subtitle"]
            set_run(run, size=23, bold=False, color=MUTED, font=BODY_FONT)
            add_image(slide, {"path": "assets/brand/char_blue.png", "x": 1100, "y": 30, "w": 115, "h": 39})

        for it in s["items"]:
            t = it["type"]
            if t == "text":
                add_text(slide, it)
            elif t == "image":
                add_image(slide, it)
            elif t == "table":
                add_table(slide, it)
            elif t == "flow":
                add_flow(slide, it)
            else:
                raise ValueError(f"unknown item type {t}")

        foot = slide.shapes.add_textbox(px(65), px(682), px(1040), px(25))
        tf = foot.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = f"开题初稿 {spec['version']} / 计划与实际分开记录"
        set_run(run, size=17, bold=False, color=MUTED, font=BODY_FONT)

        pg = slide.shapes.add_textbox(px(1135), px(682), px(100), px(25))
        tf = pg.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT
        run = p.add_run()
        run.text = f"{idx + 1:02d} / {total}"
        set_run(run, size=17, bold=False, color=MUTED, font=BODY_FONT)

        notes = slide.notes_slide.notes_text_frame
        notes.text = s.get("notes", "")

    out = ROOT / "presentations" / "01-opening" / "ppt" / f"第11组_开题展示_{spec['version']}.pptx"
    prs.save(out)
    print(f"wrote {out}  ({total} slides)")


if __name__ == "__main__":
    build()
