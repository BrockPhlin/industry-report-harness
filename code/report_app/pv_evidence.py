"""Read-only retrieval and formatting for curated report evidence."""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .errors import AppError


CODE_DIR = Path(__file__).resolve().parents[1]


def required_text(row, fields):
    if not isinstance(row, dict):
        raise ValueError("需要 JSON 对象")
    for field in fields:
        value = row.get(field)
        if (not isinstance(value, str) or not value.strip() or
                value != value.strip() or len(value.splitlines()) != 1 or
                any(ord(char) < 32 for char in value)):
            raise ValueError(f"{field} 须为非空的单行文本")


def load_inputs(omit_sources=(), *, template_path=None, corpus_path=None):
    template_file = template_path or CODE_DIR / "templates/pv-brief.json"
    corpus_file = corpus_path or CODE_DIR / "examples/pv-2024.json"
    try:
        template = json.loads(template_file.read_text(encoding="utf-8"))
        corpus = json.loads(corpus_file.read_text(encoding="utf-8"))
        required_text(template, ("title", "scope"))
        sections = template.get("sections")
        if not isinstance(sections, list) or not sections:
            raise ValueError("模板须包含至少一个章节")
        titles, metrics = set(), {}
        for section in sections:
            required_text(section, ("title", "note"))
            if section["title"] in titles:
                raise ValueError("章节标题不能重复")
            titles.add(section["title"])
            required = section.get("required")
            if not isinstance(required, dict) or not required:
                raise ValueError("章节须有必查指标")
            required_text(required, required)
            for key, name in required.items():
                if metrics.setdefault(key, name) != name:
                    raise ValueError("同一指标编号须使用相同名称")

        sources = {}
        if not isinstance(corpus["sources"], list) or not isinstance(corpus["facts"], list):
            raise ValueError("资料须包含来源列表和指标列表")
        for row in corpus["sources"]:
            required_text(row, ("id", "title", "publisher", "published_at", "url", "locator"))
            address = urlsplit(row["url"])
            if (address.scheme != "https" or not address.hostname or address.username or address.password
                    or re.search(r"[\s()]", row["url"])):
                raise ValueError("资料链接须为可直接打开的 HTTPS 地址")
            if row["id"] in sources or not re.fullmatch(r"[\w-]+", row["id"]):
                raise ValueError("来源编号须唯一，由字母、数字、下划线或连字符组成")
            sources[row["id"]] = row

        facts = {}
        for row in corpus["facts"]:
            required_text(row, ("id", "source", "metric", "period", "value", "unit"))
            if "locator" in row:
                required_text(row, ("locator",))
            if row["source"] not in sources or metrics.get(row["id"]) != row["metric"]:
                raise ValueError("指标须引用已登记的来源和模板中的同名指标")
            if row["source"] not in omit_sources:
                facts.setdefault(row["id"], []).append(row)
    except json.JSONDecodeError as exc:
        raise AppError(f"资料或模板 JSON 无效（第 {exc.lineno} 行）") from None
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(f"资料或模板格式无效：{exc}") from None
    if not set(omit_sources) <= sources.keys():
        raise AppError("只能排除已登记的资料来源")
    sources = {key: value for key, value in sources.items() if key not in omit_sources}
    return template, sources, facts


def search_evidence(keys, sources, facts):
    hits = {}
    for key in keys:
        rows = facts.get(key)
        if not rows:
            continue
        claims = {(row["period"], row["value"], row["unit"]) for row in rows}
        if len(claims) == 1:
            hits[key] = {**rows[0], "origin": sources[rows[0]["source"]]}
        else:
            hits[key] = {"alternatives": [{**row, "origin": sources[row["source"]]} for row in rows]}
    return hits


def trace_hits(hits):
    return [
        {"fact": key, "source": row["source"], "locator": fact_locator(row)}
        for key, hit in hits.items() for row in hit.get("alternatives", [hit])
    ]


def fact_locator(row):
    return row.get("locator", row["origin"]["locator"])


def fact_line(fact):
    return f'{fact["period"]}，{fact["metric"]}：{fact["value"]} {fact["unit"]} [{fact["source"]}]'
