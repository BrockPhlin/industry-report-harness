"""User-visible reports and replay of two independently archived provincial releases."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from report_app.comparison_report import render_comparison, verify_comparison
from report_app.errors import AppError
from report_app.province_comparison import build_comparison


class ComparisonReportTests(unittest.TestCase):
    def setUp(self):
        self.result = build_comparison({
            "period": "half_year", "metric": "central_new", "regions": ["江西", "湖北", "浙江", "江苏"],
        })
        self.markdown = render_comparison(self.result, "markdown")
        self.bundle = json.loads(render_comparison(self.result, "json"))

    def test_report_keeps_negative_published_cells_and_calculation_method(self):
        text = self.markdown.decode()
        self.assertIn("| 4→4 | 江西 | 17.6 | -41.9 | -59.5 | -338.07% |", text)
        self.assertIn("江苏在所选可比地区中位居第一", text)
        self.assertIn("4 个地区减少", text)
        self.assertIn("四舍五入", text)
        self.assertIn("本报告根据两期原表计算", text)
        for source in self.result["sources"]:
            self.assertIn(source["url"], text)
            self.assertIn(source["data_url"], text)

    def test_three_quarter_new_and_stock_use_correct_period_and_column(self):
        for metric, label in (("total_new", "光伏前三季度新增并网容量"), ("central_stock", "集中式光伏截至九月底累计并网容量")):
            with self.subTest(metric=metric):
                result = build_comparison({"period": "three_quarters", "metric": metric, "regions": ["江西", "广东"]})
                text = render_comparison(result, "md").decode()
                self.assertIn("2025、2026 年前三季度", text)
                self.assertNotIn("全年", text)
                self.assertIn(label, text)
                self.assertEqual(result["sources"][0]["source_type"], "html")
                self.assertEqual(text.count(result["sources"][0]["url"]), 1)

    def test_zero_base_as_gap_in_rate_only(self):
        result = build_comparison({"period": "half_year", "metric": "household_new", "regions": ["西藏", "浙江"]})
        text = render_comparison(result, "md").decode()
        self.assertIn("| 2→2 | 西藏 | 0.0 | 0.0 | 0.0 | — |", text)
        self.assertIn("基期值为零", text)

    def test_two_period_ranks_are_not_reversed(self):
        result = build_comparison({
            "period": "three_quarters", "metric": "household_new", "regions": ["浙江", "江苏", "湖北", "江西", "广东", "山东"],
        })
        text = render_comparison(result, "md").decode()
        self.assertIn("| 2→1 | 广东 |", text)
        self.assertIn("| 1→2 | 江苏 |", text)

    def test_scope_change_lists_known_originals_and_leaves_absence_visible(self):
        result = build_comparison({"period": "annual", "metric": "total_stock", "regions": ["新疆", "新疆兵团"]})
        text = render_comparison(result, "md").decode()
        self.assertIn("0 个可比较", text)
        self.assertIn("| 新疆兵团 | 329.2 | — |", text)
        self.assertIn("| 新疆 | 5345.6 | 9090.1 |", text)
        self.assertIn("地区范围需核实", text)
        self.assertNotIn("位居第一", text)

    def test_rebuilds_download_from_csv_and_compares_supplied_body(self):
        self.assertEqual(verify_comparison(self.bundle, self.markdown), {
            "verified": True, "rows": 4, "missing": 0, "sources": 2,
            "markdown_sha256": sha256(self.markdown).hexdigest(),
        })
        self.assertTrue(verify_comparison(self.bundle, self.markdown.decode())["verified"])
        with self.assertRaisesRegex(ValueError, "Markdown"):
            verify_comparison(self.bundle, self.markdown + b"x")

    def test_reject_even_coordinated_forgery_with_new_body_hash(self):
        forged = deepcopy(self.result)
        forged["rows"][0].update(before="200", after="400", delta="200", growth_pct="100.00")
        forged_bundle = json.loads(render_comparison(forged, "json"))
        forged_md = render_comparison(forged, "md")
        self.assertEqual(forged_bundle["markdown_sha256"], sha256(forged_md).hexdigest())
        with self.assertRaisesRegex(ValueError, "rows"):
            verify_comparison(forged_bundle, forged_md)

    def test_pre_rank_bundles_can_still_be_read(self):
        old = deepcopy(self.result)
        for row in old["rows"]:
            del row["before_rank"]
        old["notes"][0] = "按后期原表数值降序排列，名次限所选且两期可比的地区。并列地区同名次，下一名按实际顺位。"
        markdown = render_comparison(old, "md")
        self.assertIn("| 4 | 江西 |", markdown.decode())
        bundle = json.loads(render_comparison(old, "json"))
        self.assertEqual(bundle["version"], 1)
        self.assertTrue(verify_comparison(bundle, markdown)["verified"])

    def test_reject_invalid_schema_paths_and_types(self):
        altered_source = deepcopy(self.bundle)
        altered_source["sources"][0]["csv_file"] = "../untrusted.csv"
        bad_type = deepcopy(self.bundle)
        bad_type["rows"][0]["rank"] = True
        for case in ([], {}, dict(self.bundle, version=True), dict(self.bundle, plan=[]),
                     dict(self.bundle, plan={"period": []}), altered_source, bad_type,
                     dict(self.bundle, rows=object()), dict(self.bundle, markdown_sha256="0"*64)):
            with self.subTest(case=str(case)[:35]), self.assertRaises((ValueError, AppError)):
                verify_comparison(case)

    def test_frozen_text_used_for_downloads(self):
        frozen = "# 原文\n\n历史正文。\n"
        self.assertEqual(render_comparison(self.result, "md", markdown=frozen), frozen.encode())
        rendered = render_comparison(self.result, "json", markdown=frozen)
        self.assertEqual(json.loads(rendered)["markdown_sha256"], sha256(frozen.encode()).hexdigest())

    @unittest.skipUnless(shutil.which("typst"), "PDF export needs Typst")
    def test_pdf_compiles_ranked_and_missing_tables(self):
        result = build_comparison({"period": "annual", "metric": "total_stock", "regions": ["浙江", "新疆"]})
        self.assertTrue(render_comparison(result, "pdf").startswith(b"%PDF-"))

if __name__ == "__main__":
    unittest.main()
