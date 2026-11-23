"""Answer follow-up questions against the evidence frozen with one report."""

import re

from .errors import AppError
from .long_report import answer, choose_evidence, public_evidence, validate_draft


def grounded_followup(config, row, question):
    evidence = row["evidence"]
    requested = set(re.findall(r"\bE\d+\b", question, re.ASCII))
    if requested:
        candidates = [r for r in evidence if r["ref"] in requested]
        missing = requested - {r["ref"] for r in candidates}
        if missing:
            return "这份报告的证据清单中找不到 " + "、".join(sorted(missing)) + "。请核对编号。"
    else:
        candidates = choose_evidence(evidence, question)
    if not candidates:
        return "这份报告留存的资料不足以回答这个问题。"
    catalog = {r["ref"]: r for r in candidates}
    payload = {
        "研究题目": row["question"],
        "上轮对话": row["answers"][-2:],
        "当前问题": question,
        "证据": public_evidence(candidates),
    }
    instruction = (
        "你是光伏行业研究员。根据当前问题用简短中文答复。题目和历史对话仅帮助理解问题，"
        "事实依据限于本次提供的证据。每段只回答一个要点，数字要与对应年份、地区、统计口径相符。"
        '只返回 JSON。可以回答时给出 {"paragraphs":[{"text":"完整答句","refs":["E1"]}]}。'
        '证据不足时给出 {"insufficient":true}。引用编号只能放在 refs 中。'
    )
    for _ in range(2):
        result = answer(config, instruction, payload)
        if result.get("insufficient") is True:
            return "这份报告留存的资料不足以回答这个问题。可以在新研究中补查。"
        try:
            return "\n\n".join(validate_draft(result, catalog, 1, 900))
        except ValueError as exc:
            payload["上次答复需要复核"] = str(exc)
    raise AppError("追问答复经两次核对仍与所引资料有出入，请缩小问题后重试", 502, "followup_evidence_mismatch")
