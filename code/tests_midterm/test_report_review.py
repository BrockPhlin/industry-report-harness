"""Exercise validation, polishing, follow-up and the exported-file CLI together."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from report_app.errors import AppError
from report_app.followup import grounded_followup
from report_app.long_report import validate_draft, validate_paragraphs
from report_app.report_review import check_edited_paragraph


CODE = Path(__file__).resolve().parents[1]
MARKET_COST = dict(
    ref="E1",
    title="2025 年光伏发电成本",
    publisher="IRENA",
    locator="成本表 · 中国",
    metric="新投运公用事业级光伏平准化发电成本",
    region="China",
    unit="美元/MWh",
    series=[[2025, "36"]],
    text="2025年中国新投运公用事业级光伏平准化发电成本为36美元/MWh。",
)
COST_SENTENCE = MARKET_COST["text"]
PRICE_SENTENCE = "2025年中国新投运公用事业级光伏的售电成交价为36美元/MWh。"


def draft(sentence):
    return {"paragraphs": [{"text": sentence, "refs": ["E1"]}]}


class TestReviewIntegration(unittest.TestCase):
    def setUp(self):
        self.catalog = {"E1": MARKET_COST}
        self.report = {"evidence": [MARKET_COST], "question": "中国光伏发电成本如何？", "answers": []}

    def test_writing_gate_catches_a_cost_used_as_a_price(self):
        # The previous paragraph-only check accepts the year, number, unit and reference.
        self.assertEqual(validate_paragraphs(draft(PRICE_SENTENCE), self.catalog, 1, 900), [PRICE_SENTENCE + " [E1]"])
        with self.assertRaisesRegex(ValueError, "E1"):
            validate_draft(draft(PRICE_SENTENCE), self.catalog, 1, 900)
        self.assertEqual(validate_draft(draft(COST_SENTENCE), self.catalog, 1, 900), [COST_SENTENCE + " [E1]"])

    def test_edits_reject_new_conflicts_and_allow_old_conflicts_to_be_repaired(self):
        before = COST_SENTENCE + " [E1]"
        bad = PRICE_SENTENCE + " [E1]"
        edited = COST_SENTENCE.replace("为", "记录为") + " [E1]"
        check_edited_paragraph(before, edited, [MARKET_COST])
        with self.assertRaises(AppError) as err:
            check_edited_paragraph(before, bad, [MARKET_COST])
        self.assertEqual((err.exception.code, err.exception.status), ("citation_regression", 409))
        check_edited_paragraph(bad, before, [MARKET_COST])
        check_edited_paragraph(bad, bad, [MARKET_COST])

    def test_followup_retries_wrong_metric_with_the_frozen_citation(self):
        with patch("report_app.followup.answer", side_effect=[draft(PRICE_SENTENCE), draft(COST_SENTENCE)]) as model:
            reply = grounded_followup({}, self.report, "请解释E1这项数据。")
        self.assertEqual(reply, COST_SENTENCE + " [E1]")
        self.assertEqual(model.call_count, 2)
        retry_payload = model.call_args.args[2]
        self.assertEqual([r["ref"] for r in retry_payload["证据"]], ["E1"])
        self.assertIn(PRICE_SENTENCE, retry_payload["上次答复需要复核"])

    def test_two_invalid_followup_attempts_never_publish_an_unverified_answer(self):
        with patch("report_app.followup.answer", return_value=draft(PRICE_SENTENCE)) as model:
            with self.assertRaises(AppError) as err:
                grounded_followup({}, self.report, "请解释E1。")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(err.exception.code, "followup_evidence_mismatch")

    def test_missing_identifier_and_no_evidence_stop_before_any_model_call(self):
        with patch("report_app.followup.answer", side_effect=AssertionError("unexpected model call")):
            self.assertIn("E999", grounded_followup({}, self.report, "比较E1和E999。"))
            self.assertIn("资料不足", grounded_followup({}, dict(self.report, evidence=[]), "这项数据的依据是什么？"))

    def test_model_can_report_insufficient_evidence_without_a_retry(self):
        with patch("report_app.followup.answer", return_value={"insufficient": True}) as model:
            reply = grounded_followup({}, self.report, "用E1解释某家公司的利润。")
        model.assert_called_once()
        self.assertIn("资料不足", reply)

    def test_offline_cli_checks_exact_file_bytes_before_auditing(self):
        with tempfile.TemporaryDirectory() as folder:
            markdown = Path(folder) / "报告.md"
            evidence = Path(folder) / "证据.json"
            text = ("## 成本\r\n\r\n" + COST_SENTENCE + " [E1]\r\n").encode()
            digest = sha256(text).hexdigest()
            markdown.write_bytes(text)
            evidence.write_text(json.dumps({"markdown_sha256": digest, "evidence": [MARKET_COST]}), encoding="utf-8")
            command = [sys.executable, str(CODE / "pv_brief.py"), "audit", str(markdown), str(evidence)]
            success = subprocess.run(command, capture_output=True, text=True, check=True)
            result = json.loads(success.stdout)
            self.assertEqual(result["markdown_sha256"], digest)
            self.assertEqual(result["audit"]["summary"]["matched"], 1)

            markdown.write_bytes(text.replace(b"\r\n", b"\n"))
            wrong = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(wrong.returncode, 1)
            self.assertIn("正文指纹不匹配", wrong.stderr)
            self.assertEqual(wrong.stdout, "")

            markdown.write_bytes(text)
            evidence.write_text(json.dumps({"markdown_sha256": digest, "evidence": ["E1"]}), encoding="utf-8")
            malformed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(malformed.returncode, 1)
            self.assertIn("证据记录", malformed.stderr)
            self.assertEqual(malformed.stdout, "")
