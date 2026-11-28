"use strict";

const libraryKinds = {data:"统计资料", policy:"政策文件", study:"研究报告", release:"发布原文"};

function reportCard(report, picker) {
  const card = element("div", undefined, "library-card");
  const title = element("h4", report.title);
  const published = report.year ? report.year + " 年出版" : "";
  card.append(title, element("p", [report.publisher, published].filter(Boolean).join(" · "), "library-meta"),
    element("p", report.summary));
  const foot = element("div", undefined, "library-card-foot");
  if (picker) {
    const choice = element("label");
    const box = element("input");
    box.type = "checkbox";
    box.checked = picker.ids.has(report.id);
    box.setAttribute("aria-label", "选用 " + report.title);
    box.onchange = () => {
      if (box.checked) picker.ids.add(report.id);
      else picker.ids.delete(report.id);
      picker.update();
    };
    choice.append(box, "本次研究选用");
    foot.append(choice);
  }
  foot.append(link("阅读原报告 ↗", report.url));
  card.append(foot);
  if (report.sections?.length) {
    const detail = element("details", undefined, "library-sections");
    detail.append(element("summary", "可参考的章节"));
    for (const section of report.sections) {
      const note = element("p");
      note.append(element("strong", section.locator), " · " + section.lesson);
      detail.append(note);
    }
    if (report.topics?.length) detail.append(element("p", "主题 · " + report.topics.join("、"), "library-meta"));
    card.append(detail);
  }
  return card;
}

function usedReferences(reports) {
  const panel = element("details", undefined, "used-references");
  panel.append(element("summary", "写作时参考的报告（" + reports.length + "）"));
  for (const report of reports) panel.append(reportCard(report));
  return panel;
}

function reportsView(reports, picker, selectedIds) {
  const container = element("div");
  if (!reports.length) {
    container.append(element("p", "参考目录里还没有报告。"));
    return container;
  }
  const category = element("div", undefined, "library-roles");
  category.setAttribute("role", "group");
  category.setAttribute("aria-label", "筛选参考报告");
  const list = element("div");
  function populate(filter) {
    for (const choice of category.children) choice.setAttribute("aria-pressed", String(choice.dataset.role === filter));
    list.replaceChildren();
    for (const [role, title] of [["industry","光伏行业研究"], ["method","跨领域写法参考"]]) {
      if (filter !== "all" && filter !== role) continue;
      const items = reports.filter(r => r.role === role);
      const group = element("section", undefined, "library-group");
      group.append(element("h3", title));
      if (role === "method") group.append(element("p", "这些报告提供章节组织、图表和论证写法。光伏数据另查原始来源。", "library-meta"));
      if (!items.length) group.append(element("p", "这个类别还没有收录报告。"));
      for (const report of items) {
        const card = reportCard(report, picker);
        if (!picker && selectedIds.includes(report.id)) card.append(element("small", "这份研究已选用"));
        group.append(card);
      }
      list.append(group);
    }
  }
  for (const [value, text] of [["all","全部"], ["industry","光伏行业研究"], ["method","跨领域写法参考"]]) {
    const option = button(text, () => populate(value));
    option.dataset.role = value;
    category.append(option);
  }
  container.append(category, list);
  populate("all");
  return container;
}

function sourceView(data) {
  const body = element("div");
  const filter = element("select");
  filter.setAttribute("aria-label", "筛选来源类别");
  for (const [key,text] of Object.entries({all:"全部来源", ...libraryKinds})) {
    const option = element("option", text);
    option.value = key;
    filter.append(option);
  }
  const list = element("div", undefined, "library-sources");
  function show() {
    list.replaceChildren();
    const sources = data.sources.filter(s => filter.value === "all" || s.kind === filter.value);
    if (!sources.length) list.append(element("p", filter.value === "all" ? "本机还没有入库的来源。"
      : "本机还没有这一类来源。"));
    for (const source of sources) {
      const card = element("div", undefined, "source-record");
      const meta = [libraryKinds[source.kind], source.publisher];
      if (source.observations) meta.push(source.observations + " 条观测");
      if (source.passages) meta.push(source.passages + " 条入库摘记");
      if (source.checked) meta.push("核对于 " + source.checked.slice(0,10));
      card.append(link(source.title, source.url), element("p", meta.filter(Boolean).join(" · "), "library-meta"));
      if (source.passages > 0) card.append(sourcePassages(source));
      list.append(card);
    }
  }
  filter.onchange = show;
  body.append(filter, list);
  show();
  return body;
}

