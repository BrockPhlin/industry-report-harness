"""Check provincial comparisons against actual archived tables and explicit edge cases."""

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from report_app.errors import AppError
from report_app.province_comparison import build_comparison, comparison_catalog


def selection(period="half_year", metric="central_new", regions=None):
    return dict(period=period, metric=metric, regions=["江西", "湖北"] if regions is None else regions)


class ProvinceComparisonTests(unittest.TestCase):
    def test_published_negative_zero_and_decimal_change(self):
        result = build_comparison(selection(regions=["江西", "河南", "湖北", "浙江"]))
        self.assertEqual([(r["region"], r["rank"]) for r in result["rows"]],
                         [("浙江", 1), ("河南", 2), ("湖北", 3), ("江西", 4)])
        self.assertEqual([r["before_rank"] for r in result["rows"]], [1, 3, 2, 4])
        jx = result["rows"][-1]
        self.assertEqual((jx["before"], jx["after"], jx["delta"], jx["growth_pct"]),
                         ("17.6", "-41.9", "-59.5", "-338.07"))
        self.assertEqual(result["rows"][1]["after"], "0.0")
        self.assertEqual(result["missing"], [])
        self.assertTrue(any("退出" in note for note in result["notes"]))
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)

    def test_every_catalog_choice_has_two_archived_tables_and_distinct_source_hashes(self):
        catalog = comparison_catalog()
        self.assertEqual({p["id"] for p in catalog["periods"]}, {"half_year", "three_quarters", "annual"})
        for period in catalog["periods"]:
            self.assertNotIn("China", period["regions"])
            self.assertEqual(len(period["metrics"]), 8)
            for metric in period["metrics"]:
                with self.subTest(period=period["id"], metric=metric["id"]):
                    result = build_comparison(selection(period["id"], metric["id"], period["regions"]))
                    self.assertEqual(result["plan"]["metric_label"], metric["label"])
                    self.assertEqual(len(result["rows"]) + len(result["missing"]), len(period["regions"]))
                    self.assertEqual([s["year"] for s in result["sources"]],
                                     [period["before_year"], period["after_year"]])
                    for source in result["sources"]:
                        raw = (Path(__file__).resolve().parents[2] / source["csv_file"]).read_bytes()
                        self.assertEqual(sha256(raw).hexdigest(), source["csv_sha256"])
                        self.assertNotEqual(source["csv_sha256"], source["source_sha256"])

    def test_third_quarters_compare_actual_html_to_image_without_using_annual_values(self):
        result = build_comparison(selection("three_quarters", "total_new"))
        self.assertEqual(result["plan"]["metric_label"], "光伏前三季度新增并网容量")
        jx = next(r for r in result["rows"] if r["region"] == "江西")
        self.assertEqual((jx["before"], jx["after"], jx["delta"]), ("241.9", "115.0", "-126.9"))
        source, target = result["sources"]
        self.assertEqual(source["source_type"], "html")
        self.assertEqual(source["data_url"], source["url"])
        self.assertIsNone(source["image_sha256"])
        self.assertEqual(target["image_sha256"], target["source_sha256"])
        self.assertEqual(target["source_type"], "image")
        self.assertNotEqual(target["data_url"], target["url"])

    def test_blanks_and_annual_geography_change_do_not_enter_ranking(self):
        result = build_comparison(selection("annual", "central_new", ["上海", "新疆", "北京", "新疆兵团"]))
        self.assertEqual([r["region"] for r in result["rows"]], ["北京"])
        self.assertEqual((result["rows"][0]["before_rank"], result["rows"][0]["rank"]), (1, 1))
        missing = {r["region"]: r for r in result["missing"]}
        self.assertEqual((missing["上海"]["before"], missing["上海"]["after"]), (None, "22.2"))
        self.assertEqual((missing["新疆"]["before"], missing["新疆"]["after"]), ("2659.4", "3402.1"))
        self.assertIn("范围", missing["新疆"]["reason"])
        self.assertIsNone(missing["新疆兵团"]["after"])
        self.assertEqual(build_comparison(selection("annual", "central_new", ["上海", "河南"]))["rows"], [])

    def test_zero_baseline_is_measured_but_has_no_growth_rate(self):
        result = build_comparison(selection(metric="household_new", regions=["西藏", "北京"]))
        tibet = next(r for r in result["rows"] if r["region"] == "西藏")
        self.assertEqual((tibet["before"], tibet["after"], tibet["delta"]), ("0.0", "0.0", "0.0"))
        self.assertIsNone(tibet["growth_pct"])
        self.assertIn("零", tibet["growth_note"])

    def test_forced_tie_rounding_and_negative_baseline(self):
        # Current releases have no tied end values or negative starting values in these measures.
        releases = [
            ({"江西": "32", "浙江": "8.0", "湖北": "-5"}, {}),
            ({"江西": "33.0", "浙江": "33.00", "湖北": "-4"}, {}),
        ]
        with patch("report_app.province_comparison._read_release", side_effect=releases):
            result = build_comparison(selection(regions=["浙江", "江西", "湖北"]))
        zhejiang, jx, hubei = result["rows"]
        self.assertEqual([(r["region"], r["rank"]) for r in result["rows"]], [("浙江", 1), ("江西", 1), ("湖北", 3)])
        self.assertEqual(zhejiang["delta"], "25.00")
        self.assertEqual(jx["growth_pct"], "3.13")
        self.assertIsNone(hubei["growth_pct"])
        self.assertIn("负", hubei["growth_note"])

    def test_each_period_uses_the_same_regions_and_its_own_ties(self):
        releases = [
            ({"江西": "10.0", "浙江": "10.00", "湖北": "9"}, {}),
            ({"江西": "7", "浙江": "12", "湖北": "7"}, {}),
        ]
        with patch("report_app.province_comparison._read_release", side_effect=releases):
            result = build_comparison(selection(regions=["湖北", "江西", "浙江"]))
        self.assertEqual([(r["region"], r["before_rank"], r["rank"]) for r in result["rows"]],
                         [("浙江", 1, 1), ("湖北", 3, 2), ("江西", 1, 2)])
        default = build_comparison(comparison_catalog()["default"])
        jx = next(r for r in default["rows"] if r["region"] == "江西")
        self.assertEqual((jx["before_rank"], jx["rank"]), (3, 3))

    def test_invalid_user_input_fails_before_reading(self):
        invalid = [
            None, [], {}, dict(selection(), unit="GW"), dict(selection(), after_year=2024),
            selection(["annual"]), selection("../../outside"), selection("three_quarters", "annual_total"),
            selection(metric={}), selection(metric="utilization"), selection(regions="湖北"),
            selection(regions=["北京"]), selection(regions=["北京"] * 33), selection(regions=["江西", "江西"]),
            selection(regions=["上海", []]), selection(regions=["China", "北京"]),
            selection(regions=["新疆兵团", "北京"]),
        ]
        with patch("report_app.province_comparison._read_release") as reader:
            for value in invalid:
                with self.subTest(value=value), self.assertRaises(AppError):
                    build_comparison(value)
            reader.assert_not_called()

    def test_changed_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "2025-h1.csv").write_text("地区,测试\n江西,999\n", encoding="utf-8")
            with patch("report_app.province_comparison.TABLE_DIR", Path(folder)):
                with self.assertRaisesRegex(AppError, "指纹"):
                    build_comparison(selection())
