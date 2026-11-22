#set document(title: "光伏产业研究报告")
#set page(paper: "a4", margin: (x: 23mm, top: 23mm, bottom: 21mm),
  header: align(right, text(size: 9pt, fill: rgb("#596a68"))[光伏研究室　/　产业研究]),
  numbering: "1")
#set text(font: ("LXGW WenKai", "PingFang SC", "Noto Sans CJK SC"), lang: "zh", size: 11pt)
#set par(justify: true, leading: 0.72em, spacing: 0.88em)
#let teal = rgb("#195959")
#show heading.where(level: 1): it => block(above: 12pt, below: 7pt, text(fill: teal, size: 15pt, it.body))
#let blocks = json("brief.json")
#for b in blocks {
  if b.kind == "title" {
    block(above: 14mm, below: 8mm, text(size: 24pt, fill: teal, weight: "bold", b.text))
    line(length: 100%, stroke: 1.2pt + teal)
  } else if b.kind == "contents" {
    outline(title: [目录], indent: 8pt, depth: 1)
    pagebreak()
  } else if b.kind == "heading" {
    heading(level: 1, b.text)
  } else if b.kind == "table" {
    table(columns: b.rows.first().len(), inset: 5pt, align: (x,y) => if x == 0 {left} else {right},
      stroke: (x: none, y: 0.4pt + rgb("#c4d4d0")),
      fill: (x,y) => if y == 0 { rgb("#e6f1ed") },
      table.header(..b.rows.first().map(c => text(weight: "bold", c))),
      ..b.rows.slice(1).flatten().map(c => text(c)))
  } else if b.kind == "chart" {
    block(breakable: false, above: 7pt, below: 7pt, width: 100%)[
      #text(size: 10pt, weight: "bold", b.title)
      #v(4pt)
      #for point in b.points {
        grid(columns: (1.6fr, 3.5fr, 1fr), gutter: 6pt, align: horizon,
          text(size: 9pt, point.label), box(width: 100%)[
            #rect(width: point.fraction * 100%, height: 6pt, stroke: none, fill: teal)
          ], align(right,text(size: 9pt, point.value)))
        v(3pt)
      }
      #text(size: 8pt, fill: rgb("#586967"), "资料来源　" + b.refs.join("、"))
    ]
  } else if b.kind == "link" {
    par(text(size: 9pt, link(b.url, text(fill: teal, b.text))))
  } else {
    par(b.text)
  }
}
