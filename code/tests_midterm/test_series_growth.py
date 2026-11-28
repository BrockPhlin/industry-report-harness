"""Regression from a report that cited both Chinese PV additions and year-end stock."""
import unittest

from report_app.claim_audit import audit_claims
from report_app.errors import AppError
from report_app.long_report import assemble, validate_draft
from report_app.report_review import check_edited_paragraph
from report_app.series_growth import growth_issues, repair_growth
from report_app.solar_data import trend


def record(ref, metric, first, last, unit="GWdc", years=(2024, 2025)):
    series = list(zip(years, (str(first), str(last))))
    return {
        "ref": ref, "metric": metric, "unit": unit, "region": "China", "series": series,
        "raw_series": series, "title": "IEA PVPS《2026 年光伏应用趋势》", "locator": metric,
        "publisher": "IEA PVPS", "url": "https://iea-pvps.org/trends_reports/trends-2026/", "digest": "a" * 64,
        "text": f"{metric}：{years[0]}年 {first} {unit}；{years[1]}年 {last} {unit}。" + trend(series, unit),
    }


EVIDENCE = [
    record("E1", "IEA PVPS光伏年度新增装机（直流侧）", 357, 415),
    record("E2", "IEA PVPS光伏年末累计装机（直流侧）", 1049, 1464),
]
OBSERVATIONS = "中国2024年、2025年新增分别为357 GWdc与415 GWdc，年末累计分别为1049 GWdc与1464 GWdc"
WRONG = OBSERVATIONS + "，2024至2025年累计增长16.2%。"
CORRECT = OBSERVATIONS + "，2024至2025年累计增长39.6%。"


class SeriesGrowthTests(unittest.TestCase):
    def test_swapped_end_to_end_growth_gets_own_denominator(self):
        issues = growth_issues(WRONG, EVIDENCE)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].refs, ("E2",))
        self.assertEqual(repair_growth(WRONG, EVIDENCE), CORRECT)
        self.assertEqual(repair_growth(CORRECT, EVIDENCE), CORRECT)
        audit = audit_claims(WRONG + " [E1] [E2]", EVIDENCE)
        self.assertEqual((audit["claims"][0]["status"], audit["claims"][0]["checks"][-1]["refs"]), ("mismatch", ["E2"]))

    def test_genuine_change_in_annual_additions_remains_intact(self):
        for text in (OBSERVATIONS + "，同期新增装机增长16.2%。", "中国新增从357增至415 GWdc，期间增速为16.2%。"):
            self.assertEqual(repair_growth(text, EVIDENCE), text)

    def test_ambiguous_rate_removed_original_observations_retained(self):
        text = OBSERVATIONS + "，两者均增长16.2%。"
        self.assertEqual(repair_growth(text, EVIDENCE), OBSERVATIONS + "。")

    def test_editor_cannot_move_existing_percentages_between_series(self):
        original = "新增装机从357升至415 GWdc，增长16.2%；累计装机从1049升至1464 GWdc，增长39.6%。 [E1] [E2]"
        edited = original.replace("16.2%", "临时").replace("39.6%", "16.2%").replace("临时", "39.6%")
        with self.assertRaises(AppError):
            check_edited_paragraph(original, edited, EVIDENCE)

    def test_does_not_relabel_other_percentage_concepts(self):
        for tail in ("年均增长16.2%", "复合增长率为16.2%", "CAGR为16.2%", "市场份额为16.2%",
                     "官方同比增长16.2%", "LCOE下降16.2%", "累计增长16.2%-39.6%",
                     "累计增长16.2%至39.6%", "2020至2022年累计增长16.2%", "份额上升16.2个百分点"):
            with self.subTest(tail=tail):
                content = OBSERVATIONS + "，" + tail + "。"
                self.assertEqual(repair_growth(content, EVIDENCE), content)
        shares = [record("E3", "光伏电量占比", 3, 8, "%")]
        text = "占比从3%升至8%，变化5个百分点。"
        self.assertEqual(repair_growth(text, shares), text)

    def test_no_uncited_or_unverifiable_rate_is_inserted(self):
        for refs in ([EVIDENCE[0]], [dict(EVIDENCE[1], text="没有已算过的期间变化")],
                     [record("E2", "累计装机", 0, 1464)]):
            self.assertEqual(repair_growth(WRONG, refs), WRONG)

    def test_new_draft_and_resumed_body_and_summary_receive_same_fix(self):
        draft = validate_draft({"paragraphs": [{"text": WRONG, "refs": ["E1", "E2"]}]},
                               {r["ref"]: r for r in EVIDENCE}, 1, 300)
        self.assertEqual(draft[0], CORRECT + " [E1] [E2]")
        plan = dict(title="装机口径对照", start=2024, end=2025, regions=["China"],
                    keywords=["装机"], sections=["新增与年末累计"], source_groups=[])
        old = WRONG + " [E1] [E2]"
        md, trace = assemble(plan, EVIDENCE, [], [[old]], [old], [], 800, "research")
        self.assertEqual(md.count(CORRECT), 2)
        self.assertNotIn(WRONG, md)
        self.assertEqual(trace["protected_lines"].count(CORRECT + " [E1] [E2]"), 2)


if __name__ == "__main__":
    unittest.main()
