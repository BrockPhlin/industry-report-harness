"""Check portable upload contents; no business-quality conclusions."""
from pathlib import Path
import csv
import json
import os
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
deck = json.loads((ROOT/"presentations/01-opening/ppt/slides.json").read_text(encoding="utf-8"))
report_source = (ROOT/"presentations/01-opening/report/report.md").read_text(encoding="utf-8")
report_version = re.search(r"\*\*版本\*\*：([^\s]+)", report_source).group(1)
required = [
    "README.md", "code/run.py", "code/tests/test_baseline.py", "team/claims.csv",
    "presentations/01-opening/report/report.md",
    'presentations/01-opening/report/第11组_项目计划书.pdf',
    "presentations/01-opening/ppt/slides.json",
    f"presentations/01-opening/ppt/第11组_开题展示_{deck['version']}.pptx",
    'presentations/01-opening/ppt/第11组_开题展示.pdf',
    "materials/references/课程报告与评分细则.md",
    'presentations/01-opening/speech/演讲稿.md',
    'presentations/01-opening/speech/第11组_开题演讲稿.pdf',
]
for item in required:
    assert (ROOT/item).is_file(), f"Missing {item}"
image_deck=f"presentations/01-opening/ppt/第11组_开题展示_{deck['version']}_纯图片版.pptx"
required.append(image_deck)
assert (ROOT/image_deck).is_file(), 'Missing image-only display deck'
expected_outputs={Path(item) for item in required if Path(item).suffix in {'.pdf','.pptx'}}
actual_outputs={p.relative_to(ROOT) for folder in ['report','ppt','speech']
                for p in (ROOT/'presentations/01-opening'/folder).iterdir()
                if p.suffix in {'.pdf','.pptx'} and not p.name.startswith(('~$', '.~'))}
assert actual_outputs==expected_outputs, 'Keep only the current generated report/deck outputs'
for stage in ["02-midterm", "03-final"]:
    for kind in ["report", "ppt"]:
        assert (ROOT/"presentations"/stage/kind).is_dir()
# A checkout has root Git metadata; only embedded repositories are invalid.
for directory, children, files in os.walk(ROOT):
    if Path(directory) != ROOT:
        assert ".git" not in children + files, f"Nested Git history: {directory}"
    children[:] = [name for name in children if name not in {".git", ".build", "node_modules", ".venv"}]
with (ROOT/"team/claims.csv").open(encoding="utf-8") as f:
    claims=list(csv.DictReader(f))
assert [r["task_id"] for r in claims] == [f"T{i}" for i in range(6)]
assert claims[0]["owner"] == "程文博"
with (ROOT/"team/members.csv").open(encoding="utf-8") as f:
    names={r["name"] for r in csv.DictReader(f)}
assert all(not r["owner"] or r["owner"] in names for r in claims)
for source in ROOT.rglob("*.md"):
    if ".build" in source.parts:
        continue
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)",source.read_text(encoding="utf-8")):
        if target.startswith(("http:","https:","#")):
            continue
        assert (source.parent/target.split("#")[0]).exists(), f"Broken link in {source}: {target}"
assert len(deck["slides"]) == 12 and sum(s["seconds"] for s in deck["slides"]) == 400
assert deck["formal_slides"] == len(deck['slides']) and all(s['seconds']>0 for s in deck['slides'])
assert all(s.get('speech') and s['speech'] in s['notes'] for s in deck['slides'])
assert all('备用' not in s['title'] for s in deck['slides'])
# The delivered opening deck is frozen after the presentation. Report-only
# patch revisions may follow it, while unrelated report versions still fail.
assert (deck['report_version'] == report_version or
        re.fullmatch(re.escape(deck['report_version']) + r'\.\d+', report_version)), \
    "Report must match the presented version or be its report-only patch revision"
with zipfile.ZipFile(ROOT/required[7]) as z:
    slides=[p for p in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml",p)]
    assert len(slides)==len(deck['slides'])
    for p in slides:
        node=ET.fromstring(z.read(p))
        assert node.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}t"), "Editable text required"
with (ROOT/'team/wbs.csv').open(encoding='utf-8') as f:
    leaves=list(csv.DictReader(f))
with (ROOT/'team/semester-plan.csv').open(encoding='utf-8') as f:
    parents=list(csv.DictReader(f))
assert len(leaves)==21 and len({r['activity_id'] for r in leaves})==21
def totals(rows, key):
    result={}
    for row in rows:
        assert int(row['owner_hours'])+int(row['collaborator_hours'])==int(row['total_hours'])
        if key=='work_package':
            result[row[key]]=result.get(row[key],0)+int(row['total_hours'])
        else:
            for who,hours in [('owner','owner_hours'),('collaborator','collaborator_hours')]:
                if row[who]:
                    assert row[who] in names
                    result[row[who]]=result.get(row[who],0)+int(row[hours])
    return result
