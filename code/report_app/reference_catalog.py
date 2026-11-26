"""Expose manually checked reading notes; factual observations remain in the source library."""

from copy import deepcopy
import json
from pathlib import Path

from .studies import STUDIES


TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def _load():
    studies = {study.key: study for study in STUDIES}
    styles = json.loads((TEMPLATES / "report-styles.json").read_text(encoding="utf-8"))
    entries = json.loads((TEMPLATES / "reference-reports.json").read_text(encoding="utf-8"))
    for entry in entries:
        if entry["role"] == "industry":
            study = studies[entry["id"]]
            entry.update(title=study.title, publisher=study.publisher, url=study.landing)
        else:
            entry["title"] = styles[entry.pop("style")]["source"]
    return {entry["id"]: entry for entry in entries}


_REPORTS = _load()


def catalog():
    """Return independent public cards in catalog order. Year means publication year."""
    return deepcopy(list(_REPORTS.values()))


def selected_reports(ids):
    """Resolve an ordered UI selection without accepting paths, arbitrary URLs or repeated IDs."""
    if not isinstance(ids, list) or len(ids) > len(_REPORTS):
        raise ValueError("请从参考报告目录中选择报告。")
    if any(not isinstance(key, str) or key not in _REPORTS for key in ids):
        raise ValueError("所选参考报告不在目录中。")
    if len(set(ids)) != len(ids):
        raise ValueError("同一本参考报告只需选择一次。")
    return [deepcopy(_REPORTS[key]) for key in ids]
