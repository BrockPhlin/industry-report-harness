"""Browser service contracts that the CLI and baseline tests do not cover."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from report_app.errors import AppError
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

    def test_error_is_persistent_and_safe_to_display(self):
        with patch("pv_brief.create_run", side_effect=RuntimeError("private diagnostic detail")):
            row = self.completed_task()
        self.assertEqual(row["status"], "failed")
        self.assertNotIn("private", json.dumps(row))