function sourcePassages(source) {
  const detail = element("details", undefined, "library-sections");
  const content = element("div");
  detail.append(element("summary", "查看入库摘记（" + source.passages + "）"), content);
  let loading = false;
  let loaded = false;
  async function load() {
    if (!detail.open || loaded || loading) return;
    loading = true;
    content.textContent = "正在读取摘记…";
    try {
      const {passages} = await api("/library/" + encodeURIComponent(source.id) + "/passages");
      content.replaceChildren();
      for (const passage of passages) {
        content.append(element("strong", passage.locator), element("blockquote", passage.text));
      }
      if (!passages.length) content.textContent = "这份来源暂无可读取的摘记。";
      loaded = true;
    } catch (err) {
      content.replaceChildren(element("p",err.message),button("重新读取", load, "link"));
    } finally { loading = false; }
  }
  detail.ontoggle = load;
  return detail;
}

function observationView(data) {
  const body = element("div");
  const count = element("p", data.observations.toLocaleString() + " 条入库观测 · " + data.passages.toLocaleString() + " 条入库摘记");
  body.append(count);
  if (!data.regions.length) {
    body.append(element("p", "本机还没有可查询的统计观测。可以先阅读参考报告或查看已有来源。"));
    return body;
  }
  const form = element("form", undefined, "library-filters");
  function field(name, control) {
    const label = element("label", name);
    label.append(control);
    form.append(label);
    return control;
  }
  const region = field("查询地区", element("select"));
  for (const name of data.regions) {
    const opt = element("option", name === "China" ? "中国（全国）" : name);
    opt.value = name;
    region.append(opt);
  }
  region.value = data.regions.includes("China") ? "China" : data.regions[0];
  const start = field("起始年份", element("input"));
  const end = field("结束年份", element("input"));
  for (const [el,value] of [[start,2020], [end,new Date().getFullYear()]]) {
    Object.assign(el,{type:"number",min:1900,max:2100,value,required:true});
  }
  const metric = field("筛选指标", element("input"));
  Object.assign(metric,{type:"search",maxLength:100,placeholder:"如户用、发电量"});
  const publisher = field("发布机构", element("select"));
  const all = element("option","所有机构");
  all.value = "";
  publisher.append(all);
  for (const name of [...new Set(data.sources.map(source => source.publisher).filter(Boolean))].sort()) {
    const option = element("option",name);
    option.value = name;
    publisher.append(option);
  }
  const submit = element("button","查询","action");
  submit.type = "submit";
  form.append(submit);
  const list = element("div", undefined, "query-results");
  const download = element("a", "导出当前结果 CSV", "action");
  download.hidden = true;
  let request = 0;
  async function query() {
    const current = ++request;
    download.hidden = true;
    if (+start.value > +end.value) { list.textContent = "起始年份应早于或等于结束年份。"; return; }
    const params = new URLSearchParams({region:region.value,start:start.value,end:end.value,
      metric:metric.value.trim(),publisher:publisher.value});
    list.textContent = "正在查询…";
    try {
      const rows = await api("/observations?" + params);
      if (current !== request) return;
      const table = element("table");
      const header = table.createTHead().insertRow();
      for (const name of ["年份","指标","数值","发布机构"]) header.append(element("th",name));
      const tbody = table.createTBody();
      for (const row of rows) {
        const tr = tbody.insertRow();
        const original = element("td");
        original.append(link(row.value + " " + row.unit, row.url));
        tr.append(element("td",row.year),element("td",row.metric),original,element("td",row.publisher));
      }
      list.replaceChildren(rows.length ? table : element("p", "这个条件下还没有入库观测。"));
      if (rows.length === 1200) list.prepend(element("p","已显示前 1200 条。可用年份或指标缩小范围。"));
      download.href = "/api/research/observations.csv?" + params;
      download.hidden = !rows.length;
    } catch (err) { if (current === request) list.textContent = err.message; }
  }
  form.onsubmit = e => { e.preventDefault(); query(); };
  body.append(form, list, download);
  query();
  return body;
}

