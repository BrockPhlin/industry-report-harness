"""HTTP, model adapter and database compatibility checks for the research workspace."""
from contextlib import closing, contextmanager
from io import BytesIO
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from report_app.errors import AppError
from report_app.generator import chat_completion, model_connection
from report_app.long_report import answer
from report_app.research import Research
from report_app.server import make_server
from report_app.service import Service, text_field
from report_app.store import Store


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "app.sqlite3")

    def open_workspace(self):
        research = Research(Service(self.store, {}))
        self.addCleanup(research.pool.shutdown)
        return research

    def test_new_workspace_creates_only_current_tables(self):
        self.assertEqual(self.open_workspace().rows(), [])
        with closing(self.store.connect()) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"research", "long_jobs", "solar_sources", "solar_observations"} <= tables)
        self.assertTrue({"sources", "reports"}.isdisjoint(tables))

    def test_existing_opening_rows_remain_readable_when_opening_workspace(self):
        with closing(self.store.connect()) as db, db:
            db.executescript("""
                CREATE TABLE sources (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, publisher TEXT NOT NULL,
                    published_at TEXT NOT NULL, url TEXT NOT NULL, body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE reports (
                    id TEXT PRIMARY KEY, topic TEXT NOT NULL, mode TEXT NOT NULL,
                    markdown TEXT NOT NULL, sources_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                INSERT INTO sources VALUES ('original','资料','机构','2025','','原文','2025');
                INSERT INTO reports VALUES ('history','题目','excerpt','历史稿','["original"]','[]','2025');
            """)
            original_source = tuple(db.execute("SELECT * FROM sources").fetchone())
            original_report = tuple(db.execute("SELECT * FROM reports").fetchone())
        self.assertEqual(self.open_workspace().rows(), [])
        with closing(self.store.connect()) as db:
            self.assertEqual(tuple(db.execute("SELECT * FROM sources").fetchone()), original_source)
            self.assertEqual(tuple(db.execute("SELECT * FROM reports").fetchone()), original_report)

    def test_research_text_fields_validate_type_and_length(self):
        self.assertEqual(text_field({"scope": " 光伏 "}, "scope", 2, True), "光伏")
        for value in (None, " ", "光伏报告"):
            with self.subTest(value=value), self.assertRaises(AppError):
                text_field({"scope": value}, "scope", 2, True)


class ModelAdapterTests(unittest.TestCase):
    config = dict(MODEL_ENDPOINT="https://example.invalid/v1/chat/completions",
                  MODEL_NAME="test-model", MODEL_API_KEY="test-only")

    def test_unconfigured_model_reports_missing_configuration(self):
        with self.assertRaises(AppError) as ctx:
            model_connection({})
        self.assertEqual(ctx.exception.code, "model_not_configured")

    def test_adapter_preserves_messages_and_records_reported_usage(self):
        messages = [{"role": "user", "content": "分析光伏产量"}]

        @contextmanager
        def fake(request, timeout):
            self.assertEqual(json.loads(request.data), {"model": "test-model", "messages": messages})
            self.assertEqual(timeout, 15)
            yield BytesIO(json.dumps({
                "choices": [{"message": {"content": "草稿"}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 2},
            }).encode())

        choice = chat_completion(model_connection(self.config), messages, fake, request_timeout=15)
        self.assertEqual(choice["message"]["content"], "草稿")
        self.assertEqual(choice["usage"], {"total_tokens": 2})

    def test_provider_error_body_is_not_exposed(self):
        def fake(request, timeout):
            raise HTTPError("https://secret.invalid", 401, "sensitive-detail", {}, BytesIO(b"secret-key"))
        with self.assertRaises(AppError) as ctx:
            chat_completion(model_connection(self.config), [], fake)
        self.assertIn("401", str(ctx.exception))
        self.assertNotIn("secret", str(ctx.exception))

    def test_truncated_output_is_rejected(self):
        @contextmanager
        def fake(request, timeout):
            yield BytesIO(b'{"choices":[{"message":{"content":"partial"},"finish_reason":"length"}]}')
        with self.assertRaises(AppError) as ctx:
            chat_completion(model_connection(self.config), [], fake)
        self.assertEqual(ctx.exception.code, "model_output_truncated")

    def test_filtered_output_is_rejected_by_research_writer(self):
        for content in ("partial", None):
            response = {"message": {"content": content}, "finish_reason": "content_filter"}
            with self.subTest(content=content), patch("report_app.long_report.chat_completion", return_value=response):
                with self.assertRaises(AppError) as ctx:
                    answer(self.config, "test", {})
                self.assertEqual(ctx.exception.code, "model_reply_filtered")


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = Service(Store(Path(self.tmp.name) / "test.sqlite3"), {})
        self.server = make_server(self.service, port=0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.tmp.cleanup()

    def request(self, path, data=None, headers=None):
        req = Request(self.base + path, data=None if data is None else json.dumps(data).encode(),
                      headers={"Content-Type": "application/json", **(headers or {})})
        return urlopen(req, timeout=5)

    def test_research_home_and_health(self):
        with self.request("/api/health") as r:
            self.assertTrue(json.load(r)["harness"])
        with self.request("/") as r:
            self.assertIn("产业研究工作台", r.read().decode())

    def test_demo_facts_and_archived_model_samples(self):
        with self.request("/api/research/settings") as response:
            settings = json.load(response)
        facts = {row["id"]: row for row in settings["fixture_facts"]}
        self.assertEqual(set(facts), {"pv-module-output", "pv-module-price", "pv-new-capacity"})
        self.assertEqual({row["source"] for row in facts.values()},
                         {row["id"] for row in settings["sources"]})
        self.assertNotEqual(facts["pv-module-output"]["unit"], facts["pv-new-capacity"]["unit"])
        for path in ["/samples/2024-full.pdf", "/samples/2024-missing.pdf"]:
            with self.subTest(path=path), self.request(path) as response:
                self.assertEqual(response.headers.get_content_type(), "application/pdf")
                self.assertEqual(response.read(5), b"%PDF-")
        with self.assertRaises(HTTPError) as ctx:
            self.request("/samples/2025-full.pdf")
        self.assertEqual(ctx.exception.code, 404)

    def test_cross_site_post_rejected_without_writes(self):
        with self.assertRaises(HTTPError) as ctx:
            self.request("/api/research", {"question": "x"}, {"Origin": "https://other.invalid"})
        self.assertEqual(ctx.exception.code, 403)
        with self.request("/api/research") as response:
            self.assertEqual(json.load(response), [])

    def test_opening_routes_are_retired_and_do_not_create_records(self):
        for path in ("/api/sources", "/api/reports"):
            for payload in (None, {"title": "原文", "body": "验证资料"}):
                with self.subTest(path=path, payload=payload), self.assertRaises(HTTPError) as ctx:
                    self.request(path, payload)
                self.assertEqual(ctx.exception.code, 404)
        with self.request("/api/research") as response:
            self.assertEqual(json.load(response), [])

    def test_research_details_reject_extra_or_empty_path_segments(self):
        task = "0" * 32
        for path in (f"/api/research/extra/{task}", f"/api/research//{task}", f"/api/research/{task}/", "/api/research/"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as ctx:
                self.request(path)
            self.assertEqual(ctx.exception.code, 404)

    def test_static_paths_are_allowlisted(self):
        for path in ["/../run.py", "/.env", "/api/reports/missing/unknown", "/baseline", "/app.js", "/style.css"]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as ctx:
                self.request(path)
            self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
