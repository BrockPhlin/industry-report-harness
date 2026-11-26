"""Browser service contracts that the CLI and baseline tests do not cover."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from report_app.errors import AppError
from report_app import long_report, studies
from report_app.policy import POLICIES
from report_app.research import Research
from report_app.service import Service
from report_app.store import Store


class WebResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.research = Research(Service(Store(Path(self.tmp.name) / "test.db"), {}))
        self.addCleanup(self.research.pool.shutdown)
        self.data = {"question": "新增装机多少？", "focus": ["发电新增装机"], "mode": "fixture"}

    def completed_task(self):
        response = self.research.start(self.data)
        self.research.pool.shutdown(wait=True)
        return self.research.task(response["id"])

    def test_section_selection_and_history_survive_reload(self):
        row = self.completed_task()
        self.assertEqual(row["status"], "ready")
        self.assertFalse(row["approved"])
        self.assertIn("2.78", row["markdown"])
        self.assertNotIn("588", row["markdown"])
        self.assertEqual({e["section"] for e in row["events"]}, {"发电新增装机"})
        self.assertEqual(self.research.rows()[0]["id"], row["id"])
        with self.assertRaises(AppError):
            self.research.launch(row["id"])
        with self.assertRaises(AppError):
            self.research.ask(row["id"], {"question": "来源是哪里？"})

    def test_missing_key_never_runs_live_or_silently_switches_mode(self):
        self.assertIsNone(self.research.settings()["model"])
        with self.assertRaises(AppError) as ctx:
            self.research.start(dict(self.data, mode="live"))
        self.assertEqual(ctx.exception.code, "model_not_configured")
        self.assertEqual(self.research.rows(), [])

    def test_invalid_scope_rejected(self):
        for focus in ([], None, ["不存在"], ["发电新增装机"] * 2):
            with self.subTest(focus=focus), self.assertRaises(AppError):
                self.research.start(dict(self.data, focus=focus))

    def test_reference_selection_survives_edits_and_is_locked_when_writing(self):
        self.research.config.update(MODEL_NAME="fixture", MODEL_API_KEY="test-only",
                                    MODEL_ENDPOINT="https://example.invalid/chat")
        choice = ["pvps-china-2025", "stanford-ai-index-2026"]
        edit = dict(scope="中国光伏市场", target=1250, style="market", outline=["并网口径"])
        with patch.object(long_report, "discuss", return_value="先确定统计口径") as discuss:
            row = self.research.start(dict(question="口径如何比较？", workflow="discuss", reference_ids=choice))
            key = row["id"]
            self.assertEqual([r["id"] for r in discuss.call_args.kwargs["references"]], choice)
            self.research.revise_scope(key, edit)
            self.assertEqual(self.research.spec(key)["reference_ids"], choice)
            with self.assertRaises(AppError):
                self.research.revise_scope(key, dict(edit, reference_ids=["unknown"]))
            self.assertEqual(self.research.spec(key)["reference_ids"], choice)
            revised = self.research.revise_scope(key, {"reference_ids": []})["spec"]
            self.assertEqual({k: revised[k] for k in edit}, edit)
            self.research.plan_turn(key, {"question": "确认范围"})
            self.assertEqual(discuss.call_args.kwargs["references"], [])
        with patch.object(self.research, "launch"):
            self.research.begin(key)
            with self.assertRaises(AppError):
                self.research.revise_scope(key, dict(edit, reference_ids=choice))

    def test_industry_choice_can_add_in_scope_retrieval_but_not_widen_it(self):
        plan = dict(title="市场概况", regions=["China"], start=2025, end=2025, keywords=[],
                    industry_reference_ids=["pvps-china-2025", "stanford-ai-index-2026"])
        self.assertEqual([job[3] for job in studies.jobs(plan)], [studies.STUDIES[1].landing])
        self.assertEqual(studies.jobs(dict(plan, regions=["Germany"])), [])
        self.assertEqual(studies.jobs(dict(plan, start=2026, end=2026)), [])
        self.assertEqual(studies.jobs(dict(plan, industry_reference_ids=[])), [])

    def test_library_identifies_documents_by_origin_and_reopens_passages(self):
        library = self.research.library
        ref = studies.STUDIES[0]
        proof = [("测试页码", "测试摘记。")]
        observations = [("China", 2025, "测试指标", "GW", "8")]
        expected = {}
        for url, obs, kind in ((POLICIES[0].url, [], "policy"), (ref.landing, observations, "study"),
                               ("https://example.invalid/table", observations, "data"),
                               ("https://example.invalid/notice", [], "release")):
            key, _ = library.ingest(url, "任意标题", "同一发布者", url, lambda raw: (obs, proof),
                                    loader=lambda url: b"fixture")
            expected[key] = kind
            self.assertEqual(library.passages(key), [dict(locator=proof[0][0], text=proof[0][1])])
        sources = library.summary()["sources"]
        self.assertEqual({s["id"]: s["kind"] for s in sources}, expected)
        with self.assertRaises(AppError) as missing:
            library.passages(max(expected) + 1)
        self.assertEqual(missing.exception.status, 404)

    def test_error_is_persistent_and_safe_to_display(self):
        with patch("pv_brief.create_run", side_effect=RuntimeError("private diagnostic detail")):
            row = self.completed_task()
        self.assertEqual(row["status"], "failed")
        self.assertNotIn("private", json.dumps(row))
