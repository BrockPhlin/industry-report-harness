"""Expose a saved calculation to the writer with both of its original sources."""

from decimal import Decimal
import re


RANKING = re.compile(r"排名|排序|名次|位次|升至第|降至第|位居|居首|首位|末位|垫底|"
                     r"第[一二三四五六七八九十\d]+(?:名|位)|(?:排|列|居|三地|两地)第[一二三四五六七八九十\d]+|居[首末]")
CHANGE_EXTREME = re.compile(r"(?:变动|变化|增幅|降幅|增量|降量|差额|减幅|降得|增加|减少).{0,8}(?:最大|最小|最多|最少)")
EDITOR_NOTE = re.compile(r"(?:重新|补充|重新核对).{0,8}(?:引用|证据编号)|(?:改写|删去)(?:本句|这句)|需回到.{0,20}复算条目")
NEGATIVE_CAUSE = re.compile(r"(?:负值|负新增|负增长|为负).{0,30}(?:源于|说明|反映|意味着|归因|原因是|是因|表明|证明|由于)|"
                            r"(?:退出|退运|拆除|修正|下调).{0,25}(?:导致|造成|致使).{0,15}(?:负值|为负|负新增)")


def comparison_scope(result):
    plan = result["plan"]
    return (f"{plan['period_label']}，{plan['metric_label']}（{plan['unit']}），"
            + "、".join(plan["regions"]))


def calculation_evidence(result, key, created, first_number):
    plan = result["plan"]
    sources = result["sources"]
    before_year, after_year = plan["before_year"], plan["after_year"]
    unit = plan["unit"]
    rows = []

    def add(region, text):
        rows.append(dict(ref=f"E{first_number + len(rows)}", comparison_id=key,
            sources=sources, region=region, fetched=created, digest=result["markdown_sha256"],
            publisher="光伏研究室（根据国家能源局原表计算）", url=sources[-1]["url"],
            data_url=sources[-1]["data_url"], title=plan["metric_label"] + " · 分省对比复算",
            locator=f"{region} · {plan['period_label']} · {plan['metric_label']}", text=text))

    for row in result["rows"]:
        label = row["region"] + plan["metric_label"]
        growth = (f"{label}按{before_year}年同期基数计算，变动率为{row['growth_pct']}%。"
                  if row["growth_pct"] is not None else row["region"] + row["growth_note"])
        rank = rank_sentence(result, row)
        caveat = ""
        if Decimal(row["after"]) < 0 or Decimal(row["before"]) < 0:
            caveat = "".join(n for n in result["notes"] if "修正" in n or "退出" in n)
        add(row["region"], f"{label}在{before_year}年为{row['before']}{unit}，{after_year}年为{row['after']}{unit}。"
            f"{label}的两期差额为{row['delta']}{unit}（后期减前期）。{growth}"
            + rank + caveat)
    for row in result["missing"]:
        add(row["region"], f"{row['region']}，{plan['metric_label']}，{plan['period_label']}。"
            f"未参加排名。{row['reason']}")
    return rows


def rank_sentence(result, row):
    plan = result["plan"]
    size = len(result["rows"])
    if "before_rank" in row:
        before_rank = row["before_rank"]
    else:
        before_rank = 1 + sum(Decimal(other["before"]) > Decimal(row["before"]) for other in result["rows"])
    return (f"在所选{size}个两期可比地区中，{row['region']}的{plan['metric_label']}"
            f"按原表数值在{plan['before_year']}年排第{before_rank}，{plan['after_year']}年排第{row['rank']}。")


def comparison_summary(result, evidence, question):
    """Answer who leads and quantify the change for the region singled out in the question."""
    rows, plan = result["rows"], result["plan"]
    if not rows:
        return []
    refs = {r["region"]: r["ref"] for r in evidence if r.get("comparison_id")}
    leaders = [r for r in rows if r["rank"] == 1]
    names = "、".join(r["region"] for r in leaders)
    position = "并列第一" if len(leaders) > 1 else "位居第一"
    unit = plan["unit"]
    summary = [f"按{plan['metric_label']}比较，{plan['after_year']}年{names}在所选{len(rows)}个可比地区中"
               f"{position}，公布值为{leaders[0]['after']}{unit}。 "
               + " ".join(f"[{refs[r['region']]}]" for r in leaders)]
    focus = next((r for r in rows if re.search(re.escape(r["region"]) + r"(?:省|市)?的?(?:名次|排名|位次|变化|差额)", question)), None)
    focus = focus or max(rows, key=lambda r: abs(Decimal(r["delta"])))
    delta = Decimal(focus["delta"])
    change = "两期持平" if not delta else f"{'减少' if delta < 0 else '增加'}了{abs(delta)}{unit}"
    previous = focus.get("before_rank")
    rank = (f"两期均列第{focus['rank']}" if previous == focus["rank"] else
            f"由第{previous}位变为第{focus['rank']}位") if previous is not None else f"后期列第{focus['rank']}"
    summary.append(f"{focus['region']}从{plan['before_year']}年的{focus['before']}{unit}变为"
                   f"{plan['after_year']}年的{focus['after']}{unit}，{change}，在这组地区中{rank}。 [{refs[focus['region']]}]")
    return summary