function openLibrary() {
  nav(false);
  const root = element("div", undefined, "research-library");
  const tabs = element("div", undefined, "library-tabs");
  tabs.setAttribute("role","group");
  tabs.setAttribute("aria-label","资料类别");
  const content = element("div");
  const footer = element("div", undefined, "library-selection");
  const version = state.version;
  const row = state.row;
  const selectedIds = row?.spec?.reference_ids || state.reference_ids;
  const ids = new Set(selectedIds);
  const editing = Boolean(state.settings?.model && !state.busy &&
    (!row || row.status === "planning"));
  const status = element("span");
  status.setAttribute("role","status");
  const save = button("保存选择", async () => {
    if (version !== state.version || !editing) return;
    save.disabled = true;
    try {
      if (row) {
        const updated = await api("/" + row.id + "/scope", {reference_ids:[...ids]});
        if (version !== state.version) return;
        render(updated);
      } else {
        state.reference_ids = [...ids];
        controls();
      }
      if (root.isConnected) $("dialog").close();
    } catch (err) {
      status.textContent = err.message;
      save.disabled = false;
    }
  }, "action");
  function selectionStatus() {
    status.textContent = "已选 " + ids.size + " 份参考报告";
    save.disabled = ids.size === selectedIds.length && selectedIds.every(id => ids.has(id));
  }
  const picker = editing ? {ids, update:selectionStatus} : null;
  if (editing) {
    footer.append(status, save);
    selectionStatus();
  } else if (!state.settings?.model) {
    footer.append(element("span", "当前可阅读和查询资料，配置模型后可为新研究选用报告。"));
  }
  const panels = new Map();
  let libraryData;
  let active = "";
  async function view(tab) {
    active = tab;
    footer.hidden = tab !== "reports" || !footer.childElementCount;
    for (const control of tabs.children) control.setAttribute("aria-pressed", String(control.dataset.key === tab));
    if (panels.has(tab)) { content.replaceChildren(panels.get(tab)); return; }
    content.textContent = "正在读取资料…";
    try {
      let panel;
      if (tab === "reports") {
        const {reports} = await api("/references");
        panel = reportsView(reports, picker, selectedIds);
      } else {
        libraryData ||= api("/library").catch(err => { libraryData = null; throw err; });
        const data = await libraryData;
        panel = tab === "data" ? observationView(data) : sourceView(data);
      }
      panels.set(tab, panel);
      if (active === tab) content.replaceChildren(panel);
    } catch (err) {
      if (active === tab) content.replaceChildren(element("p",err.message), button("重新读取",()=>view(tab),"link"));
    }
  }
  for (const [key,name] of [["reports","参考报告"], ["data","原始数据"], ["sources","来源与政策"]]) {
    const tab = button(name, () => view(key));
    tab.dataset.key = key;
    tabs.append(tab);
  }
  root.append(tabs, content, footer);
  dialog("资料库", root);
  $("dialog").addEventListener("close", () => {
    if (location.hash === "#library") window.history.replaceState(null,"",row ? "#" + row.id : location.pathname);
  }, {once:true});
  view("reports");
}
