"""Writing guidance from the selected report cards, distinct from retrieved evidence."""

REFERENCE_RULE = (
    "你看到的是所选报告的章节摘记。行业报告可用来确定比较维度，方法报告可用来组织叙述、表格和局限说明。"
    "只采用与用户问题相符的做法，保持用户已定的范围和章名。摘记不提供本项目的事实证据。"
    "涉及具体数字、年份、行业结论或因果关系，必须另有该章证据包内的 E 编号支持。"
    "不可将其他行业的数字、结论或摘记页码写成光伏事实，不得声称已通读参考报告。"
)


def chapter_notes(reports):
    notes = []
    for report in reports:
        for index, section in enumerate(report["sections"], 1):
            notes.append({
                "key": f"{report['id']}/{index}",
                "报告": report["title"],
                "用途": "行业分析维度" if report["role"] == "industry" else "跨领域写作方法",
                "主题": report["topics"],
                "章节位置": section["locator"],
                "可借鉴的做法": section["lesson"],
            })
    return notes


def attach_notes(task, notes):
    """Omitting all reference fields keeps earlier tasks' prompts unchanged."""
    if not notes:
        return task
    return dict(task, 参考报告章节摘记=notes)


def outline_choices(raw, sections, notes):
    """Keep only actual user-selected chapter notes and accepted report headings."""
    if not isinstance(raw, dict):
        return {}
    known = {note["key"] for note in notes}
    choices = {}
    for title in sections:
        keys = raw.get(title)
        if isinstance(keys, list):
            chosen = [k for k in keys if isinstance(k, str) and k in known]
            if chosen:
                choices[title] = list(dict.fromkeys(chosen))
    return choices


def notes_for_section(plan, title, notes):
    """Only legacy or unassigned outlines without a mapping receive the full selection."""
    if "reference_sections" not in plan:
        return notes
    choices = plan["reference_sections"]
    if not isinstance(choices, dict):
        return []
    keys = choices.get(title, ())
    return [note for note in notes if note["key"] in keys]
