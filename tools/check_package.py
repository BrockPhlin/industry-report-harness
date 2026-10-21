"""Check portable upload contents; no business-quality conclusions."""
from pathlib import Path
import csv
import json
import re
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
required = [
    "README.md", "code/run.py", "code/tests/test_baseline.py", "team/claims.csv",
    "presentations/01-opening/report/report.md",
    "presentations/01-opening/report/第11组_项目计划书_模板_v0.4.pdf",
    "presentations/01-opening/ppt/slides.json",
    "presentations/01-opening/ppt/第11组_开题展示_模板_v0.4.pptx",
    "presentations/01-opening/ppt/第11组_开题展示_模板_v0.4.pdf",
    "materials/references/课程报告与评分细则.md",
]
for item in required:
    assert (ROOT/item).is_file(), f"Missing {item}"
for stage in ["02-midterm", "03-final"]:
    for kind in ["report", "ppt"]:
        assert (ROOT/"presentations"/stage/kind).is_dir()
assert not (ROOT/".git").exists(), "Do not package a nested Git history"
with (ROOT/"team/claims.csv").open() as f:
    claims=list(csv.DictReader(f))
assert [r["task_id"] for r in claims] == [f"T{i}" for i in range(6)]
assert claims[0]["owner"] == "程文博"
with (ROOT/"team/members.csv").open() as f:
    names={r["name"] for r in csv.DictReader(f)}
assert all(not r["owner"] or r["owner"] in names for r in claims)
for source in ROOT.rglob("*.md"):
    if ".build" in source.parts:
        continue
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)",source.read_text()):
        if target.startswith(("http:","https:","#")):
            continue
        assert (source.parent/target.split("#")[0]).exists(), f"Broken link in {source}: {target}"
deck=json.loads((ROOT/"presentations/01-opening/ppt/slides.json").read_text())
assert len(deck["slides"]) == 12 and sum(s["seconds"] for s in deck["slides"]) == 400
with zipfile.ZipFile(ROOT/required[7]) as z:
    slides=[p for p in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml",p)]
    assert len(slides)==12
    for p in slides:
        node=ET.fromstring(z.read(p))
        assert node.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}t"), "Editable text required"
print("Upload package checks passed: files, claims, relative links, reserved folders, editable 12-slide deck.")
