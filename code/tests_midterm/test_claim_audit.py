"""Regression cases for quantitative claims in the public PV report examples."""
import unittest

from report_app.claim_audit import audit_claims


def row(ref, metric, unit, series, region="China"):
    return dict(ref=ref, metric=metric, unit=unit, series=series, region=region, text="")


class ClaimAuditTests(unittest.TestCase):
    def test_original_unit_sign_period_and_explicit_year(self):
        data = [
            row("E1", "光伏电池产量（10月）", "万千瓦", [[2025, "6794"], [2026, "7310"]]),
            row("E2", "光伏电池产量同比（10月）", "%", [[2026, "-1.3"]]),
        ]
        cases = [
            ("2026年10月，全国光伏电池产量为7,310万千瓦，同比下降1.3%。", "matched"),
            ("2026年10月，全国光伏电池产量为6794万千瓦。", "mismatch"),
            ("2026年1—10月，全国光伏电池产量为7310万千瓦。", "mismatch"),
            ("2026年10月，全国光伏电池产量为7310亿千瓦时。", "mismatch"),
            ("2026年10月，全国光伏电池产量同比增长1.3%。", "mismatch"),
        ]
        for sentence, expected in cases:
            with self.subTest(sentence=sentence):
                claim = audit_claims(sentence + " [E1] [E2]", data)["claims"][0]
                self.assertEqual(claim["status"], expected)

    def test_paragraph_citations_and_inline_citation_boundaries(self):
        data = [row("E1", "新增装机", "GWdc", [[2025, "415"]]), row("E2", "新增装机", "GWac", [[2025, "316.574"]])]
        text = "2025年新增415 GWdc。2025年新增316.574 GWac。 [E1] [E2]"
        self.assertEqual(audit_claims(text, data)["summary"]["matched"], 2)
        text = "2025年新增415 GWdc。 [E2] 2025年新增316.574 GWac。 [E2]"
        first, second = audit_claims(text, data)["claims"]
        self.assertEqual((first["status"], first["refs"]), ("mismatch", ["E2"]))
        self.assertEqual((second["status"], second["refs"]), ("matched", ["E2"]))

    def test_month_end_snapshot_and_province(self):
        data = [row("E1", "集中式光伏截至六月底累计并网容量", "万千瓦", [[2026, "1358.3"]], "江西")]
        for region, expected in (("江西", "matched"), ("湖北", "mismatch")):
            claim = audit_claims(f"截至2026年6月底，{region}集中式光伏累计并网容量为1358.3万千瓦。 [E1]", data)["claims"][0]
            self.assertEqual(claim["status"], expected)

    def test_cumulative_month_progression_needs_review(self):
        data = [row(f"E{m}", f"规模以上工业太阳能发电量同比（1—{m}月）", "%", [[2026, v]])
                for m, v in ((3, "9.8"), (6, "12.3"), (7, "11.4"), (10, "14.3"))]
        text = "累计同比在上半年从9.8%缓慢升至12.3%，7月回落至11.4%，1—10月回升至14.3%。 [E3] [E6] [E7] [E10]"
        item = audit_claims(text, data)["claims"][0]
        self.assertEqual([q["status"] for q in item["checks"]], ["review", "review", "review", "matched"])

    def test_ordered_comparison_cannot_silently_cross_match(self):
        data = [row("E1", "新增装机", "GW", [[2025, "415"]]), row("E2", "新增装机", "GW", [[2025, "10"]], "Germany")]
        text = "中国与德国的新增装机分别为10 GW与415 GW。 [E1] [E2]"
        self.assertTrue(all(c["status"] == "review" for c in audit_claims(text, data)["claims"][0]["checks"]))
        series = [row("E1", "新增装机", "GW", [[2025, "415"], [2026, "410"]])]
        claim = audit_claims("2025、2026年分别为410 GW与415 GW。 [E1]", series)["claims"][0]
        self.assertTrue(all(c["status"] == "review" for c in claim["checks"]))

    def test_missing_evidence_policy_and_interpretation_require_review(self):
        data = [dict(ref="E1", text="自2027年4月1日起，对光伏电池按照2%税率征收消费税。")]
        for sentence in ("2027年适用2%的消费税税率。 [E1]", "政策导致需求增长。 [E1]", "适用2%税率。", "适用2%税率。 [E999]"):
            with self.subTest(sentence=sentence):
                self.assertEqual(audit_claims(sentence, data)["summary"]["review"], 1)

    def test_metric_confusion_and_unsupported_ranking(self):
        data = [row("E1", "IRENA新投运公用事业级光伏平准化发电成本", "美元/MWh", [[2025, "36"]])]
        price = "2025年中国光伏电站售电成交价为36美元/MWh。 [E1]"
        rank = "2025年中国光伏的平准化发电成本仅为36美元/MWh，连续两年全球最低。 [E1]"
        self.assertEqual(audit_claims(price, data)["claims"][0]["status"], "mismatch")
        self.assertEqual(audit_claims(rank, data)["claims"][0]["status"], "review")

    def test_sources_and_tables_are_not_narrative_claims(self):
        data = [row("E1", "新增装机", "GW", [[2025, "410"]])]
        md = "# 研究报告\n\n运行方式：联网研究。\n\n## 装机\n\n装机为410 GW。 [E1]\n\n## 数据附表\n\n| 2025 | 999 GW |\n\n## 资料来源\n\n[E1](https://example.org)"
        claims = audit_claims(md, data)["claims"]
        self.assertEqual([(c["id"], c["section"], c["refs"]) for c in claims], [("C1", "装机", ["E1"])])


if __name__ == "__main__":
    unittest.main()
