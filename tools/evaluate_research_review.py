"""Replay report-review controls and injected faults against published photovoltaic figures.

Run with the same Python used for code/run.py. Everything is local to a temporary
database. Snapshot fingerprints here cover the CSV extracts in code/data/nea.
"""
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from report_app.claim_audit import audit_claims
from report_app.evidence_changes import compare_evidence
from report_app.long_report import validate_draft, validate_paragraphs
from report_app.provinces import HALF_YEAR_TABLES
from report_app.solar_data import SolarLibrary
from report_app.store import Store
from report_app.studies import STUDIES


CAPACITY = "集中式光伏上半年新增并网容量"
CUMULATIVE = "集中式光伏截至六月底累计并网容量"
REGIONS = ("江西", "湖北")
# Measured on the original validator before the new draft review was integrated.
BASELINE_COMMIT = "855d09eac0d0d6f97e00629cffd7d630e88e3246"
BASELINE = {
    "正确负值": "accepted", "正确上年值": "accepted", "正确累计值": "flagged",
    "漏写负号": "flagged", "单位替换": "flagged", "捏造数字": "flagged",
    "年份调换": "accepted", "省份调换": "accepted", "新增误用累计值": "accepted",
    "缺少出处": "flagged", "出处不存在": "flagged", "因果需要人工判断": "accepted",
}


def import_extract(library, year, raw):
    origin = HALF_YEAR_TABLES[year][0]

    def parse(data):
        observations = []
        for row in csv.DictReader(io.StringIO(data.decode("utf-8"))):
            if row["地区"] in REGIONS:
                for metric in (CAPACITY, CUMULATIVE):
                    if row[metric]:
                        observations.append((row["地区"], year, metric, "万千瓦", row[metric]))
        return observations, []

    # A local extract has a different identity and digest than the official image.
    download = f"https://example.invalid/local-extracts/{year}-h1.csv"
    source, notice = library.ingest(download, f"{year}年上半年光伏发电建设情况", "国家能源局",
                                    origin, parse, loader=lambda _: raw)
    if source is None:
        raise RuntimeError(notice)
    return source


