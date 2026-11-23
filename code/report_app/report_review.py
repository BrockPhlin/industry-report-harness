"""Relate a report's numeric checks to revisions of the evidence it actually cites."""

from collections import Counter, defaultdict
from hashlib import sha256
import re

from .claim_audit import audit_claims
from .evidence_changes import compare_evidence
from .errors import AppError


def check_edited_paragraph(original, edited, evidence):
    """Reject newly introduced, identifiable numeric conflicts in an edited paragraph."""
    def conflicts(text):
        counts = Counter()
        for claim in audit_claims(text, evidence)["claims"]:
            for check in claim["checks"]:
                if check["status"] == "mismatch":
                    counts[(check["value"], check["unit"], check["reason"])] += 1
        return counts

    new = conflicts(edited)
    if new:
        introduced = new - conflicts(original)
        if introduced:
            value, unit, reason = next(iter(introduced))
            raise AppError(f"润色后 {value}{unit} 与所引证据有出入。{reason}", 409, "citation_regression")


def export_markdown(markdown):
    # Older drafts separated each table row with a blank line.
    return re.sub(r"(?m)^(\|[^\n]*\|)\n\n(?=\|)", r"\1\n", markdown).encode()


def review_report(markdown, evidence, store=None):
    audit = audit_claims(markdown, evidence)
    result = {
        "version": 1,
        "markdown_sha256": sha256(export_markdown(markdown)).hexdigest(),
        "audit": audit,
    }
    if store is not None:
        changes = compare_evidence(store, evidence)
        affected = set(changes["affected_refs"])
        impact = defaultdict(list)
        for claim in audit["claims"]:
            for ref in dict.fromkeys(claim["refs"]):
                if ref in affected:
                    impact[ref].append(claim["id"])
        changes["claim_ids_by_ref"] = dict(impact)
        result["changes"] = changes
    return result
