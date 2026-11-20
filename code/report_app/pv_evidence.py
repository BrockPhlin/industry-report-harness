"""Read-only retrieval and formatting for the curated photovoltaic evidence."""
import json
from pathlib import Path

from .errors import AppError


CODE_DIR = Path(__file__).resolve().parents[1]


def load_inputs(omit_sources=()):
    template = json.loads((CODE_DIR / "templates/pv-brief.json").read_text(encoding="utf-8"))
    corpus = json.loads((CODE_DIR / "examples/pv-2024.json").read_text(encoding="utf-8"))
    sources = {row["id"]: row for row in corpus["sources"]}
    if not set(omit_sources) <= sources.keys():
        raise AppError("只能排除样例中的资料来源")
    sources = {key: value for key, value in sources.items() if key not in omit_sources}
    facts = {row["id"]: row for row in corpus["facts"] if row["source"] in sources}
    return template, sources, facts


def search_evidence(keys, sources, facts):
    return {
        key: {**facts[key], "origin": sources[facts[key]["source"]]}
        for key in keys if key in facts
    }


def fact_line(fact):
    return f'{fact["period"]}，{fact["metric"]}：{fact["value"]} {fact["unit"]} [{fact["source"]}]'
