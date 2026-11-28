"""Selected reference notes guide the editor; only retrieved evidence can support claims."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from report_app import long_report as report
from report_app.errors import AppError
from report_app.reference_catalog import selected_reports
from report_app.writing_references import attach_notes, chapter_notes, notes_for_section


IDS = ["pvps-china-2025", "stanford-ai-index-2026"]
HEADINGS = ["期末并网规模", "地区口径"]
FACT = {
    "ref": "E1", "region": "China", "metric": "光伏并网容量", "unit": "", "series": [],
    "source": 1, "text": "公开原表将各地区的并网规模按统一的统计时点列示，用户可以按行对照。",
    "title": "光伏统计", "publisher": "国家能源局", "url": "https://www.nea.gov.cn/",
    "digest": "a" * 64, "locator": "表下注释",
}


class ArchivedRelease:
    def __init__(self):
        self.plans = []

    def collect(self, plan):
        self.plans.append(deepcopy(plan))
        return [deepcopy(FACT)], []


class WritingReferenceTests(unittest.TestCase):
    def test_writer_respects_empty_invalid_and_unmentioned_chapter_assignments(self):
        cards = selected_reports(IDS)
        notes = chapter_notes(cards)
        raw = dict(title="分省口径", regions=["China"], keywords=["光伏"], start=2024, end=2025, sections=HEADINGS)
        for mapping in ({HEADINGS[0]: []}, {HEADINGS[0]: ["unselected/1"]}, {}, "无效格式"):
            with patch.object(report, "answer", return_value=dict(raw, reference_sections=mapping)):
                plan = report.make_plan({}, "分省口径", "", [], 800, references=cards)
            for title in HEADINGS:
                self.assertEqual(notes_for_section(plan, title, notes), [])
        with patch.object(report, "answer", return_value=raw):
            legacy = report.make_plan({}, "分省口径", "", [], 800, references=cards)
        self.assertNotIn("reference_sections", legacy)
        self.assertEqual(notes_for_section(legacy, HEADINGS[0], notes), notes)

    def test_discussion_preserves_user_fields_and_empty_selection(self):
        cards = selected_reports(IDS)
        with patch.object(report, "answer", return_value="选择可比的统计口径。") as model:
            report.discuss({}, "比较各省", [], "沿用讨论范围", references=cards)
            _, prompt, payload = model.call_args.args
            self.assertIn("不可将其他行业的数字", prompt)
            self.assertEqual((payload["初始需求"], payload["本轮"]), ("比较各省", "沿用讨论范围"))
            self.assertIn(cards[1]["sections"][0]["locator"], str(payload["参考报告章节摘记"]))
            report.discuss({}, "比较各省", [], "沿用讨论范围")
            self.assertNotIn("参考报告章节摘记", model.call_args.args[2])

    def test_ordinary_writer_rejects_cross_domain_number_and_uses_only_retrieved_citation(self):
        cards = selected_reports(["stanford-ai-index-2026"])
        task = attach_notes({}, chapter_notes(cards))
        supported = "公开原表将各地区的并网规模按统一的统计时点列示，用户可以按行对照。"
        bad = "统计结果表明光伏并网规模的市场份额已经达到百分之二十，即20%。"
        responses = [
            {"paragraphs": [{"text": bad, "refs": ["E1"]}]},
            {"paragraphs": [{"text": supported, "refs": ["E1"]}]},
        ]
        with patch.object(report, "answer", side_effect=responses) as model:
            result = report.write_part({}, task, {}, [FACT], HEADINGS[0], report.length_of(supported), [], "research")
        self.assertEqual(result, [supported + " [E1]"])
        first_payload = model.call_args_list[0].args[2]
        self.assertIn(cards[0]["sections"][1]["locator"], str(first_payload["任务"]))
        self.assertEqual([e["ref"] for e in first_payload["证据"]], ["E1"])
        self.assertIn("20", model.call_args_list[1].args[2]["修订要求"])

    def test_anchor_fallback_receives_notes_but_anchor_keys_come_from_evidence(self):
        cards = selected_reports(["stanford-ai-index-2026"])
        task = attach_notes({}, chapter_notes(cards))
        analysis = "核对表头所用的单位，再比较同一栏中各地区的记录。"
        size = report.length_of(FACT["text"] + analysis)

        def model(_config, prompt, payload):
            if "可选事实" not in payload:
                return {"paragraphs": [{"text": "引用了参考报告的目录页码。", "refs": [cards[0]["id"]]}]}
            self.assertIn("摘记不提供本项目的事实证据", prompt)
            self.assertEqual(payload["任务"]["参考报告章节摘记"], task["参考报告章节摘记"])
            self.assertEqual({a["来源"] for a in payload["可选事实"].values()}, {"E1"})
            return {"paragraphs": [{"keys": ["K1"], "analysis": "当地占比为20%。" + analysis}]}

        with patch.object(report, "answer", side_effect=model) as calls:
            result = report.write_part({}, task, {}, [FACT], HEADINGS[0], size, [], "research")
        self.assertEqual(calls.call_count, 3)
        self.assertIn(analysis, result[0])
        self.assertNotIn("20%", result[0])
        self.assertTrue(result[0].endswith("[E1]"))

    def test_resume_uses_frozen_cards_with_chapter_specific_scope(self):
        first_notes = selected_reports(IDS)
        library = ArchivedRelease()
        spec = dict(checkpoint={}, scope="沿用分省统计口径", turns=[], target=800, outline=HEADINGS,
                    source_groups=["grid"], reference_ids=IDS, style="research")
        row = dict(id="example", question="怎样比较光伏并网情况？")
        received = []
        paused = []
        checkpoints = []

        def model(_config, prompt, payload, **kwargs):
            if "用户指定章名" in payload:
                self.assertEqual(payload["scope"], spec["scope"])
                self.assertIn("参考报告章节摘记", payload)
                return dict(title="分省并网口径比较", regions=["China"], keywords=["光伏", "并网"],
                            start=2025, end=2025, sections=["其他章名"], reference_sections={
                                HEADINGS[0]: [IDS[0] + "/1", "invented/4"],
                                HEADINGS[1]: [IDS[1] + "/2"], "其他章名": [IDS[1] + "/1"],
                            })
            if "指标与覆盖年度" in payload:
                self.assertNotIn("参考报告章节摘记", payload["研究任务"])
                return {"usable": True, "limits": []}
            if "篇幅" in payload:
                title = payload["本节"]
                received.append((title, [item["key"] for item in payload["任务"]["参考报告章节摘记"]]))
                if title == HEADINGS[1] and not paused:
                    paused.append(True)
                    raise AppError("人为模拟服务中断", 503, "model_unavailable")
                paragraph = FACT["text"] * 12
                return {"paragraphs": [{"text": paragraph, "refs": ["E1"]}]}
            if "段落" in payload:
                return {"edits": []}
            if "可选的原句" in payload:
                return {"selected": [1]}
            self.fail(str(payload.keys()))

        def save(checkpoint):
            checkpoints.append(json.loads(json.dumps(checkpoint, ensure_ascii=False)))

        with TemporaryDirectory() as folder, patch.object(report, "answer", side_effect=model):
            root = Path(folder)
            with self.assertRaisesRegex(AppError, "中断"):
                report.generate({}, library, root, row, spec, lambda msg: None, save)
            self.assertEqual(len(checkpoints[-1]["chapters"]), 1)
            spec["checkpoint"] = checkpoints[-1]
            with patch("report_app.reference_catalog.selected_reports", side_effect=AssertionError("重读目录")):
                report.generate({}, library, root, row, spec, lambda msg: None, save)
            trace = json.loads((root / row["id"] / "trace.json").read_text())
        self.assertEqual(received, [(HEADINGS[0], [IDS[0] + "/1"]),
                                    (HEADINGS[1], [IDS[1] + "/2"]), (HEADINGS[1], [IDS[1] + "/2"])])
        self.assertEqual(len(library.plans), 1)
        self.assertEqual(library.plans[0]["industry_reference_ids"], [IDS[0]])
        self.assertEqual(library.plans[0]["source_groups"], ["grid"])
        self.assertEqual(trace["plan"]["sections"], HEADINGS)
        self.assertEqual(trace["writing_references"], first_notes)
        self.assertEqual(trace["writing_notes_offered"], {HEADINGS[0]: [IDS[0] + "/1"], HEADINGS[1]: [IDS[1] + "/2"]})
        self.assertEqual([r["ref"] for r in trace["evidence"]], ["E1"])


if __name__ == "__main__":
    unittest.main()
