"use strict";

function comparisonLink(id, text) {
  const anchor = element("a", text, "comparison-link");
  anchor.href = "#" + id;
  return anchor;
}

function evidenceSourceLinks(source) {
  if (source.comparison_id && source.sources?.length === 2) {
    const links = element("div", undefined, "comparison-source-links");
    for (const [i, original] of source.sources.entries()) {
      links.append(link((i === 0 ? "前期原表" : "后期原表") + " · " + original.year + " ↗", original.data_url || original.url));
    }
    links.append(comparisonLink(source.comparison_id, "打开原对比报告"));
    return [links];
  }
  return [link("打开发布页 ↗", source.url), element("span", "　"), link("查看原始数据 ↗", source.data_url)];
}

async function openComparison(initial) {
  const panel = element("div");
  panel.append(element("p", "正在读取可对比的统计期…"));
  dialog("分省数据对比", panel);
  try {
    const catalog = await requestJSON("/api/comparisons/catalog");
    if (!panel.isConnected || !$("dialog").open) return;
    comparisonForm(panel, catalog, initial || catalog.default);
  } catch (err) {
    panel.replaceChildren(element("p", err.message), button("重新读取", () => openComparison(initial), "link"));
  }
}

function comparisonForm(panel, catalog, initial) {
  const form = element("form", undefined, "comparison-form");
  const period = element("select");
  const metric = element("select");
  const choices = element("details", undefined, "region-options");
  const summary = element("summary");
  const grid = element("div", undefined, "region-grid");
  const picked = element("p", undefined, "region-list");
  const error = element("p", "", "comparison-error");
  error.setAttribute("role", "alert");
  const submit = element("button", "生成对比报告", "action");
  submit.type = "submit";
  const inputs = () => Array.from(grid.querySelectorAll("input"));
  const selected = () => inputs().filter(box => box.checked).map(box => box.value);
  let sending = false;
  function describeSelection() {
    const regions = selected();
    summary.textContent = "选择地区（已选 " + regions.length + " 个）";
    picked.textContent = regions.length ? regions.join("、") : "请选择至少两个地区。";
    submit.disabled = regions.length < 2 || sending;
  }
  function fillSelect(select, values) {
    select.replaceChildren(...values.map(item => {
      const option = element("option", item.label);
      option.value = item.id;
      return option;
    }));
  }
  function updatePeriod(metricId, regions) {
    const entry = catalog.periods.find(item => item.id === period.value);
    fillSelect(metric, entry.metrics);
    if (entry.metrics.some(item => item.id === metricId)) metric.value = metricId;
    grid.replaceChildren(...entry.regions.map(name => {
      const label = element("label");
      const box = element("input");
      Object.assign(box, {type:"checkbox", value:name, checked:regions.includes(name)});
      box.onchange = describeSelection;
      label.append(box, name);
      return label;
    }));
    describeSelection();
  }
  const choose = element("div", undefined, "region-tools");
  for (const [label, checked] of [["全选", true], ["清空", false]]) {
    choose.append(button(label, () => {
      for (const box of inputs()) box.checked = checked;
      describeSelection();
    }, "link"));
  }
  choices.append(summary, choose, grid);
  fillSelect(period, catalog.periods);
  period.value = initial.period;
  updatePeriod(initial.metric, initial.regions);
  period.onchange = () => updatePeriod(metric.value, selected());
  const fields = element("div", undefined, "comparison-fields");
  for (const [name, input] of [["统计期", period], ["比较指标", metric]]) {
    const label = element("label", name, "scope-field");
    label.append(input);
    fields.append(label);
  }
  form.append(element("p", "从国家能源局的两期原表取数，按同一指标比较。"),
    fields, choices, picked, error, submit);
  panel.replaceChildren(form);
  form.onsubmit = async e => {
    e.preventDefault();
    if (sending || selected().length < 2) return;
    sending = true;
    submit.disabled = true;
    submit.textContent = "正在生成…";
    error.textContent = "";
    try {
      const row = await requestJSON("/api/comparisons", {period:period.value, metric:metric.value, regions:selected()});
      if (panel.isConnected && $("dialog").open) {
        $("dialog").close();
        await select(row.id);
      }
      await historyList();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      sending = false;
      submit.textContent = "生成对比报告";
      describeSelection();
    }
  };
}

