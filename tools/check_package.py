"""Check portable upload contents; no business-quality conclusions."""
from pathlib import Path
import csv
import json
import os
import re
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
expected_outputs={Path(item) for item in required if Path(item).suffix in {'.pdf','.pptx'}}
actual_outputs={p.relative_to(ROOT) for folder in ['report','ppt','speech']
                for p in (ROOT/'presentations/01-opening'/folder).iterdir()
                if p.suffix in {'.pdf','.pptx'}}
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
assert deck["report_version"] == report_version, "Deck points to a different report version"
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
print('Package checks passed: current artifacts, links, 12 presentation slides with collaboration and speech, WBS allocations and preliminary schedule.')
