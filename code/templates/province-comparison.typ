// Reuse the solar-study typeface and colours. These two report tables have known columns.
#let teal = rgb("#195959")
#set document(title: "光伏分省并网比较")
#set page(paper: "a4", margin: (x: 23mm, top: 22mm, bottom: 21mm),
  header: align(right, text(size: 9pt, fill: rgb("#596a68"))[光伏研究室　/　产业研究]),
  numbering: "1")
#set text(font: ("LXGW WenKai", "PingFang SC", "Noto Sans CJK SC"), lang: "zh", size: 11pt)
#set par(leading: 0.65em, spacing: 4pt)
#show heading.where(level: 1): it => block(sticky: true, above: 11pt, below: 5pt,
  text(size: 15pt, fill: teal, weight: "bold", it.body))

#for b in json("brief.json") {
  if b.kind == "title" {
    block(above: 5mm, below: 5mm, text(size: 23pt, fill: teal, weight: "bold", b.text))
    line(length: 100%, stroke: 1.2pt + teal)
    v(5pt)
  } else if b.kind == "heading" {
    v(6pt, weak: true)
    heading(level: 1, b.text)
  } else if b.kind == "caption" {
    block(sticky: true, above: 3pt, below: 3pt, text(size: 9pt, b.text))
  } else if b.kind == "table" {
    let missing = b.rows.first().len() == 4
    let widths = if missing { (1fr, 1fr, 1fr, 4.5fr) } else { (1fr, 1fr, 1fr, 1fr, 1fr, 1.2fr) }
    table(columns: widths, inset: (x: 5pt, y: 5.5pt),
      align: (x, y) => if (missing and x in (0, 3)) or (not missing and x == 1) { left } else { right },
      stroke: (x: none, y: 0.4pt + rgb("#c4d4d0")),
      fill: (x, y) => if y == 0 { rgb("#e6f1ed") },
      table.header(repeat: true, ..b.rows.first().map(c => text(size: 10pt, weight: "bold", c))),
      ..b.rows.slice(1).flatten().map(c => text(size: 10pt, c)))
  } else if b.kind == "link" {
    block(above: 2pt, below: 2pt, text(size: 10pt, fill: teal, link(b.url, b.text)))
    v(2pt, weak: true)
  } else {
    par(b.text)
    v(4pt, weak: true)
  }
}
