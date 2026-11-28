"""Replay immutable report evidence against later local source snapshots."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from report_app.evidence_changes import compare_evidence
from report_app.solar_data import SolarLibrary
from report_app.store import Store


DATA = "https://example.org/annual.csv"
LANDING = "https://example.org/annual"
PLAN = dict(regions=["China"], start=2021, end=2026, keywords=[])


class EvidenceChangesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "test.sqlite3")
        self.library = SolarLibrary(self.store)

    def put(self, content, values, *, url=DATA, unit="GW", schema="", passages=()):
        observations = [("China", year, "装机", unit, val) for year, val in values]
        sid, _ = self.library.ingest(url, "装机年表", "发布方", LANDING,
                                     lambda _: (observations, passages), schema=schema,
                                     loader=lambda _: content.encode())
        self.assertIsNotNone(sid)
        return sid

    def test_changes_match_exact_asset_scope_and_raw_precision(self):
        sid = self.put("v1", [(2021, "1.234"), (2022, "2.0"), (2023, "3"), (2024, "-0.1")],
                       passages=[("附注", "表注")])
        evidence = self.library.select([sid], PLAN)
        self.put("v2", [(2021, "1.233"), (2022, "2.0000"), (2024, "-0.1"), (2025, "5")])
        self.put("other asset", [(2023, "3"), (2022, "799")], url=DATA + "?method=alternate")
        with patch.object(self.library, "download", side_effect=AssertionError("unexpected network call")):
            result = compare_evidence(self.store, evidence)
        self.assertEqual(result["counts"], {"changed": 1, "missing": 1, "unchanged": 2, "unverified": 0})
        self.assertEqual(result["skipped_passages"], 1)
        self.assertEqual(result["affected_refs"], [evidence[0]["ref"]])
        rows = {r["year"]: r for r in result["items"]}
        self.assertEqual((rows[2021]["before"], rows[2021]["after"]), ("1.234", "1.233"))
        self.assertEqual(rows[2021]["data_url"], DATA)
        self.assertIsNone(rows[2023]["after"])
        self.assertNotIn(2025, rows)
        self.assertEqual(evidence[0]["raw_series"][0], (2021, "1.234"))

    def test_unit_and_unavailable_source_are_indeterminate(self):
        sid = self.put("v1", [(2021, "1")])
        evidence = self.library.select([sid], PLAN)
        self.put("new unit", [(2021, "1000")], unit="MW")
        result = compare_evidence(self.store, evidence)
        self.assertEqual(result["items"][0]["status"], "unverified")
        self.assertIn("MW", result["items"][0]["reason"])
        self.put("article update", [], passages=[("正文", "发布内容已更新。")])
        self.assertEqual(compare_evidence(self.store, evidence)["counts"]["unverified"], 1)
        foreign = dict(evidence[0], data_url="https://example.org/unloaded.csv")
        self.assertEqual(compare_evidence(self.store, [foreign])["affected_refs"], [])

    def test_legacy_display_only_recovers_the_archived_decimal_or_reports_uncertainty(self):
        sid = self.put("v1", [(2021, "1.234")])
        legacy = self.library.select([sid], PLAN)[0]
        del legacy["raw_series"], legacy["data_url"]
        self.put("v2", [(2021, "1.233")])
        item = compare_evidence(self.store, [legacy])["items"][0]
        self.assertEqual((item["before_basis"], item["before"], item["status"]), ("stored_snapshot", "1.234", "changed"))
        self.put("identical bytes with shared landing", [(2021, "1.233")], url=DATA + "?v=2")
        mismatch = dict(legacy, digest="0" * 64, data_url=DATA)
        self.assertEqual(compare_evidence(self.store, [mismatch])["items"][0]["status"], "unverified")
        inconsistent = dict(legacy, series=[(2021, "999")])
        self.assertEqual(compare_evidence(self.store, [inconsistent])["items"][0]["before_basis"], "display_only")
        self.put("v1", [(2021, "1.234")], url=DATA + "?sheet=other")
        ambiguous = compare_evidence(self.store, [legacy])["items"][0]
        self.assertEqual(ambiguous["status"], "unverified")
        self.assertIsNone(ambiguous["data_url"])

    def test_same_bytes_reparse_distinguishes_library_revision_and_no_numeric_evidence(self):
        old = self.put("same document", [(2021, "1")], schema="v1")
        evidence = self.library.select([old], PLAN)
        self.put("same document", [(2021, "2")], schema="v2")
        with patch("report_app.solar_data.now", return_value="2099-01-01T00:00:00+00:00"):
            self.put("same document", [(2021, "1")], schema="v1")
        result = compare_evidence(self.store, evidence)
        self.assertEqual(result["items"][0]["status"], "changed")
        self.assertIn("解析值", result["items"][0]["reason"])
        self.assertEqual(compare_evidence(self.store, [{"ref": "E1", "text": "政策条文"}])["skipped_passages"], 1)
        self.assertEqual(compare_evidence(self.store, None)["items"], [])


if __name__ == "__main__":
    unittest.main()