assert totals(leaves,'work_package')==totals(parents,'work_package')
assert totals(leaves,'person')==totals(parents,'person')
assert sum(int(row['total_hours']) for row in leaves)==268
from plan_math import calculate
plan=calculate(json.loads((ROOT/'team/core-schedule.json').read_text(encoding='utf-8')))
assert plan['finish_days']==23 and plan['buffered_days']==26
assert plan['critical']==['A','B','C','D','E'] and plan['pert_hours']==56
assert deck['slides'][8]['id']=='github-collaboration'
assert (ROOT/'assets/opening/github-collaborators.png').is_file()
assert deck['slides'][6]['id']=='semester-timeline'
timeline=json.loads((ROOT/'team/semester-timeline.json').read_text(encoding='utf-8'))
timeline_text={item['text'] for item in deck['slides'][6]['items'] if item['type']=='text'}
for row in timeline['rows']:
    assert row['phase'] in timeline_text
    assert all(cell['period'] in timeline_text and cell['work'] in timeline_text for cell in row['cells'])

assert 'cash_budget_cny' not in json.loads((ROOT/'team/core-schedule.json').read_text())
for text in [report_source, json.dumps(deck,ensure_ascii=False)]:
    assert not any(amount in text for amount in ['160元','40元','200元']), 'Unsupported cash estimate remains'
assert '逐步形成自己的创新' in json.dumps(deck,ensure_ascii=False)
assert '目录' in report_source and '参考报告检索试验' in report_source
# Display-only export: exactly one full-slide raster, no editable foreground.
with zipfile.ZipFile(ROOT/image_deck) as z:
    ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
        'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
        'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    from posixpath import normpath,join,dirname
    for i,s in enumerate(deck['slides'],1):
        part=f'ppt/slides/slide{i}.xml';node=ET.fromstring(z.read(part))
        assert len(node.findall('.//p:pic',ns))==1
        assert not node.findall('.//p:sp',ns) and not node.findall('.//p:graphicFrame',ns)
        assert not node.findall('.//a:t',ns)
        rid=node.find('.//a:blip',ns).get('{'+ns['r']+'}embed')
        rel=ET.fromstring(z.read(f'ppt/slides/_rels/slide{i}.xml.rels'))
        target=next(x.get('Target') for x in rel if x.get('Id')==rid)
        image_part=normpath(join(dirname(part),target)).lstrip('/')
        # PNG stores dimensions in its fixed IHDR header. Inspect metadata only;
        # decoding/rendering remains part of the material-generation workflow.
        png = z.read(image_part)
        assert len(png) >= 24 and png[:16] == b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR', 'Expected PNG with IHDR'
        assert struct.unpack('>II', png[16:24]) == (2560, 1440), 'Unexpected slide image dimensions'
        notes=ET.fromstring(z.read(f'ppt/notesSlides/notesSlide{i}.xml'))
        assert s['speech'] in ''.join(notes.itertext())
print('Image display deck: 12 single-image slides, 2560x1440, matching speech notes.')

product_text=json.dumps(deck,ensure_ascii=False)
for requirement in ['政府智库','产业规划','行业研究','产业分析报告','景气报告','对标报告','招商报告','出海研判报告','公文风格润色','版本管理']:
    assert requirement in product_text, f'Missing original topic requirement: {requirement}'
assert '首轮跑通' in product_text and '分步扩展' in product_text

assert deck['slides'][9]['id']=='output-references'
reference_manifest=json.loads((ROOT/'materials/references/output-report-targets.json').read_text())
assert {s['id'] for s in reference_manifest['sources']}=={'R4','R5'}
for source in reference_manifest['sources']:
    assert (ROOT/source['preview_path']).is_file()
assert '每周一下午' in product_text and '课后' in product_text
assert '内容模板' in product_text and '版式模板' in product_text and 'Markdown' in product_text
assert '周一晚上' not in product_text

assert '参考报告检索工具' in product_text
assert '效果待验证' in product_text
assert '对照有无工具' in report_source
assert (ROOT/'docs/参考报告检索工具设计.md').is_file()


report_sections=re.split(r'<!--\s*pagebreak\s*-->',report_source)
assert len(report_sections)==11 and '\n## 目录' in report_sections[0]
assert len(report_sections[1:])==10
assert '人时' not in report_source and '三点估算' not in report_source
assert all(term in report_source for term in ['DeepSeek Harness','LangGraph','Deep Agents'])
contents_targets=re.findall(r'^\|[^\n]+\|\s*(\d+)\s*\|$',report_sections[0],re.M)
assert list(map(int,contents_targets))==list(range(1,11))

print('All package checks passed: artifacts, links, WBS/schedule, 12 slides, PNG dimensions and speech notes; standard-library only.')
