import json
import shutil
import subprocess
import sys
import unittest
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from report_app.errors import AppError
from report_app.pv_agent import FixtureWriter, generate_brief
from report_app.pv_evidence import CODE_DIR, load_inputs, search_evidence
from report_app.pv_model import ChatWriter


class GraphTests(unittest.TestCase):
    def test_full_run_supplements_price_and_preserves_metric_units(self):
        markdown, trace = generate_brief(*load_inputs(), FixtureWriter(), "fixture")
        self.assertIn("全国光伏组件产量：588 GW [MIIT]", markdown)
        self.assertIn("全国光伏发电新增装机：2.78 亿千瓦 [NEA]", markdown)
        self.assertEqual(trace["missing"], [])
        self.assertEqual([event["stage"] for event in trace["events"]],
                         ["initial", "supplement", "draft", "initial", "draft"])
        self.assertEqual(trace["events"][1]["returned"][0]["fact"], "pv-module-price")

    def test_missing_input_stays_unverified_after_one_supplement(self):
        markdown, trace = generate_brief(*load_inputs(["NEA"]), FixtureWriter(), "fixture")
        self.assertIn("待核实：全国光伏发电新增装机", markdown)
        self.assertNotIn("2.78", markdown)
        self.assertEqual(trace["missing"], ["pv-new-capacity"])
        self.assertEqual([event["stage"] for event in trace["events"][-3:]],
                         ["initial", "supplement", "draft"])
        self.assertEqual(trace["events"][-2]["returned"], [])

    def test_evidence_carries_metadata_and_original_location(self):
        _, sources, facts = load_inputs()
        result = search_evidence(["pv-new-capacity", "unknown"], sources, facts)
        self.assertEqual(set(result), {"pv-new-capacity"})
        self.assertEqual(result["pv-new-capacity"]["origin"]["published_at"], "2025-01-27")
        self.assertIn("光伏发电建设", result["pv-new-capacity"]["origin"]["locator"])

    def test_fabricated_fact_or_numeric_observation_is_rejected(self):
        class WrongWriter(FixtureWriter):
            def write(self, section, hits):
                return ["fake-id"], ""

        class NumberWriter(FixtureWriter):
            def write(self, section, hits):
                return list(hits), "增加了１２万"

        for writer, code in [(WrongWriter(), "invalid_selection"),
                             (NumberWriter(), "invalid_observation")]:
            with self.subTest(code=code), self.assertRaises(AppError) as found:
                generate_brief(*load_inputs(), writer, "fixture")
            self.assertEqual(found.exception.code, code)

    def test_chat_tool_transcript_receives_results_and_supplement(self):
        def mock(request, timeout):
            body = json.loads(request.data)
            messages = body["messages"]
            if "tools" in body:
                self.assertEqual(body["tool_choice"], "auto")
                keys = json.loads(messages[1]["content"])["required"]
                message = {"content": None, "tool_calls": [{
                    "id": "lookup", "type": "function", "function": {
                        "name": "search_evidence", "arguments": encode_arguments({"keys": [next(iter(keys))]})},
                }]}
                choice = {"finish_reason": "tool_calls", "message": message}
            else:
                tool_result = messages[-2]
                self.assertEqual(tool_result["tool_call_id"], "lookup")
                self.assertEqual(body["response_format"], {"type": "json_object"})
                initial = json.loads(tool_result["content"])
                supplement = json.loads(messages[-1]["content"].split("\n补查命中：", 1)[1])
                outbound = messages[-3]["tool_calls"][0]["function"]["arguments"]
                requested, = json.loads(outbound)["keys"]
                self.assertEqual(set(initial), {requested} & facts.keys())
                evidence = {**initial, **supplement}
                self.assertEqual(set(evidence), facts.keys() & json.loads(messages[1]["content"])["required"].keys())
                self.assertFalse(initial.keys() & supplement.keys())
                self.assertTrue(all("locator" in row["origin"] for row in evidence.values()))
                choice = {"finish_reason": "stop", "message": {
                    "content": json.dumps({"selected": list(evidence), "observation": ""})}}
            return BytesIO(json.dumps({"choices": [choice]}).encode())

        config = {"MODEL_ENDPOINT": "https://test.invalid/v1/chat/completions",
                  "MODEL_NAME": "api-fixture", "MODEL_API_KEY": "test-only"}
        for encode_arguments in (dict, json.dumps):
            for omit, expected_missing in [([], []), (["NEA"], ["pv-new-capacity"])]:
                with self.subTest(arguments=encode_arguments.__name__, omit=omit):
                    template, sources, facts = load_inputs(omit)
                    model = ChatWriter(config, opener=mock)
                    _, trace = generate_brief(template, sources, facts, model, "live")
                    self.assertEqual(trace["missing"], expected_missing)


class CLITests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(CODE_DIR / "pv_brief.py"), *map(str, args)],
                              text=True, capture_output=True)

    def test_review_rejects_changed_metrics_and_preserves_trace(self):
        with TemporaryDirectory() as tmp:
            task = Path(tmp) / "job"
            result = self.cli("run", task, "--mode", "fixture")
            self.assertEqual(result.returncode, 0, result.stderr)
            baseline = (task / "baseline.md").read_text()
            self.assertIn("588 GW", baseline)
            trace = self.cli("inspect", task, "--json")
            self.assertEqual(json.loads(trace.stdout)["mode"], "fixture")
            draft_path = task / "draft.md"
            draft = draft_path.read_text()
            draft_path.write_text(draft.replace("588 GW", "2.78 亿千瓦"))
            result = self.cli("approve", task, "--confirm")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("审阅稿更改", result.stderr)
            self.assertFalse((task / "reviewed").exists())

    @unittest.skipUnless(shutil.which("typst"), "requires Typst to verify actual PDF export")
    def test_confirmed_pdf_keeps_missing_status_and_matches_digest(self):
        with TemporaryDirectory() as tmp:
            task = Path(tmp) / "job"
            generated = self.cli("run", task, "--mode", "fixture", "--omit-source", "NEA")
            self.assertEqual(generated.returncode, 0, generated.stderr)
            checked = self.cli("approve", task, "--confirm")
            self.assertEqual(checked.returncode, 0, checked.stderr)
            reviewed = task / "reviewed"
            markdown = (reviewed / "brief.md").read_bytes()
            self.assertIn("仍有待核实项".encode(), markdown)
            self.assertTrue((reviewed / "brief.pdf").read_bytes().startswith(b"%PDF"))
            receipt = json.loads((reviewed / "confirmation.json").read_text())
            self.assertEqual(receipt["markdown_sha256"], sha256(markdown).hexdigest())
            self.assertNotEqual(self.cli("approve", task, "--confirm").returncode, 0)


if __name__ == "__main__":
    unittest.main()
