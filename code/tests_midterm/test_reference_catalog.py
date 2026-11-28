import json
import unittest

from report_app.reference_catalog import catalog, selected_reports
from report_app.studies import STUDIES


class ReferenceCatalogTests(unittest.TestCase):
    def test_industry_records_match_pinned_studies_and_method_cards_have_official_sources(self):
        cards = catalog()
        by_id = {card["id"]: card for card in cards}
        self.assertEqual(len(by_id), len(cards))
        for study in STUDIES:
            card = by_id[study.key]
            self.assertEqual((card["role"], card["title"], card["publisher"], card["url"]),
                             ("industry", study.title, study.publisher, study.landing))
        self.assertEqual({card["id"] for card in cards if card["role"] == "method"},
                         {"stanford-ai-index-2026", "mckinsey-trends-2026"})
        self.assertTrue(by_id["stanford-ai-index-2026"]["url"].startswith("https://hai.stanford.edu/"))
        self.assertTrue(by_id["mckinsey-trends-2026"]["url"].startswith("https://www.mckinsey.com/"))
        self.assertIn("图 S3", by_id["irena-cost-2025"]["sections"][1]["locator"])
        self.assertEqual(by_id["pvps-china-2025"]["year"], 2026)
        for card in cards:
            self.assertEqual(set(card), {"id", "title", "publisher", "year", "role", "topics", "summary", "sections", "url"})
            self.assertTrue(all(isinstance(t, str) and t for t in card["topics"]))
            self.assertTrue(card["summary"] and card["sections"])
            for section in card["sections"]:
                self.assertEqual(set(section), {"locator", "lesson"})
                self.assertTrue(section["lesson"])
                self.assertIn("页", section["locator"])
        self.assertEqual(json.loads(json.dumps(cards)), cards)

    def test_selected_order_empty_and_caller_mutation(self):
        keys = ["mckinsey-trends-2026", "pvps-china-2025"]
        self.assertEqual(selected_reports([]), [])
        cards = selected_reports(keys)
        self.assertEqual([c["id"] for c in cards], keys)
        cards[0]["sections"].clear()
        self.assertTrue(selected_reports(keys)[0]["sections"])
        cards = catalog()
        cards[0]["topics"].clear()
        self.assertTrue(catalog()[0]["topics"])

    def test_rejects_bad_ids_without_partially_applying_a_selection(self):
        key = "pvps-trends-2026"
        for value in [None, key, (key,), {}, [key, "missing"], [key, key], [True], [{}], [["id"]], ["../report"], [key] * 6]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                selected_reports(value)
