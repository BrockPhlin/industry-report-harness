"""End-to-end checks for a reusable brief, uncertain evidence and HTTP recovery."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest

from report_app.pv_evidence import CODE_DIR


CONFLICT = Path(__file__).parent / "fixtures/pv-conflict.json"
WIND = ("--template", CODE_DIR / "templates/wind-brief.json",
        "--corpus", CODE_DIR / "examples/wind-2024.json")


def cli(*args, env=None):
    return subprocess.run([sys.executable, str(CODE_DIR / "pv_brief.py"), *map(str, args)],
                          capture_output=True, text=True, env=env, timeout=20)


class FinalOptionsTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("typst"), "requires Typst for PDF export")
    def test_conflicting_figures_are_unresolved_and_protected_on_export(self):
        with TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            run = cli("run", job, "--mode", "fixture", "--corpus", CONFLICT)
            self.assertEqual(run.returncode, 0, run.stderr)
            trace = json.loads(cli("inspect", job, "--json").stdout)
            section = trace["events"][-1]
            self.assertEqual(section["selected"], [])
            self.assertEqual(section["missing"], [])
            self.assertEqual(section["conflicts"], ["pv-new-capacity"])
            self.assertEqual(section["observation_status"], "omitted_conflict")
            self.assertEqual({row["source"] for row in trace["events"][-2]["returned"]},
                             {"NEA", "TEST-CONFLICT"})

            original = (job / "draft.md").read_text(encoding="utf-8")
            self.assertIn("暂不采用任何候选值", original)
            self.assertIn("2.78 亿千瓦 [NEA]", original)
            self.assertIn("2.80 亿千瓦 [TEST-CONFLICT]", original)
            altered = Path(tmp) / "altered.md"
            altered.write_text(original.replace("2.80 亿千瓦", "2.78 亿千瓦"), encoding="utf-8")
            self.assertNotEqual(cli("approve", job, "--confirm", "--markdown", altered).returncode, 0)
            approved = cli("approve", job, "--confirm")
            self.assertEqual(approved.returncode, 0, approved.stderr)
            self.assertTrue((job / "reviewed/brief.pdf").read_bytes().startswith(b"%PDF"))
            reviewed = (job / "reviewed/brief.md").read_text(encoding="utf-8")
            self.assertIn("仍有待核实项", reviewed)
            self.assertIn("测试夹具第1条合成记录", reviewed)
            self.assertIn("（三）光伏发电建设和运行情况", reviewed)

            agree = Path(tmp) / "agree.json"
            data = json.loads(CONFLICT.read_text(encoding="utf-8"))
            data["facts"][-1]["value"] = "2.78"
            agree.write_text(json.dumps(data), encoding="utf-8")
            lookup = cli("evidence", "pv-new-capacity", "--corpus", agree)
            hit = json.loads(lookup.stdout)["pv-new-capacity"]
            self.assertEqual(hit["source"], "NEA")
            self.assertNotIn("alternatives", hit)

    @unittest.skipUnless(shutil.which("typst"), "requires Typst for PDF export")
    def test_wind_case_uses_only_new_template_and_corpus(self):
        with TemporaryDirectory() as tmp:
            job = Path(tmp) / "wind"
            run = cli("run", job, "--mode", "fixture", *WIND)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = (job / "draft.md").read_text(encoding="utf-8")
            self.assertIn("## 装机与并网", report)
            for figure in ("7982 万千瓦", "5.21 亿千瓦", "9916 亿千瓦时"):
                self.assertIn(f"{figure} [NEA-WIND]", report)
            self.assertNotIn("光伏", report)
            approved = cli("approve", job, "--confirm")
            self.assertEqual(approved.returncode, 0, approved.stderr)
            self.assertTrue((job / "reviewed/brief.pdf").read_bytes().startswith(b"%PDF"))

    @unittest.skipUnless(shutil.which("typst"), "requires Typst for PDF export")
    def test_socket_read_timeout_recovers_and_does_not_redo_first_chapter(self):
        requests = []
        first_chapter_writes = []
        timed_out = Event()
        unblock = Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                messages = request["messages"]
                chapter = json.loads(messages[1]["content"])
                keys = list(chapter["required"])
                action = "query" if "tools" in request else "write"
                requests.append((chapter["title"], action))
                if action == "query":
                    call = {"id": "lookup", "type": "function", "function": {
                        "name": "search_evidence", "arguments": json.dumps({"keys": keys})}}
                    choice = {"finish_reason": "tool_calls", "message": {"tool_calls": [call]}}
                else:
                    initial = json.loads(messages[-2]["content"])
                    supplement = json.loads(messages[-1]["content"].split("\n补查命中：", 1)[1])
                    if chapter["title"] == "制造与价格":
                        first_chapter_writes.append(list(initial | supplement))
                    choice = {"finish_reason": "stop", "message": {
                        "content": json.dumps({"selected": list(initial | supplement), "observation": ""})}}
                body = json.dumps({"choices": [choice]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if chapter["title"] == "发电新增装机" and action == "write" and not timed_out.is_set():
                    timed_out.set()
                    unblock.wait(8)
                    return
                self.wfile.write(body)

        with TemporaryDirectory() as tmp, ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                job = Path(tmp) / "job"
                corpus = Path(tmp) / "first-chapter-conflict.json"
                data = json.loads(CONFLICT.read_text(encoding="utf-8"))
                data["facts"][-1] = {**data["facts"][0], "source": "TEST-CONFLICT", "value": "590",
                                     "locator": "合成来源第2条，组件产量"}
                corpus.write_text(json.dumps(data), encoding="utf-8")
                command = ("run", job, "--mode", "live", "--corpus", corpus)
                env = dict(os.environ, MODEL_ENDPOINT=f"http://127.0.0.1:{server.server_port}/chat/completions",
                           MODEL_NAME="delayed-http-fixture", MODEL_API_KEY="test-only")
                failure = cli(*command, "--request-timeout", "0.5", env=env)
                self.assertEqual(failure.returncode, 1, failure.stderr)
                self.assertIn("发电新增装机」：撰写章节：等待模型响应超时", failure.stderr)
                self.assertIn("已保存 1 章", failure.stderr)
                self.assertIn("--resume", failure.stderr)
                self.assertTrue(timed_out.is_set())
                self.assertFalse(job.exists())
                first_attempt = list(requests)
                self.assertEqual(first_attempt, [
                    ("制造与价格", "query"), ("制造与价格", "write"),
                    ("发电新增装机", "query"), ("发电新增装机", "write"),
                ])
                self.assertEqual(first_chapter_writes, [["pv-module-price"]])
                unblock.set()

                resumed = cli(*command, "--resume", env=env)
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                self.assertEqual(requests[len(first_attempt):], [("发电新增装机", "query"), ("发电新增装机", "write")])
                trace = json.loads(cli("inspect", job, "--json").stdout)
                self.assertEqual(trace["resumed_sections"], 1)
                self.assertEqual(trace["missing"], [])
                self.assertEqual(trace["conflicts"], ["pv-module-output"])
                self.assertIn({"stage": "resume_retry", "section": "发电新增装机", "attempts": 1}, trace["events"])
                approved = cli("approve", job, "--confirm")
                self.assertEqual(approved.returncode, 0, approved.stderr)
                self.assertTrue((job / "reviewed/brief.pdf").read_bytes().startswith(b"%PDF"))
                self.assertIn("合成来源第2条，组件产量",
                              (job / "reviewed/brief.md").read_text(encoding="utf-8"))
            finally:
                unblock.set()
                server.shutdown()
                thread.join()
