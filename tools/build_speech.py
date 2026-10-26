"""Generate a printable speech and Markdown from each slide's spoken text.

slides.json is the single content source. Presenter cues and sources stay outside
spoken paragraphs. Three slide scripts per A4 page; overflow fails the build.
"""
import html
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from build_pdfs import ROOT, BLUE, INK, MUTED, register_fonts


def build():
    register_fonts()
    deck=json.loads((ROOT/'presentations/01-opening/ppt/slides.json').read_text())
    target=ROOT/'presentations/01-opening/speech'
    target.mkdir(exist_ok=True)
    lines=['# 第11组开题演讲稿', '', f"展示人：郭润航　对应PPT：{deck['version']}　共{len(deck['slides'])}页", '',
           '按页讲述，合计计划400秒，留20秒用于翻页和停顿。正式上台前需要实际计时彩排。操作提示不必读出，来源已放在PPT备注。', '']
    for i,slide in enumerate(deck['slides'],1):
        lines += [f"## 第{i}页：{slide['title']}", '', f"计划用时：{slide['seconds']}秒。", '']
        if slide['cue']:
            lines += [f"指图提示：{slide['cue']}", '']
        lines += [slide['speech'], '']
    (target/'演讲稿.md').write_text('\n'.join(lines),encoding='utf8')
    output=target/'第11组_开题演讲稿.pdf'
    pdf=canvas.Canvas(str(output),pagesize=A4,pageCompression=1)
    pdf.setTitle('第11组开题演讲稿 '+deck['version']);pdf.setAuthor('Team 11')
    body=ParagraphStyle('speech',fontName='Body',fontSize=13,leading=22,wordWrap='CJK',textColor=colors.HexColor(INK))
    heading=ParagraphStyle('heading',fontName='Strong',fontSize=15,leading=22,wordWrap='CJK',textColor=colors.HexColor(BLUE))
    cue=ParagraphStyle('cue',fontName='Body',fontSize=10.5,leading=16,wordWrap='CJK',textColor=colors.HexColor(MUTED))
    w,h=A4;margin=52;width=w-2*margin
    groups=[deck['slides'][i:i+3] for i in range(0,len(deck['slides']),3)]
    for page,group in enumerate(groups,1):
        pdf.setFont('Strong',18);pdf.setFillColor(colors.HexColor(BLUE));pdf.drawString(margin,h-43,'第11组开题演讲稿')
        pdf.setFont('Body',9);pdf.setFillColor(colors.HexColor(MUTED));pdf.drawRightString(w-margin,h-40,f"郭润航 · PPT {deck['version']}")
        pdf.setStrokeColor(colors.HexColor(BLUE));pdf.line(margin,h-54,w-margin,h-54)
        y=h-73
        for offset,slide in enumerate(group):
            index=(page-1)*3+offset+1
            blocks=[(f"第{index}页　{slide['title']}",heading,8),
                    (f"约{slide['seconds']}秒"+('　|　'+slide['cue'] if slide['cue'] else ''),cue,7),
                    (slide['speech'],body,22)]
            for value,style,gap in blocks:
                p=Paragraph(html.escape(value),style);_,ph=p.wrap(width,h)
                if y-ph<49:raise ValueError(f'Speech page {page} overflows')
                p.drawOn(pdf,margin,y-ph);y-=ph+gap
        pdf.setFont('Body',9);pdf.setFillColor(colors.HexColor(MUTED));pdf.drawString(margin,27,'提示不必朗读；讲述内容与PPT备注一致')
        pdf.drawRightString(w-margin,27,f'{page} / {len(groups)}');pdf.showPage()
    pdf.save()
    print(f'Speech: {len(deck["slides"])} slides, {len(groups)} PDF pages')


if __name__=='__main__':
    build()
