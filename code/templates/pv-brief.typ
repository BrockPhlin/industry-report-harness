#set page(paper: "a4", margin: (x: 24mm, top: 22mm, bottom: 20mm), numbering: "1")
#set text(font: ("LXGW WenKai", "PingFang SC", "Noto Sans CJK SC"), lang: "zh", size: 11pt, fill: rgb("#212e3f"))
#set par(leading: 0.65em)
#let doc = json("brief.json")
#text(fill: rgb("#16635b"), size: 10pt, weight: "bold")[第11组　产业研究简报]
#v(2mm)
#for block in doc {
  if block.kind == "title" {
    text(size: 26pt, fill: rgb("#133f40"), weight: "bold", block.text)
    v(3mm)
    line(length: 100%, stroke: 1.2pt + rgb("#16635b"))
    v(4mm)
  } else if block.kind == "heading" {
    v(4mm)
    text(size: 15pt, fill: rgb("#16635b"), weight: "bold", block.text)
  } else if block.kind == "bullet" {
    par([• #block.text])
  } else if block.kind == "link" {
    par(link(block.url, text(fill: rgb("#145875"), block.text)))
  } else {
    par(block.text)
  }
}
