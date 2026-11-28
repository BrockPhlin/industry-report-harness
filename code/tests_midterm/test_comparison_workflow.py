"""Exercise stored and agent-selected calculations across the workspace boundary."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from report_app import long_report
from report_app.comparison_input import calculation_evidence, comparison_summary, reconcile_comparison
from report_app.comparison_report import verify_comparison
from report_app.errors import AppError
from report_app.province_comparison import comparison_catalog
from report_app.research import Research
from report_app.service import Service
from report_app.store import Store


class ComparisonWorkflowTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name) / "history.sqlite3")
        self.service = Service(self.store, dict(MODEL_ENDPOINT="https://example.invalid/v1/chat/completions",
                                                 MODEL_API_KEY="test-only", MODEL_NAME="fixture"))
        self.app = Research(self.service)
        self.addCleanup(self.app.pool.shutdown)
        self.selection = comparison_catalog()["default"]

    def test_concurrent_submits_share_a_frozen_report_after_reopening(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows = list(pool.map(self.app.create_comparison, [self.selection] * 3))
        self.assertEqual(len({r["id"] for r in rows}), 1)
        key = rows[0]["id"]
        reopened = Research(self.service)
        self.addCleanup(reopened.pool.shutdown)
        with patch("report_app.province_comparison.build_comparison", side_effect=AssertionError("unexpected rerun")):
            row = reopened.task(key)
            self.assertEqual(reopened.comparison_download(key, "report.md"), row["markdown"].encode())
            self.assertEqual([item["id"] for item in reopened.rows()], [key])
        self.assertTrue(verify_comparison(row["comparison"], row["markdown"])["verified"])
        with self.assertRaises(AppError):
            reopened.launch(key)

    def test_attachment_scope_validation_precedes_scheduling(self):
        row = self.app.create_comparison(self.selection)
        base = dict(question="解释负值", workflow="direct", target=800)
        for extra in (dict(comparison_id=["bad"]), dict(comparison_id="f" * 32),
                      dict(comparison_id=row["id"], source_groups=["policy"])):
            with self.subTest(extra=extra), self.assertRaises(AppError):
                self.app.start({**base, **extra})
        self.assertEqual(len(self.app.rows()), 1)

    def test_agent_selects_calculator_from_explicit_two_period_question(self):
        with patch.object(long_report, "generate") as writer:
            task = self.app.start(dict(workflow="direct", target=800, source_groups=["grid"],
                question="比较江西、湖北和浙江在2025年和2026年上半年的集中式光伏新增并网容量，计算差额并排名。"))
            self.app.pool.shutdown(wait=True)
        spec = self.app.spec(task["id"], checkpoint=True)
        comparison = self.app.task(spec["comparison_id"])
        self.assertEqual(set(comparison["comparison"]["plan"]["regions"]), {"江西", "湖北", "浙江"})
        self.assertEqual(writer.call_args.args[4]["comparison"], comparison["comparison"])
        self.assertIn("comparison", [item["stage"] for item in spec["checkpoint"]["operations"]])

    def test_attached_report_links_both_originals_and_renders_even_without_prose_citation(self):
        parent = self.app.create_comparison(self.selection)
        result = parent["comparison"]
        refs = calculation_evidence(result, parent["id"], parent["created"], 20)
        plan = dict(title="分省并网研究", start=2025, end=2026, regions=["江西", "湖北", "浙江"],
                    sections=["口径说明"], source_groups=["grid"])
        md, trace = long_report.assemble(plan, refs, [], [["保持原表负号。"]], [], [],
                                         800, "research", result)
        self.assertIn("附：分省对比复算", md)
        self.assertIn("-59.5", md)
        for source in result["sources"]:
            self.assertIn(source["url"], md)
        self.assertEqual(len(trace["evidence"]), 3)
        self.assertTrue(all(r["comparison_id"] == parent["id"] for r in trace["evidence"]))

    def test_real_draft_rank_change_is_replaced_from_both_years(self):
        parent = self.app.create_comparison(self.selection)
        result = parent["comparison"]
        refs = calculation_evidence(result, parent["id"], parent["created"], 1)
        jiangxi = next(r["ref"] for r in refs if r["region"] == "江西")
        raw = f"江西集中式光伏新增并网由正值转负，在三地中变化幅度最大，排名也相应降至末位。 [{jiangxi}]"
        prior = "此处仅列同一统计期内的并网量。"
        cleaned, count = reconcile_comparison([prior + raw], refs, result)
        text = "\n".join(cleaned)
        self.assertEqual(count, 1)
        self.assertIn(prior, text)
        self.assertIn("2025年排第3，2026年排第3", text)
        self.assertNotIn("降至末位", text)
        self.assertNotIn("变化幅度最大", text)
        self.assertIn("-114.6万千瓦", text)
        summary = " ".join(comparison_summary(result, refs, "江西的名次有变化吗？"))
        self.assertIn("减少了59.5万千瓦", summary)
        self.assertIn("两期均列第3", summary)
        self.assertIn("浙江", summary)