def reconcile_comparison(paragraphs, evidence, result):
    """Express rank claims from the selected table and leave unrelated prose in place."""
    plan = result["plan"]
    refs = {r["ref"]: r for r in evidence}
    by_region = {r["region"]: r["ref"] for r in evidence if r.get("comparison_id")}
    records = {r["region"]: r for r in result["rows"]}
    emitted = set()
    updated = []
    revised = 0
    for paragraph in paragraphs:
        labels = re.findall(r"\[(E\d+)\]", paragraph)
        relevant = [refs[k] for k in labels if k in refs and
                    (refs[k].get("comparison_id") or refs[k].get("metric") == plan["metric_label"])]
        if not relevant:
            updated.append(paragraph)
            continue
        clean = re.sub(r"\s*\[E\d+\]", "", paragraph).strip()
        sentences = re.findall(r"[^。！？]+[。！？]?", clean)
        kept, corrections = [], []
        for sentence in sentences:
            if EDITOR_NOTE.search(sentence):
                revised += 1
                continue
            ranking = RANKING.search(sentence)
            extreme = CHANGE_EXTREME.search(sentence)
            causal = NEGATIVE_CAUSE.search(sentence)
            if not (ranking or extreme or causal):
                kept.append(sentence)
                continue
            targets = [region for region in records if region in sentence]
            if not targets:
                targets = list(dict.fromkeys(r.get("region") for r in relevant if r.get("region") in records))
            if not targets:
                kept.append(sentence)
                continue
            # A statistic for another metric cannot be rewritten using these rows.
            if any(word in sentence for word in ("成本", "电价", "企业排名", "产量排名", "发电量排名")):
                kept.append(sentence)
                continue
            revised += 1
            if causal:
                if "negative" not in emitted:
                    corrections.append("分省表记录的是并网统计值。仅凭某一行的负数，无法分别量化项目退出和口径修正各自的影响。 "
                                       + " ".join(f"[{by_region[t]}]" for t in targets))
                    emitted.add("negative")
            if extreme:
                if "range" not in emitted:
                    deltas = [Decimal(r["delta"]) for r in records.values()]
                    low, high = min(deltas), max(deltas)
                    labels_for_range = [by_region[r["region"]] for r in records.values() if Decimal(r["delta"]) in {low, high}]
                    corrections.append(f"按后期减前期计算，所选地区的差额在{low}{plan['unit']}与{high}{plan['unit']}之间。 "
                                       + " ".join(f"[{ref}]" for ref in labels_for_range))
                    emitted.add("range")
            if ranking:
                for region in targets:
                    if region not in emitted:
                        corrections.append(rank_sentence(result, records[region]) + f" [{by_region[region]}]")
                        emitted.add(region)
        if kept:
            updated.append("".join(kept) + " " + " ".join(f"[{ref}]" for ref in labels))
        updated.extend(corrections)
    if not updated and records:
        updated = comparison_summary(result, evidence, "")
    return updated, revised


def comparison_appendix(result, evidence):
    plan = result["plan"]
    by_region = {r["region"]: r["ref"] for r in evidence if r.get("comparison_id")}
    lines = [f"| 地区 | {plan['before_year']}年 | {plan['after_year']}年 | 差额 | 后期排名 |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for row in result["rows"]:
        lines.append(f"| {row['region']} [{by_region[row['region']]}] | {row['before']} | {row['after']} | "
                     f"{row['delta']} | {row['rank']} |")
    blocks = ["## 附：分省对比复算",
              f"{plan['period_label']}，{plan['metric_label']}，单位为{plan['unit']}。"
              "差额为后期减前期，名次按后期值在所选可比地区中排列。"]
    if result["rows"]:
        blocks.append("\n".join(lines))
    for row in result["missing"]:
        blocks.append(f"{row['region']}未参加排名。{row['reason']} [{by_region[row['region']]}]")
    return blocks
