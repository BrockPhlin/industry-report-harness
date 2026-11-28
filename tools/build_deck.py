#!/usr/bin/env python3
"""Build a deck PPTX from a presentations/*/ppt/slides.json source.

A portable alternative to build_slides.mjs (which needs Codex's private
@oai/artifact-tool runtime). This script uses only python-pptx and renders
an editable 1280x720 canvas with the opening master’s fonts for the midterm,
blue accent #003F88, pale table header #ECF3FA.

Usage:
    py -3.11 tools/build_deck.py              # opening deck
    py -3.11 tools/build_deck.py --midterm    # midterm deck
Writes:
    presentations/<stage>/ppt/第11组_<label>_<version>.pptx
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NamedTuple

from PIL import Image

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Pt
from pptx.oxml.xmlchemy import OxmlElement

ROOT = Path(__file__).resolve().parent.parent

BLUE = RGBColor(0x00, 0x3F, 0x88)
INK = RGBColor(0x23, 0x30, 0x42)
MUTED = RGBColor(0x60, 0x72, 0x8C)
PALE = RGBColor(0xEC, 0xF3, 0xFA)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRID = RGBColor(0xD9, 0xE1, 0xEB)

class Theme(NamedTuple):
    title: str
    body: str
    points_per_unit: float


LEGACY = Theme("Microsoft YaHei", "Microsoft YaHei", 0.92)
# The opening master uses pixel units on a 1280 px canvas at 96 dpi.
OPENING = Theme("Smiley Sans Oblique", "LXGW WenKai", 72 / 96)

PX = 9525


def px(v: float) -> Emu:
    return Emu(int(v * PX))


def hex_color(value: str) -> RGBColor:
    return RGBColor.from_string(value.lstrip("#"))


def set_run(run, *, size, bold, color, theme, heading=False):
    font = theme.title if heading else theme.body
    precision = 2 if theme is OPENING else 1
    run.font.size = Pt(round(size * theme.points_per_unit, precision))
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    if theme is OPENING:
        # PowerPoint chooses the East Asian face independently of the Latin run.
        properties = run._r.get_or_add_rPr()
        east_asian = OxmlElement("a:ea")
        east_asian.set("typeface", font)
        properties.append(east_asian)


def add_text(slide, item, theme):
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
        if item.get("href"):
            run.hyperlink.address = item["href"]
        set_run(
            run,
            size=item.get("size", 20),
            bold=item.get("bold", False),
            color=RGBColor.from_string(item.get("color", "233042").lstrip("#")),
            theme=theme, heading=item.get("font") == "title",
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


def add_box(slide, item):
    return add_rect(
        slide,
        item["x"],
        item["y"],
        item["w"],
        item["h"],
        hex_color(item["fill"]) if item.get("fill") else None,
        hex_color(item["line"]) if item.get("line") else None,
        item.get("line_w", 1),
    )


def add_image(slide, item, contain=False):
    p = ROOT / item["path"]
    x, y, width, height = (item[key] for key in ("x", "y", "w", "h"))
    if contain:
        with Image.open(p) as image:
            scale = min(width / image.width, height / image.height)
            fitted_w, fitted_h = image.width * scale, image.height * scale
        x, y = x + (width - fitted_w) / 2, y + (height - fitted_h) / 2
        width, height = fitted_w, fitted_h
    slide.shapes.add_picture(str(p), px(x), px(y), px(width), px(height))


def add_table(slide, item, theme):
    rows, cols = len(item["rows"]), len(item["rows"][0])
    gfx = slide.shapes.add_table(rows, cols, px(item["x"]), px(item["y"]), px(item["w"]), px(item["h"]))
    tbl = gfx.table
    widths = item.get("widths")
    if widths:
        total = sum(widths)
        for i, w in enumerate(widths):
            tbl.columns[i].width = Emu(int(item["w"] * PX * w / total))
    row_h = item["h"] / rows
    pad = item.get("pad", 6)
    for r in range(rows):
        tbl.rows[r].height = px(row_h)
        for c in range(cols):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Emu(95250)
            cell.margin_top = cell.margin_bottom = Emu(int(pad * PX))
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = PALE if r == 0 else WHITE
            if theme is OPENING:
                props = cell._tc.get_or_add_tcPr()
                for side in ("lnL", "lnR", "lnT", "lnB"):
                    line = OxmlElement("a:" + side)
                    line.set("w", str(int(Pt(.45))))
                    fill = OxmlElement("a:solidFill")
                    color = OxmlElement("a:srgbClr")
                    color.set("val", "D9E1EB")
                    fill.append(color)
                    line.append(fill)
                    props.insert(0, line)
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
                theme=theme,
            )
    return tbl


def add_flow(slide, item, theme):
    for x1, y1, x2, y2 in item["edges"]:
        left = min(x1, x2)
        top = min(y1, y2)
        w = max(1.5, abs(x2 - x1))
        h = max(1.5, abs(y2 - y1))
        add_rect(slide, left, top, w, h, BLUE)
    title_size = item.get("title_size", 30)
    body_size = item.get("body_size", 23)
    for title, body, x, y, w, h in item["nodes"]:
        add_rect(slide, x, y, w, h, PALE, BLUE, 1)
        tbox = slide.shapes.add_textbox(px(x + 15), px(y + 12), px(w - 30), px(38))
        tf = tbox.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = title
        set_run(run, size=title_size, bold=True, color=BLUE, theme=theme)
        bbox = slide.shapes.add_textbox(px(x + 15), px(y + 58), px(w - 30), px(h - 64))
        tf = bbox.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        for i, line in enumerate(body.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            run = p.add_run()
            run.text = line
            set_run(run, size=body_size, bold=False, color=INK, theme=theme)


def build(midterm: bool = False):
    theme = OPENING if midterm else LEGACY
    stage_dir = "02-midterm" if midterm else "01-opening"
    label = "中期展示" if midterm else "开题展示"
    deck_dir = ROOT / "presentations" / stage_dir / "ppt"
    spec = json.loads((deck_dir / "slides.json").read_text(encoding="utf-8"))
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
            set_run(run, size=40, bold=not midterm, color=BLUE, theme=theme, heading=True)
            add_rect(slide, 60, 89, 1160, 3, BLUE)
            section = s.get("section")
            sub_x = 65
            if section and not midterm:
                add_rect(slide, 65, 98, 165, 36, PALE)
                add_text(slide, {"text": section, "x": 78, "y": 104, "w": 140, "h": 26,
                                 "size": 18, "bold": True, "color": "#003F88"}, theme)
                sub_x = 247
            sub = slide.shapes.add_textbox(px(sub_x), px(100), px(1260 - sub_x), px(40))
            tf = sub.text_frame
            tf.word_wrap = True
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = s["subtitle"]
            set_run(run, size=23, bold=False, color=MUTED, theme=theme)
            add_image(slide, {"path": "assets/brand/char_blue.png", "x": 1100, "y": 30, "w": 115, "h": 39})

        for it in s["items"]:
            t = it["type"]
            if t == "text":
                add_text(slide, it, theme)
            elif t == "image":
                add_image(slide, it, contain=midterm)
            elif t == "table":
                add_table(slide, it, theme)
            elif t == "flow":
                add_flow(slide, it, theme)
            elif t == "box":
                add_box(slide, it)
            else:
                raise ValueError(f"unknown item type {t}")

        foot = slide.shapes.add_textbox(px(65), px(682), px(1040), px(25))
        tf = foot.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        run = p.add_run()
        if midterm:
            run.text = f"第11组 · 中期展示 {spec['version']}"
        else:
            run.text = f"开题初稿 {spec['version']} / 计划与实际分开记录"
        set_run(run, size=17, bold=False, color=MUTED, theme=theme)

        pg = slide.shapes.add_textbox(px(1135), px(682), px(100), px(25))
        tf = pg.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT if midterm else PP_ALIGN.RIGHT
        run = p.add_run()
        run.text = f"{idx + 1:02d} / {total:02d}" if midterm else f"{idx + 1:02d} / {total}"
        set_run(run, size=17, bold=False, color=MUTED, theme=theme)

        notes = slide.notes_slide.notes_text_frame
        notes.text = s.get("notes", "")

    out = deck_dir / f"第11组_{label}_{spec['version']}.pptx"
    prs.save(out)
    print(f"wrote {out}  ({total} slides)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--midterm", action="store_true", help="build the midterm deck")
    args = parser.parse_args()
    build(midterm=args.midterm)
