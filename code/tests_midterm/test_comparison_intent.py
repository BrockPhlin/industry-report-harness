"""Only unambiguous user requests should select the offline comparison tool."""

import unittest

from report_app.comparison_intent import infer_comparison
from report_app.province_comparison import build_comparison


class ComparisonIntentTests(unittest.TestCase):
    def test_natural_queries_select_all_three_windows(self):
        examples = [
            ("比较 2025 年和 2026 年上半年江西、湖北的集中式光伏新增并网容量。", "half_year", "central_new", ["江西", "湖北"]),
            ("请将浙江省与江苏省在 2024、2025 年底的光伏累计并网装机容量排序。", "annual", "total_stock", ["浙江", "江苏"]),
            ("2025—2026 年 1 月至 9 月，西藏、青海户用分布式光伏新增并网容量相差多少？", "three_quarters", "household_new", ["西藏", "青海"]),
            ("对比２０２５年和２０２６年截至９月底的江苏、江西分布式光伏累计并网容量。", "three_quarters", "distributed_stock", ["江苏", "江西"]),
            ("江苏和浙江的光伏新增并网容量从2024到2025全年有何变化？写2000字。", "annual", "total_new", ["江苏", "浙江"]),
            ("比较江西、湖北和浙江在2025年和2026年上半年的集中式光伏新增并网容量，计算差额并排名。", "half_year", "central_new", ["江西", "湖北", "浙江"]),
        ]
        for q, period, metric, regions in examples:
            with self.subTest(question=q):
                parsed = infer_comparison(q)
                self.assertEqual(parsed, dict(period=period, metric=metric, regions=regions))
                self.assertEqual(build_comparison(parsed)["plan"]["metric"], metric)

    def test_user_scope_may_supply_dates_regions_and_measure(self):
        self.assertEqual(
            infer_comparison("帮我做两省光伏并网容量对比。", "浙江、江苏；2025年和2026年上半年的新增容量",
                             ["数据出处", "浙江与江苏两期变化"]),
            dict(period="half_year", metric="total_new", regions=["浙江", "江苏"]),
        )

    def test_all_provinces_and_corps(self):
        annual = "比较2024和2025年全国各省全年集中式光伏新增并网容量"
        all_regions = infer_comparison(annual)["regions"]
        self.assertEqual(len(all_regions), 31)
        self.assertNotIn("新疆兵团", all_regions)
        self.assertNotIn("China", all_regions)
        with_corps = infer_comparison(annual + "，也单列新疆生产建设兵团")["regions"]
        self.assertEqual(len(with_corps), 32)
        self.assertIn("新疆兵团", with_corps)
        named = infer_comparison(annual.replace("全国各省", "新疆生产建设兵团与新疆"))
        self.assertEqual(named["regions"], ["新疆兵团", "新疆"])
        for group in ("中国全国", "全国合计", "全国与湖北", "全国各省（不含湖北）"):
            self.assertIsNone(infer_comparison(annual.replace("全国各省", group)))
        self.assertIsNone(infer_comparison("比较2025及2026年上半年新疆兵团和湖北光伏新增并网容量"))

    def test_no_silent_coercion_of_time_measure_or_geography(self):
        template = "比较{years}年{when}，{where}的{measure}"
        defaults = dict(years="2025、2026", when="上半年", where="江西、湖北", measure="集中式光伏新增并网容量")
        changes = {
            "years": ["2026", "2024、2026", "2024至2026", "2024、2025、2026", "2025及2027"],
            "when": ["", "第三季度", "Q3", "一季度和上半年", "全年与上半年", "1至6月和7月", "上半年与前三季度"],
            "where": ["江西", "全国", "江浙地区", "江西、湖北等地", "江西、湖北和美国"],
            "measure": ["光伏新增装机数量", "光伏并网容量", "光伏发电量", "风电新增并网容量",
                        "光伏新增和累计并网容量", "集中式与分布式光伏新增并网容量", "企业光伏新增并网容量",
                        "光伏制造产量和新增并网容量", "预测光伏新增并网容量", "光伏新增并网容量占比",
                        "光伏新增并网容量的增速排名"],
        }
        for field, values in changes.items():
            for value in values:
                q = template.format(**(defaults | {field: value}))
                with self.subTest(question=q):
                    self.assertIsNone(infer_comparison(q))

    def test_outline_does_not_invent_missing_scope_and_can_reveal_conflicts(self):
        q = "比较2025、2026年上半年江西与湖北的集中式光伏新增并网容量"
        for missing in ("比较", "2025、", "上半年", "与湖北", "新增"):
            self.assertIsNone(infer_comparison(q.replace(missing, ""), outline=[q]))
        for heading in ("增加浙江比较", "先锋企业排名", "2023年历史表现", "全年新增量", "累计容量", "分布式光伏"):
            self.assertIsNone(infer_comparison(q, outline=[heading]))
        self.assertEqual(infer_comparison(q, outline=["研究范围", "江西和湖北两期数据", "统计口径"]),
                         infer_comparison(q))
        self.assertIsNone(infer_comparison(q.replace("比较", "不要比较")))
        self.assertIsNone(infer_comparison(q, scope="也请比较全年。"))
        self.assertIsNone(infer_comparison(q, scope="改为只比较江苏、浙江。"))

    def test_malformed_fields(self):
        for question, scope, outline in [(None, "", []), ("", "比较", []), ("比较", {}, []), ("比较", "", "江苏"), ("比较", "", [3])]:
            self.assertIsNone(infer_comparison(question, scope, outline))
