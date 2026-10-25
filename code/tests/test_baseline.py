"""Actual local baseline tests, not industry-quality or live model evidence."""
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from report_app.errors import AppError
from report_app.generator import model_report, read_config
from report_app.server import make_server
from report_app.service import Service
from report_app.store import Store


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "app.sqlite3"
        self.app = Service(Store(self.db), {})

    def source(self, title="真实输入样例", body="用户提供的原文。\n第二段原文。"):
        return self.app.add_source(dict(title=title, body=body, publisher="测试机构"))

    def test_source_and_report_survive_store_reopen(self):
        source = self.source()
        report = self.app.generate(dict(topic="测试主题", source_ids=[source["id"]]))
        reopened = Store(self.db)
        self.assertEqual(reopened.get_source(source["id"])["body"], source["body"])
        self.assertIn("[S1]", reopened.get_report(report["id"])["markdown"])
        self.assertEqual(reopened.get_report(report["id"])["sources"][0], source)

    def test_citation_order_tracks_requested_sources(self):
        first = self.source("甲", "甲的原文")
        second = self.source("乙", "乙的原文")
        result = self.app.generate(dict(topic="顺序", source_ids=[second["id"], first["id"]]))
        self.assertEqual([s["title"] for s in result["sources"]], ["乙", "甲"])
        self.assertIn("> 乙的原文\n> [S1]", result["markdown"])
        self.assertIn("> 甲的原文\n> [S2]", result["markdown"])

    def test_bad_input_and_unknown_source_leave_no_reports(self):
        for data in [{"topic": "", "source_ids": ["missing"]},
                     {"topic": "test", "source_ids": []},
                     {"topic": "test", "source_ids": ["missing", "missing"]},
                     {"topic": "test", "source_ids": ["missing"], "mode": []}]:
            with self.subTest(data=data), self.assertRaises(AppError):
                self.app.generate(data)
        with self.assertRaises(AppError) as ctx:
            self.app.generate(dict(topic="test", source_ids=["missing"]))
        self.assertEqual(ctx.exception.status, 404)
        self.assertEqual(self.app.store.list_reports(), [])

    def test_empty_source_rejected(self):
        with self.assertRaises(AppError):
            self.source(body="  ")
        self.assertEqual(self.app.store.list_sources(), [])

    def test_source_library_excludes_bodies_but_detail_preserves_them(self):
        sources = [self.source(f"构造资料{i}", "测" * 50000) for i in range(10)]
        summaries = self.app.store.list_sources()
        self.assertEqual([s["id"] for s in summaries], [s["id"] for s in sources])
        for summary, source in zip(summaries, sources):
            self.assertNotIn("body", summary)
            self.assertEqual(summary["body_length"], 50000)
            self.assertEqual({k: v for k, v in summary.items() if k != "body_length"},
                             {k: v for k, v in source.items() if k != "body"})
            self.assertEqual(self.app.store.get_source(source["id"]), source)
        # Bound transferred bytes for this fixture, not execution time.
        self.assertLess(len(json.dumps(summaries, ensure_ascii=False).encode()), 10000)
        report = self.app.generate(dict(topic="完整正文", source_ids=[sources[0]["id"]]))
        self.assertEqual(report["sources"][0]["body"], sources[0]["body"])
        self.assertIn(sources[0]["body"], report["markdown"])

    def test_source_character_count_includes_unicode_and_newlines(self):
        source = self.source(body="中文\nA😀e\u0301")
        self.assertEqual(self.app.store.list_sources()[0]["body_length"], len(source["body"]))

    def test_unconfigured_model_does_not_silently_fallback(self):
        source = self.source()
        with self.assertRaises(AppError) as ctx:
            self.app.generate(dict(topic="test", source_ids=[source["id"]], mode="model"))
        self.assertEqual(ctx.exception.code, "model_not_configured")
        self.assertEqual(self.app.store.list_reports(), [])

    def test_model_adapter_payload_and_unknown_citation_warning(self):
        source = self.source()
        calls = []

        @contextmanager
        def fake(request, timeout):
            calls.append(json.loads(request.data))
            yield BytesIO(json.dumps({"choices": [{"message": {"content": "草稿[S99]"}, "finish_reason": "stop"}]}).encode())

        config = dict(MODEL_ENDPOINT="https://example.invalid/v1/chat/completions", MODEL_NAME="test-model", MODEL_API_KEY="test-only")
        markdown, warnings = model_report("主题", [source], config, opener=fake)
        self.assertEqual(calls[0]["model"], "test-model")
        self.assertEqual(calls[0]["messages"][0]["role"], "system")
        sent = json.loads(calls[0]["messages"][1]["content"])
        self.assertEqual(sent["sources"][0]["body"], source["body"])
        self.assertTrue(any("超出" in x for x in warnings))
        self.assertIn("草稿[S99]", markdown)

    def test_provider_error_body_is_not_exposed(self):
        def fake(request, timeout):
            raise HTTPError("https://secret.invalid", 401, "sensitive-detail", {}, BytesIO(b"secret-key"))
        config = dict(MODEL_ENDPOINT="https://example.invalid/v1/chat/completions", MODEL_NAME="test", MODEL_API_KEY="secret-key")
        with self.assertRaises(AppError) as ctx:
            model_report("主题", [self.source()], config, opener=fake)
        self.assertIn("401", str(ctx.exception))
        self.assertNotIn("secret", str(ctx.exception))

    def test_truncated_model_output_is_not_saved_as_success(self):
        @contextmanager
        def fake(request, timeout):
            yield BytesIO(b'{"choices":[{"message":{"content":"partial"},"finish_reason":"length"}]}')
        config = dict(MODEL_ENDPOINT="https://example.invalid/chat", MODEL_NAME="test", MODEL_API_KEY="test")
        with self.assertRaises(AppError) as ctx:
            model_report("主题", [self.source()], config, opener=fake)
        self.assertEqual(ctx.exception.code, "model_output_truncated")

    def test_non_stop_model_output_is_rejected(self):
        @contextmanager
        def fake(request, timeout):
            yield BytesIO(json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "content_filter"}]}).encode())
        config = dict(MODEL_ENDPOINT="https://example.invalid/chat", MODEL_NAME="test", MODEL_API_KEY="test")
        for content in ["partial", None]:
            with self.subTest(content=content), self.assertRaises(AppError) as ctx:
                model_report("主题", [self.source()], config, opener=fake)
            self.assertEqual(ctx.exception.code, "model_output_incomplete")

    def test_json_safe_storage_and_source_snapshot(self):
        source = self.source(title="x'); DROP TABLE sources; --", body="<script>alert('x')</script>")
        report = self.app.generate(dict(topic="test", source_ids=[source["id"]]))
        self.assertEqual(self.app.store.get_report(report["id"])["sources"][0]["body"], source["body"])
        self.assertEqual(len(self.app.store.list_sources()), 1)


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

    def test_real_http_roundtrip_and_download(self):
        with self.request("/api/health") as r:
            self.assertEqual(json.load(r)["harness"], False)
        with self.request("/api/sources", {"title": "原文", "body": "验证资料"}) as r:
            source = json.load(r)
            self.assertEqual(r.status, 201)
        with self.request("/api/reports", {"topic": "测试", "source_ids": [source["id"]]}) as r:
            report = json.load(r)
        with self.request(f"/api/reports/{report['id']}/download") as r:
            self.assertIn("text/markdown", r.headers["Content-Type"])
            self.assertIn("验证资料", r.read().decode())
        with self.request("/") as r:
            self.assertIn("产业研究工作台", r.read().decode())

    def test_public_sample_to_download_keeps_distinct_metrics(self):
        sample = json.loads((Path(__file__).parents[1] / "examples/public-sources.json").read_text(encoding="utf-8"))
        ids = []
        for item in sample["sources"][:2]:
            with self.request("/api/sources", item) as response:
                ids.append(json.load(response)["id"])
        with self.request("/api/reports", {"topic": sample["topic"], "source_ids": ids}) as response:
            report = json.load(response)
        with self.request(f"/api/reports/{report['id']}/download") as response:
            markdown = response.read().decode("utf-8")
        self.assertIn("588GW", markdown)
        self.assertIn("2.78亿千瓦", markdown)
        self.assertIn("[S1]", markdown)
        self.assertIn("[S2]", markdown)
        self.assertEqual([s["id"] for s in report["sources"]], ids)

    def test_cross_site_post_rejected_without_writes(self):
        with self.assertRaises(HTTPError) as ctx:
            self.request("/api/sources", {"title": "x", "body": "x"}, {"Origin": "https://other.invalid"})
        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(self.service.store.list_sources(), [])

    def test_source_list_and_detail_http_contract(self):
        with self.request("/api/sources", {"title": "原文", "body": "完整证据😀"}) as r:
            source = json.load(r)
        with self.request("/api/sources") as r:
            summaries = json.load(r)
        self.assertEqual(summaries[0]["body_length"], len(source["body"]))
        self.assertNotIn("body", summaries[0])
        with self.request(f"/api/sources/{source['id']}") as r:
            self.assertEqual(json.load(r), source)

    def test_source_detail_rejects_extra_or_empty_path_segments(self):
        source = self.service.add_source({"title": "原文", "body": "完整证据"})
        for path in [f"/api/sources/extra/{source['id']}",
                     f"/api/sources//{source['id']}",
                     f"/api/sources/{source['id']}/", "/api/sources/"]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as ctx:
                self.request(path)
            self.assertEqual(ctx.exception.code, 404)

    def test_static_paths_are_allowlisted(self):
        for path in ["/../run.py", "/.env", "/api/reports/missing/unknown"]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as ctx:
                self.request(path)
            self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