def injected_csv(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    output = io.StringIO()
    writer = csv.DictWriter(output, reader.fieldnames)
    writer.writeheader()
    for row in reader:
        if row["地区"] == "江西":
            row[CAPACITY] = "-40.9"
        if row["地区"] == "湖北":
            row[CUMULATIVE] = ""
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def check_gate(validator, task, catalog):
    try:
        validator(task, catalog, 1, 400)
        return "accepted", ""
    except ValueError as exc:
        return "flagged", str(exc)


def run_claim_cases(evidence):
    refs = {(r["raw_series"][0][0], r["region"], r["metric"]): r["ref"] for r in evidence}
    j25 = refs[2025, "江西", CAPACITY]
    j26 = refs[2026, "江西", CAPACITY]
    h26 = refs[2026, "湖北", CAPACITY]
    total = refs[2026, "江西", CUMULATIVE]
    # Labels were set against the two NEA tables before running either checker.
    cases = [
        ("正确负值", "2026年上半年江西集中式光伏新增并网容量为-41.9万千瓦。", [j26], "matched"),
        ("正确上年值", "2025年上半年江西集中式光伏新增并网容量为17.6万千瓦。", [j25], "matched"),
        ("正确累计值", "截至2026年6月底，江西集中式光伏累计并网容量为1358.3万千瓦。", [total], "matched"),
        ("漏写负号", "2026年上半年江西集中式光伏新增并网容量为41.9万千瓦。", [j26], "mismatch"),
        ("单位替换", "2026年上半年江西集中式光伏新增并网容量为-41.9 GW。", [j26], "mismatch"),
        ("捏造数字", "2026年上半年江西集中式光伏新增并网容量为7777.7万千瓦。", [j26], "mismatch"),
        ("年份调换", "2026年上半年江西集中式光伏新增并网容量为17.6万千瓦。", [j25, j26], "mismatch"),
        ("省份调换", "2026年上半年江西集中式光伏新增并网容量为-0.7万千瓦。", [j26, h26], "mismatch"),
        ("新增误用累计值", "2026年上半年江西集中式光伏新增并网容量为1358.3万千瓦。", [j26, total], "mismatch"),
        ("缺少出处", "2026年上半年江西集中式光伏新增并网容量为-41.9万千瓦。", [], "review"),
        ("出处不存在", "2026年上半年江西集中式光伏新增并网容量为-41.9万千瓦。", ["E999"], "review"),
        ("因果需要人工判断", "针对新增并网容量的变化，融资条件起到了决定性作用。", [j26], "review"),
    ]
    catalog = {r["ref"]: r for r in evidence}
    results = []
    for name, sentence, cited, expected in cases:
        task = {"paragraphs": [{"text": sentence, "refs": cited}]}
        gate, gate_reason = check_gate(validate_paragraphs, task, catalog)
        draft, draft_reason = check_gate(validate_draft, task, catalog)
        markdown = sentence + " " + " ".join(f"[{ref}]" for ref in cited)
        claims = audit_claims(markdown, evidence)["claims"]
        actual = claims[0]["status"] if len(claims) == 1 else f"{len(claims)} claims"
        results.append(dict(case=name, sentence=sentence, refs=cited, expected=expected,
                            historical_gate=BASELINE[name], paragraph_gate=gate, gate_reason=gate_reason,
                            draft_gate=draft, draft_reason=draft_reason, claim_audit=actual,
                            review_reasons=[reason for claim in claims for reason in claim["reasons"]]))
    return results


def explore_cost_metric():
    study = next(study for study in STUDIES if study.key == "irena-cost-2025")
    with (ROOT / "code/data/studies/irena-cost-2025.csv").open(encoding="utf-8") as source:
        row = next(row for row in csv.DictReader(source) if row["region"] == "China")
    evidence = dict(
        ref="E1", title=study.title, publisher=study.publisher, url=study.landing,
        region=row["region"], metric=row["metric"], unit=row["unit"], locator=study.location,
        text=f'{row["year"]}年中国{row["metric"]}为{row["value"]}{row["unit"]}。',
        series=[(int(row["year"]), row["value"])],
    )
    examples = [
        ("2025年中国新投运公用事业级光伏平准化发电成本为36美元/MWh。", "matched"),
        ("2025年中国光伏电站售电成交价为36美元/MWh。", "mismatch"),
        ("2025年中国光伏的平准化发电成本仅为36美元/MWh，连续两年全球最低。", "review"),
    ]
    results = []
    for sentence, expected in examples:
        claim, = audit_claims(sentence + " [E1]", [evidence])["claims"]
        results.append(dict(sentence=sentence, expected=expected, status=claim["status"], reasons=claim["reasons"]))
    return dict(source=study.landing, location=study.location, cases=results)


def run_versions(directory):
    store = Store(directory / "replay.sqlite3")
    library = SolarLibrary(store)
    raw = {year: (ROOT / f"code/data/nea/{year}-h1.csv").read_bytes() for year in (2025, 2026)}
    ids = [import_extract(library, year, data) for year, data in raw.items()]
    plan = dict(regions=REGIONS, start=2025, end=2026, keywords=[])
    evidence = library.select(ids, plan)
    old_count = len(evidence)
    if old_count != 8:
        raise RuntimeError(f"Expected two years × two regions × two indicators, got {old_count}")
    stable = compare_evidence(store, evidence)
    import_extract(library, 2026, injected_csv(raw[2026]))
    changed = compare_evidence(store, evidence)
    rows = {(i["year"], i["region"], i["metric"]): i for i in changed["items"]}
    changed_row = rows[2026, "江西", CAPACITY]
    missing_row = rows[2026, "湖北", CUMULATIVE]
    version_pass = (
        stable["counts"]["unchanged"] == old_count
        and changed["counts"]["unchanged"] == old_count - 2
        and changed_row["status"] == "changed"
        and changed_row["before"] == "-41.9" and changed_row["after"] == "-40.9"
        and missing_row["status"] == "missing"
        and library.select(ids, plan) == evidence
    )
    versions = dict(
        unchanged_control=stable["counts"], injected_snapshot=changed["counts"],
        edited_observation=changed_row, removed_observation=missing_row, passed=version_pass,
    )
    return run_claim_cases(evidence), versions


def main():
    with tempfile.TemporaryDirectory() as temp:
        cases, versions = run_versions(Path(temp))
    incorrect = [row for row in cases if row["expected"] == "mismatch"]
    controls = [row for row in cases if row["expected"] == "matched"]
    manual = [row for row in cases if row["expected"] == "review"]
    exploratory = explore_cost_metric()
    result = dict(
        scope="离线小样本。在临时数据库植入一处数值修订和一处缺行。",
        sources={
            str(year): dict(
                official_page=HALF_YEAR_TABLES[year][0],
                fixture_sha256=sha256((ROOT / f"code/data/nea/{year}-h1.csv").read_bytes()).hexdigest(),
            )
            for year in (2025, 2026)
        },
        historical_validator=BASELINE_COMMIT,
        correct_controls=len(controls),
        baseline_falsely_flagged_controls=sum(r["historical_gate"] == "flagged" for r in controls),
        new_matched_controls=sum(r["claim_audit"] == "matched" for r in controls),
        draft_accepted_controls=sum(r["draft_gate"] == "accepted" for r in controls),
        injected_errors=len(incorrect),
        baseline_flagged_errors=sum(r["historical_gate"] == "flagged" for r in incorrect),
        draft_flagged_errors=sum(r["draft_gate"] == "flagged" for r in incorrect),
        new_confirmed_mismatches=sum(r["claim_audit"] == "mismatch" for r in incorrect),
        expected_manual_review=len(manual),
        new_referred_to_review=sum(r["claim_audit"] == "review" for r in manual),
        cases=cases, version_comparison=versions, exploratory_cost_checks=exploratory,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    passed = (
        versions["passed"] and all(r["expected"] == r["claim_audit"] for r in cases)
        and all(r["draft_gate"] == "flagged" for r in incorrect)
        and all(r["draft_gate"] == "accepted" for r in controls)
        and all(r["status"] == r["expected"] for r in exploratory["cases"])
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
