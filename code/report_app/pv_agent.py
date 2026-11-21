"""Bounded LangGraph workflow for source-grounded reports."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .errors import AppError
from .pv_evidence import fact_line, fact_locator, search_evidence, trace_hits


LABELS = {"fixture": "离线流程验证（未调用真实模型）", "live": "模型辅助生成"}


class SectionState(TypedDict):
    section: dict
    hits: dict
    selected: list
    observation: str
    events: list


def valid_observation(observation):
    return (isinstance(observation, str) and len(observation) <= 100
            and not any(ch.isnumeric() or ch in "[]\n\r<>" for ch in observation)
            and "://" not in observation)


def classify_evidence(section, hits):
    usable = {key: hit for key, hit in hits.items() if "alternatives" not in hit}
    missing = [key for key in section["required"] if key not in hits]
    conflicts = [key for key in section["required"] if key in hits and key not in usable]
    return usable, missing, conflicts


def section_graph(model, sources, facts):
    def search(state, keys, stage):
        section = state["section"]
        if (not isinstance(keys, list) or not keys or
                any(not isinstance(key, str) or key not in section["required"] for key in keys)):
            raise AppError("模型请求了本章节范围外的资料", 502, "invalid_tool_call")
        hits = search_evidence(keys, sources, facts)
        event = {
            "stage": stage,
            "tool": "search_evidence",
            "section": section["title"],
            "requested": list(dict.fromkeys(keys)),
            "returned": trace_hits(hits),
        }
        return {"hits": {**state["hits"], **hits}, "events": [*state["events"], event]}

    def initial(state):
        return search(state, model.query(state["section"]), "initial")

    def missing(state):
        return [key for key in state["section"]["required"] if key not in state["hits"]]

    def next_after_search(state):
        return "supplement" if missing(state) else "draft"

    def supplement(state):
        return search(state, missing(state), "supplement")

    def draft(state):
        usable, absent, conflicts = classify_evidence(state["section"], state["hits"])
        selection, observation = model.write(state["section"], usable)
        if (not isinstance(selection, list) or
                any(not isinstance(key, str) or key not in usable for key in selection) or
                set(selection) != usable.keys()):
            raise AppError("模型返回的证据编号与本章检索结果不一致", 502, "invalid_selection")
        allowed_observation = not conflicts and valid_observation(observation)
        event = {
            "stage": "draft",
            "section": state["section"]["title"],
            "selected": list(dict.fromkeys(selection)),
            "missing": absent,
        }
        if conflicts:
            event["conflicts"] = conflicts
            event["observation_status"] = "omitted_conflict"
        elif not allowed_observation:
            event["observation_status"] = "omitted_invalid"
        return {
            "selected": event["selected"],
            "observation": observation.strip() if allowed_observation else "",
            "events": [*state["events"], event],
        }

    graph = StateGraph(SectionState)
    graph.add_node("initial", initial)
    graph.add_node("supplement", supplement)
    graph.add_node("draft", draft)
    graph.add_edge(START, "initial")
    graph.add_conditional_edges("initial", next_after_search, {
        "supplement": "supplement", "draft": "draft",
    })
    graph.add_edge("supplement", "draft")
    graph.add_edge("draft", END)
    return graph.compile()


def check_saved_section(result, section, sources, facts):
    available = search_evidence(list(section["required"]), sources, facts)
    usable, missing, conflicts = classify_evidence(section, available)
    if (not isinstance(result, dict) or result.get("section") != section or
            not isinstance(result.get("selected"), list) or
            any(not isinstance(key, str) or key not in usable for key in result["selected"]) or
            result.get("hits") != available or set(result["selected"]) != usable.keys() or
            not valid_observation(result.get("observation")) or
            (conflicts and result["observation"]) or
            not isinstance(result.get("events"), list) or not result["events"] or
            any(not isinstance(event, dict) or event.get("section") != section["title"]
                for event in result["events"])):
        raise AppError("检查点章节记录无效，请保留原记录并换新任务目录")
    *searches, draft = result["events"]
    if (draft.get("stage") != "draft" or draft.get("selected") != result["selected"] or
            draft.get("missing") != missing or draft.get("conflicts", []) != conflicts or
            [event.get("stage") for event in searches] not in (["initial"], ["initial", "supplement"])):
        raise AppError("检查点中的运行记录无效，请保留原记录并换新任务目录")
    for event in searches:
        requested = event.get("requested")
        if (not isinstance(requested, list) or
                any(not isinstance(key, str) or key not in section["required"] for key in requested) or
                event.get("returned") != trace_hits(search_evidence(requested, sources, facts))):
            raise AppError("检查点中的资料查询无效，请保留原记录并换新任务目录")


def generate_brief(template, sources, facts, model, mode, *, checkpoint=None):
    graph = section_graph(model, sources, facts)
    lines = [f'# {template["title"]}', f'运行方式：{LABELS[mode]}。状态：待人工核对。',
             "## 研究范围", template["scope"]]
    events, missing, conflicts, protected, used = [], [], [], [], {}
    saved = list(checkpoint.completed) if checkpoint else []
    sections = template["sections"]
    if len(saved) > len(sections):
        raise AppError("检查点章节数超过报告模板")
    for index, section in enumerate(sections):
        if index < len(saved):
            result = saved[index]
            check_saved_section(result, section, sources, facts)
        else:
            if checkpoint:
                checkpoint.start_section()
            try:
                result = graph.invoke({"section": section, "hits": {}, "events": []})
            except AppError as exc:
                raise AppError(f'「{section["title"]}」：{exc}', exc.status, exc.code) from None
            if checkpoint:
                checkpoint.save_section(result)
        lines.append(f'## {section["title"]}')
        for key in result["selected"]:
            fact = result["hits"][key]
            used[fact["source"]] = sources[fact["source"]]
            entry = f"- {fact_line(fact)}"
            lines.append(entry)
            protected.append(entry)
        for key in result["events"][-1]["missing"]:
            entry = f'- 待核实：{section["required"][key]}。本次资料未覆盖。'
            lines.append(entry)
            protected.append(entry)
            missing.append(key)
        for key in result["events"][-1].get("conflicts", []):
            warning = f'- 待核实：{section["required"][key]}。资料表述不一致，暂不采用任何候选值。'
            candidates = []
            for fact in result["hits"][key]["alternatives"]:
                used[fact["source"]] = fact["origin"]
                candidates.append(f"- 候选资料：{fact_line(fact)}。原文位置：{fact_locator(fact)}。")
            lines.extend([warning, *candidates])
            protected.extend([warning, *candidates])
            conflicts.append(key)
        if result["observation"]:
            lines.append(f'辅助观察（待核对）：{result["observation"]}')
        lines.append(f'口径说明：{section["note"]}')
        protected.append(lines[-1])
        if checkpoint:
            retries = checkpoint.interruptions.count(index)
            if retries:
                events.append({"stage": "resume_retry", "section": section["title"], "attempts": retries})
        events.extend(result["events"])
    lines.append("## 资料来源")
    for source in used.values():
        entry = (f'[{source["id"]}｜{source["title"]}]({source["url"]}) '
                 f'｜{source["publisher"]}｜{source["published_at"]}｜{source["locator"]}')
        lines.append(entry)
        protected.append(entry)
    return "\n\n".join(lines) + "\n", {
        "mode": mode, "framework": "LangGraph StateGraph", "sources": list(sources),
        "events": events, "missing": list(dict.fromkeys(missing)),
        "conflicts": list(dict.fromkeys(conflicts)),
        "protected_lines": protected, "resumed_sections": len(saved),
    }


class FixtureWriter:
    """Deterministic decisions for exercising the graph without a model service."""

    def query(self, section):
        return list(section["required"])[:1]

    def write(self, section, hits):
        return list(hits), ""
