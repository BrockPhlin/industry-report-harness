"""Expand native slide diagram nodes and export their reusable SVG artwork."""
from pathlib import Path
from xml.etree import ElementTree as ET

BLUE = "#003F88"
INK = "#233042"
MUTED = "#60728C"
PALE = "#ECF3FA"


def node_shapes(node):
    x, y, w, h = (node[k] for k in ("x", "y", "w", "h"))
    title_size = node.get("title_size", 27)
    body_size = node.get("body_size", 23)
    pad = node.get("pad", 12)
    title_height = round(title_size * 1.3)
    yield {"type": "box", "x": x, "y": y, "w": w, "h": h,
           "fill": node.get("fill", PALE), "line": node.get("line", "#B5C8DB"), "line_w": 1}
    yield {"type": "text", "x": x+pad, "y": y+8, "w": w-2*pad, "h": title_height,
           "text": node["heading"], "size": title_size, "color": BLUE, "bold": True}
    yield {"type": "text", "x": x+pad, "y": y+title_height+10, "w": w-2*pad,
           "h": h-title_height-14, "text": node["body"], "size": body_size, "color": INK}


def svg_diagram(diagram, path):
    ns = "http://www.w3.org/2000/svg"
    ET.register_namespace("", ns)
    def element(parent, tag, **attrs):
        return ET.SubElement(parent, f"{{{ns}}}{tag}", {k.replace("_", "-"):str(v) for k,v in attrs.items()})
    x, y, w, h = diagram["view"]
    root = ET.Element(f"{{{ns}}}svg", {"viewBox": f"{x} {y} {w} {h}", "width":str(w), "height":str(h), "role":"img"})
    element(root, "title").text = diagram["caption"]
    mark = element(element(root, "defs"), "marker", id="tip", viewBox="0 0 10 10", refX=9.4,
                   refY=5, markerWidth=6, markerHeight=6, orient="auto-start-reverse")
    element(mark, "path", d="M 0 0 L 10 5 L 0 10 z", fill=BLUE)
    element(root, "rect", x=x, y=y, width=w, height=h, fill="#FFFFFF")
    def paint(item, parent):
        kind = item["type"]
        if kind == "node":
            group = element(parent,"g")
            element(group,"title").text = item["heading"]
            for part in node_shapes(item):
                paint(part, group)
        elif kind == "box":
            element(parent,"rect",x=item["x"],y=item["y"],width=item["w"],height=item["h"],
                    fill=item["fill"],stroke=item.get("line","none"),stroke_width=item.get("line_w",0))
        elif kind == "text":
            size=item["size"]
            text=element(parent,"text",x=item["x"],y=item["y"]+size,font_size=size,
                         font_family="LXGW WenKai, KaiTi, serif",fill=item.get("color",INK),
                         font_weight="bold" if item.get("bold") else "normal")
            for i,line in enumerate(item["text"].splitlines()):
                element(text,"tspan",x=item["x"],dy=0 if i==0 else size*1.24).text=line
        elif kind == "arrow":
            element(parent,"polyline",points=" ".join(f"{a},{b}" for a,b in item["points"]),
                    fill="none",stroke=BLUE,stroke_width=2.5,marker_end="url(#tip)")
        else:
            raise ValueError(f"Unsupported diagram element {kind}")
    for item in diagram["parts"]:
        paint(item, root)
    ET.indent(root)
    Path(path).write_text(ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
