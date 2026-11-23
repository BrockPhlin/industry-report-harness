"use strict";

function reportReview(row) {
  const panel = element("details", undefined, "report-review");
  const heading = element("summary", "核查正文与资料修订");
  const content = element("div", undefined, "review-body");
  panel.append(heading, content);
  let loading = false;
  let loaded = false;
  panel.ontoggle = async () => {
    if (!panel.open || loading || loaded) return;
    loading = true;
    content.replaceChildren(element("p", "正在核对原句和本机资料库…"));
    try {
      const result = await api("/" + row.id + "/review");
      if (!panel.isConnected) return;
      if (result.revision !== row.revision) throw Error("正文已更新，请重新打开报告。");
      displayReview(content, row, result);
      loaded = true;
    } catch (error) {
      content.replaceChildren(element("p", error.message), button("重新核查", () => panel.ontoggle(), "link"));
    } finally {
      loading = false;
    }
  };
  return panel;
}

function displayReview(content, row, result) {
  const audit = result.audit;
  const changes = result.changes;
  const claimNames = {mismatch:"数值有出入", review:"需人工判断", matched:"数值匹配"};
  const changeNames = {changed:"数值修订", missing:"本机现行表缺项", unverified:"无法比对", unchanged:"数值相同"};
  const tabs = element("div", undefined, "review-tabs");
  const controls = element("div", undefined, "review-controls");
  const output = element("div", undefined, "review-results");
  const download = button("下载本次核查 JSON", () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], {type:"application/json"});
    const url = URL.createObjectURL(blob);
    const a = element("a");
    a.href = url;
    a.download = "report-review.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, "link");
  const lookup = new Map(audit.claims.map(c => [c.id, c]));
  const sources = new Map(row.evidence.map(s => [s.ref, s]));
  function claimView(claim) {
    const card = element("div", undefined, "review-item");
    card.append(element("small", claim.section + " · " + claimNames[claim.status]),
      element("p", claim.text));
    for (const reason of claim.reasons) card.append(element("div", reason, "review-reason"));
    if (claim.checks.length) {
      const quantities = element("details", undefined, "review-source");
      quantities.append(element("summary", "核对各项数值"));
      for (const check of claim.checks) {
        quantities.append(element("p", check.value + " " + check.unit + " · " + check.reason +
          (check.refs.length ? " " + check.refs.join("、") : "")));
      }
      card.append(quantities);
    }
    for (const ref of claim.refs) {
      const source = sources.get(ref);
      if (source) {
        const details = element("details", undefined, "review-source");
        details.append(element("summary", ref + " · " + source.locator),
          element("blockquote", source.text), link("核对发布原文 ↗", source.url));
        card.append(details);
      }
    }
    return card;
  }
  function changeView(item) {
    const card = element("div", undefined, "review-item");
    card.append(element("small", item.ref + " · " + changeNames[item.status]),
      element("p", [item.region, item.year, item.metric].filter(Boolean).join(" · ")));
    if (item.before != null || item.after != null) {
      card.append(element("div", "报告取值 " + (item.before ?? "缺项") + "　→　本机现行值 " +
        (item.after ?? "缺项") + " " + (item.unit || ""), "review-value"));
    }
    if (item.reason) card.append(element("div", item.reason, "review-reason"));
    if (item.old_digest && item.current_digest && item.status !== "unchanged") {
      card.append(element("small", "原快照 " + item.old_digest.slice(0, 12) +
        "　现行快照 " + item.current_digest.slice(0, 12)));
    }
    if (item.data_url && item.data_url.startsWith("https://")) card.append(link("查看原始数据 ↗", item.data_url));
    const ids = changes.claim_ids_by_ref[item.ref] || [];
    if (ids.length) {
      const related = element("details", undefined, "review-source");
      related.append(element("summary", "引用此证据的原句（" + ids.length + "）"));
      for (const id of ids) related.append(element("p", lookup.get(id).text));
      card.append(related);
    }
    return card;
  }
  function show(mode) {
    const isClaims = mode === "claims";
    for (const tab of tabs.children) tab.setAttribute("aria-pressed", String(tab.dataset.mode === mode));
    const names = isClaims ? claimNames : changeNames;
    const counts = isClaims ? audit.summary : changes.counts;
    const items = isClaims ? audit.claims : changes.items;
    const hint = element("p", isClaims ? "按原句核对数字、单位和引用。因果解释和定性结论需要读原文判断。" :
      "用报告留存的值与本机最近入库的同口径观测比对。另有 " + changes.skipped_passages + " 条文本证据。", "caption");
    const select = element("select");
    select.setAttribute("aria-label", isClaims ? "筛选原句" : "筛选资料状态");
    for (const [status, label] of Object.entries(names)) {
      const option = element("option", label + "（" + counts[status] + "）");
      option.value = status;
      select.append(option);
    }
    select.value = Object.keys(names).find(status => counts[status] > 0) || Object.keys(names)[0];
    function list() {
      const selected = items.filter(item => item.status === select.value);
      output.replaceChildren();
      if (!selected.length) output.append(element("p", "当前筛选没有结果。", "caption"));
      let offset = 0;
      const more = button("显示更多", nextPage, "link");
      function nextPage() {
        more.remove();
        for (const item of selected.slice(offset, offset + 12)) output.append(isClaims ? claimView(item) : changeView(item));
        offset += 12;
        if (offset < selected.length) output.append(more);
      }
      nextPage();
    }
    select.onchange = list;
    controls.replaceChildren(hint, select);
    list();
  }
  for (const [mode, label] of [["claims", "逐句核查"], ["changes", "资料修订"]]) {
    const tab = button(label, () => show(mode));
    tab.dataset.mode = mode;
    tabs.append(tab);
  }
  content.replaceChildren(tabs, controls, output, download);
  show("claims");
}