function signedComparisonValue(value) {
  if (value == null) return "—";
  return Number(value) > 0 ? "+" + value : String(value);
}

function comparisonReport(row) {
  const result = row.comparison;
  const plan = result.plan;
  const page = element("section", undefined, "comparison-report");
  page.append(element("div", "分省数据对比", "byline"),
    element("h1", plan.metric_label), element("p", plan.period_label + " · " + plan.regions.length + " 个地区 · 单位为" + plan.unit, "comparison-subtitle"));
  const actions = element("div", undefined, "actions comparison-actions");
  if (state.settings?.model) {
    actions.append(button("继续研究这组数据", () => {
      fresh();
      state.comparisonId = row.id;
      $("workflow").value = "discuss";
      $("prompt").value = "请分析" + plan.period_label + "，" + plan.regions.join("、") + "的" + plan.metric_label +
        "有何变化？请引用两期原表，并说明哪些差异还需要其他资料解释。";
      controls();
      $("prompt").focus();
    }, "action"));
  }
  actions.append(button("调整对比条件", () => openComparison(plan), "link"));
  const base = "/api/comparisons/" + row.id + "/";
  const downloads = element("div", undefined, "comparison-downloads");
  for (const [text, file] of [["下载 PDF", "report.pdf"], ["下载 Markdown", "report.md"], ["计算明细 JSON", "calculation.json"]]) {
    const anchor = element("a", text);
    anchor.href = base + file;
    anchor.download = "";
    downloads.append(anchor);
  }
  page.append(actions);
  const findings = row.markdown?.split(/^## 主要结果[ \t]*$/m)[1]?.split(/^## /m)[0].trim();
  if (findings) {
    const section = element("div", undefined, "comparison-findings");
    section.append(element("h2", "主要结果"));
    for (const paragraph of findings.split(/\n+/)) section.append(element("p", paragraph));
    page.append(section);
  }
  page.append(element("h2", "地区排名"), element("p", "按后期数值从高到低排列，仅计入两期口径一致且数值齐全的地区。", "caption"));
  const table = element("table", undefined, "comparison-table");
  const hasPriorRanks = result.rows.some(item => item.before_rank != null);
  const headers = [hasPriorRanks ? "排名（前期 → 后期）" : "后期排名", "地区",
    String(plan.before_year), String(plan.after_year), "增减量", "计算增幅"];
  const heading = table.createTHead().insertRow();
  for (const name of headers) {
    const th = element("th", name);
    th.scope = "col";
    heading.append(th);
  }
  const body = table.createTBody();
  for (const item of result.rows) {
    const tr = body.insertRow();
    const rank = hasPriorRanks ? (item.before_rank ?? "—") + " → " + item.rank : item.rank;
    const values = [rank, item.region, item.before, item.after, signedComparisonValue(item.delta),
      item.growth_pct == null ? "—" : signedComparisonValue(item.growth_pct) + "%"];
    for (const [i, value] of values.entries()) {
      const cell = element(i === 1 ? "th" : "td", value);
      if (i === 1) cell.scope = "row";
      cell.dataset.label = headers[i];
      if (i === 5 && item.growth_pct == null && item.growth_note) cell.append(element("small", item.growth_note));
      tr.append(cell);
    }
  }
  page.append(result.rows.length ? table : element("p", "所选地区均缺少可比的两期数值。"));
  if (result.missing.length) {
    page.append(element("h2", "缺项或口径变化的地区"));
    const list = element("ul", undefined, "comparison-missing");
    for (const item of result.missing) {
      list.append(element("li", item.region + " · " + item.reason + "（" + plan.before_year + " 年 " +
        (item.before ?? "缺项") + "，" + plan.after_year + " 年 " + (item.after ?? "缺项") + "）"));
    }
    page.append(list);
  }
  const method = element("details");
  method.append(element("summary", "计算口径与说明"));
  for (const note of result.notes) method.append(element("p", note, "caption"));
  page.append(method, element("h2", "核对原始来源"));
  for (const source of result.sources) {
    const line = element("div", undefined, "comparison-source");
    line.append(element("b", String(source.year)), link(source.title, source.url));
    if (source.data_url && source.data_url !== source.url) line.append(link("查看原表 ↗", source.data_url));
    page.append(line);
  }
  page.append(downloads);
  return page;
}
