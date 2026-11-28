"""Compare measurements cited in a saved report with one read-only library snapshot."""

from collections import Counter
from contextlib import closing
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from .solar_data import display_value
from .store import now


def _decimal(value):
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _current_source(db, url):
    # Same selection as SolarLibrary.summary. A recheck selects the raw file,
    # and the last parser version for those bytes supplies the observations.
    return db.execute("""
        SELECT s.id, COALESCE(s.raw_digest,s.digest) AS fingerprint,
               EXISTS(SELECT 1 FROM solar_observations WHERE source=s.id) AS has_values
        FROM solar_sources s
        WHERE s.url=? AND COALESCE(s.raw_digest,s.digest)=(
            SELECT COALESCE(raw_digest,digest) FROM solar_sources WHERE url=?
            ORDER BY checked DESC,id DESC LIMIT 1)
        ORDER BY s.id DESC LIMIT 1
    """, (url, url)).fetchone()


def _original_source(db, ref):
    """Verify a legacy database ID before using it to recover a URL or raw value."""
    digest, landing, data_url = ref.get("digest"), ref.get("url"), ref.get("data_url")
    if not digest or not (data_url or landing):
        return None
    # Report imports may come from a different database where the numeric ID
    # has been reused. A shared landing page alone cannot identify its asset.
    if data_url:
        condition, value = "url=?", data_url
    else:
        condition, value = "origin=?", landing
    candidates = list(db.execute(
        f"SELECT id,url FROM solar_sources WHERE {condition} AND COALESCE(raw_digest,digest)=?",
        (value, digest),
    ))
    if not data_url and len({candidate["url"] for candidate in candidates}) != 1:
        return None
    for candidate in candidates:
        if candidate["id"] == ref.get("source"):
            return candidate
    return candidates[0] if len(candidates) == 1 else None


def _measurements(db, source, region, metric):
    return {row["year"]: (row["unit"], row["value"]) for row in db.execute(
        "SELECT year,unit,value FROM solar_observations WHERE source=? AND region=? AND metric=?",
        (source, region, metric),
    )}


def _compare_year(year, before, unit, basis, current, observations):
    if basis == "display_only":
        return "unverified", None, "旧报告只保存了展示精度，无法恢复原始数值。"
    if _decimal(before) is None:
        return "unverified", None, "报告中的原始数值无法比较。"
    if current is None or not current["has_values"]:
        return "unverified", None, "本地资料库暂无该取数地址的数值快照。"
    if year not in observations:
        return "missing", None, "当前快照缺少同一地区、指标和年份的观测。"
    current_unit, after = observations[year]
    if current_unit != unit:
        return "unverified", None, f"当前观测的单位为{current_unit}，需人工核对口径。"
    if _decimal(after) is None:
        return "unverified", after, "当前快照的数值无法比较。"
    if _decimal(before) == _decimal(after):
        return "unchanged", after, "两份记录在相同口径下数值相等。"
    return "changed", after, "两份记录在相同口径下数值有变。"


def _consistent_with_display(observed, displayed, unit):
    value = _decimal(observed)
    if value is None or _decimal(displayed) is None:
        return False
    places = 4 if "美元" in unit or "欧元" in unit or unit in {"GWac", "GWdc"} else 2
    return value == _decimal(displayed) or _decimal(display_value(observed, places)) == _decimal(displayed)


def compare_evidence(store, evidence):
    """Inspect only years cited in the report. No fetch, model call or database write."""
    counts = Counter(dict.fromkeys(("changed", "missing", "unchanged", "unverified"), 0))
    items, affected_refs = [], {}
    skipped_passages = 0
    with closing(store.connect()) as db:
        db.execute("BEGIN")
        compared_at = now()
        lookup_source = lru_cache(maxsize=None)(lambda url: _current_source(db, url))
        lookup_values = lru_cache(maxsize=None)(
            lambda source, region, metric: _measurements(db, source, region, metric)
        )
        for ref in evidence or ():
            raw = ref.get("raw_series")
            series = raw or ref.get("series")
            if not series:
                skipped_passages += 1
                continue
            region, metric, unit = (ref.get(field) for field in ("region", "metric", "unit"))
            url = ref.get("data_url")
            original = _original_source(db, ref) if not raw or not url else None
            if not url and original:
                url = original["url"]
            current = lookup_source(url) if url else None
            old = lookup_values(original["id"], region, metric) if original and not raw else {}
            latest = lookup_values(current["id"], region, metric) if current else {}
            for year, recorded in series:
                before = recorded
                basis = "raw_series" if raw else "display_only"
                if not raw and unit and year in old and old[year][0] == unit and (
                    _consistent_with_display(old[year][1], recorded, unit)
                ):
                    basis, before = "stored_snapshot", old[year][1]
                if not all((region, metric, unit)) or not url:
                    status, after, reason = "unverified", None, "旧报告缺少可核实的取数地址或指标口径。"
                else:
                    status, after, reason = _compare_year(year, before, unit, basis, current, latest)
                current_digest = current["fingerprint"] if current else None
                if status == "changed" and current_digest == ref.get("digest"):
                    reason = "原文件指纹相同，资料库对该观测的解析值有变。"
                counts[status] += 1
                if status in ("changed", "missing"):
                    affected_refs[ref["ref"]] = None
                items.append(dict(ref=ref["ref"], status=status, region=region, metric=metric, unit=unit,
                                  year=year, before=before, after=after, before_basis=basis, reason=reason,
                                  data_url=url, old_digest=ref.get("digest"), current_digest=current_digest))
    return dict(compared_at=compared_at, counts=dict(counts), items=items, affected_refs=list(affected_refs),
                skipped_passages=skipped_passages)
