"use strict";

const $ = id => document.getElementById(id);
const state = {settings: null, row: null, version: 0, timer: null, busy: false, scope: "", target: null, style: "research", outline: []};
function element(tag, text, style) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (style) el.className = style;
  return el;
}
function button(text, fn, style) {
  const el = element("button", text, style);
  el.type = "button";
  el.onclick = fn;
  return el;
}
function link(text, url) {
  const el = element("a", text);
  el.href = url;
  el.target = "_blank";
  el.rel = "noopener noreferrer";
  return el;
}
async function api(path, data) {
  const response = await fetch("/api/research" + path, data === undefined ? {} :
    {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error?.message || "请求失败，请重试。");
  return result;
}
function notice(text) { $("notice").textContent = text; }
function dialog(title, ...children) {
  $("dialog-title").textContent = title;
  $("dialog-body").replaceChildren(...children);
  $("dialog").showModal();
}
$("dismiss").onclick = () => $("dialog").close();
$("dialog").onclick = e => { if (e.target === $("dialog")) $("dialog").close(); };
function nav(show) {
  document.body.classList.toggle("nav-open", show);
  $("shade").hidden = !show;
}
$("menu").onclick = () => nav(true);
$("shade").onclick = $("close-nav").onclick = () => nav(false);
document.addEventListener("keydown", e => { if (e.key === "Escape") nav(false); });
function focusLabel() {
  $("focus-btn").textContent = state.target ? "约 " + state.target + " 字" : "范围与篇幅";
}
$("focus-btn").onclick = () => {
  const scope = element("textarea");
  scope.rows = 3;
  scope.maxLength = 1800;
  scope.placeholder = "例如：写给省级能源部门，关注分布式和集中式的差异";
  scope.value = state.scope;
  const outline = element("textarea");
  outline.rows = 3;
  outline.placeholder = "每行一章；留空则由模型拟定";
  outline.value = state.outline.join("\n");
  const count = element("input");
  Object.assign(count, {type:"number", min:800, max:10000, step:1, placeholder:"默认 3600，亦可在指令中指定", value:state.target || ""});
  const style = element("select");
  for (const [v,profile] of Object.entries(state.settings.styles)) {
    const option = element("option",profile.name);
    option.value = v;
    style.append(option);
  }
  style.value = state.style;
  function field(label, input) {
    const l = element("label",label,"scope-field");
    l.append(input);
    return l;
  }
  const message = element("p","正文支持 800 至 10000 字。参考报告提供篇章结构，统计数字来自本次检索。");
  const reference = element("p");
  const showReference = () => {
    const profile = state.settings.styles[style.value];
    reference.replaceChildren("版式参考 · ", profile.url ? link(profile.source,profile.url) : profile.source, " · "+profile.locator);
  };
  style.onchange = showReference;
  showReference();
  const apply = button("保存", async () => {
    if (!count.checkValidity()) { count.reportValidity(); return; }
    const titles = outline.value.split("\n").map(t => t.trim()).filter(Boolean);
    if (titles.length > 12 || new Set(titles).size !== titles.length || titles.some(t=>t.length>100)) {
      message.textContent = "请填写不超过12个不同的简短章名。"; return;
    }
    const changes = {scope:scope.value.trim(), target:count.value ? Number(count.value) : null,
      style:style.value, outline:titles};
    if (state.row?.status === "planning") {
      apply.disabled = true;
      try {
        const row = await api("/"+state.row.id+"/scope",{...changes,target:changes.target || state.row.spec.target});
        render(row);
      } catch(err) { message.textContent = err.message; return; }
      finally { apply.disabled = false; }
    } else Object.assign(state, changes);
    focusLabel();
    $("dialog").close();
  },"action");
  dialog("范围与篇幅",field("读者、地区、年份及研究重点",scope),field("目标正文字数",count),field("自定提纲（可选）",outline),
    field("写作结构",style),reference,message,apply);
};
$("sources").onclick = async () => {
  try {
    const data = await api("/library");
    const count = element("p",data.sources.length+" 个数据源 · "+data.observations.toLocaleString()+" 条年度指标 · "+data.passages+" 段发布原文");
    const rows = data.sources.flatMap(s => [link(s.title,s.url),element("p",s.publisher+" · 最近核对 "+s.checked.slice(0,10))]);
    const filters = element("div",undefined,"library-filters");
    const region = element("select");
    region.setAttribute("aria-label","查询地区");
    for (const name of data.regions) {
      const opt = element("option",name);
      opt.value = name;
      region.append(opt);
    }
    region.value = data.regions.includes("China") ? "China" : (data.regions[0] || "");
    const start = element("input"), end = element("input");
    for (const [el,value,label] of [[start,2020,"起始年份"],[end,new Date().getFullYear(),"结束年份"]]) {
      Object.assign(el,{type:"number",min:1900,max:2100,value});
      el.setAttribute("aria-label",label);
    }
    const list = element("div",undefined,"query-results");
    const query = button("查询",async () => {
      try {
        const result = await api("/observations?" + new URLSearchParams({region:region.value,start:start.value,end:end.value}));
        const table = element("table");
        for (const r of result) {
          const tr = element("tr");
          const origin = element("td");
          origin.append(link(r.value+" "+r.unit,r.url));
          tr.append(element("td",r.year),element("td",r.metric),origin);
          table.append(tr);
        }
        list.replaceChildren(result.length ? table : element("p","这个范围尚无年度观测。"));
      } catch (err) { list.textContent = err.message; }
    },"action");
    filters.append(region,start,end,query);
    const sources = element("details");
    sources.append(element("summary","查看数据来源"),...rows);
    dialog("光伏数据库",count,filters,list,sources);
    if (data.regions.length) query.click();

  } catch(err) { notice(err.message); }
};
$("model-info").onclick = () => {
  const model = state.settings.model;
  dialog("模型连接", element("p", model ? "服务端已配置 " + model + "。可以先讨论范围，也可以直接联网写报告。" :
    "服务端尚未配置模型。请在 code/.env 设置 MODEL_ENDPOINT、MODEL_NAME 和 MODEL_API_KEY 后重启服务。"),
    element("p", "离线样例使用两份固定资料。"));
};
function controls() {
  const row = state.row;
  const planning = row?.status === "planning";
  const readyToAsk = row && row.status === "ready" && row.mode === "live";
  $("composer").hidden = Boolean(row && !readyToAsk && !planning);
  $("workflow").hidden = Boolean(row);
  $("focus-btn").hidden = Boolean(row && !planning);
  $("focus-btn").disabled = (!row && $("workflow").value === "fixture") || !state.settings || state.busy;
  $("send").title = planning ? "补充要求" : row ? "发送追问" : "发送研究问题";
  $("prompt").placeholder = planning ? "补充你想看的地区、时间或问题…" : row ? "就这份报告继续提问…" : "输入研究问题，也可以指定年份、读者和篇幅…";
  $("send").disabled = state.busy || !state.settings;
  $("prompt").disabled = state.busy;
}
async function historyList() {
  const rows = await api("");
  const items = rows.map(r => {
    const item = button(r.question, () => select(r.id), r.id === state.row?.id ? "current" : "");
    item.title = r.question;
    item.dataset.key = r.id;
    return item;
  });
  $("history").replaceChildren(...(items.length ? items : [element("p", "还没有研究记录")]));
}
function fresh() {
  ++state.version;
  clearTimeout(state.timer);
  state.row = null;
  state.busy = false;
  state.scope = ""; state.target = null; state.style = "research"; state.outline = [];
  window.history.replaceState(null, "", location.pathname);
  focusLabel();
  nav(false);
  notice("");
  $("breadcrumb").textContent = "新建研究";
  $("canvas").classList.remove("thread");
  $("conversation").hidden = true;
  $("prompt").value = "";
  controls();
  $("prompt").focus();
  historyList().catch(e => notice(e.message));
}
$("new").onclick = fresh;
document.querySelectorAll("#suggestions button").forEach(b => b.onclick = () => {
  $("prompt").value = b.textContent.replace("↗", "").trim();
  $("prompt").focus();
});
function citedText(text, style) {
  const p = element("p", undefined, style);
  const pieces = text.split(/(\*\*[^*\n]+\*\*|\[[\w-]+\])/g);
  for (const part of pieces) {
    const source = (state.row?.evidence || state.settings.sources).find(s => "[" + (s.ref || s.id) + "]" === part);
    if (source?.ref) {
      p.append(button(part,() => dialog(source.ref+" · 数据出处",element("p",source.title),
        element("p",source.locator),element("blockquote",source.text),
        element("p",source.publisher+" · 采集于 "+source.fetched.slice(0,10)+" · 快照 "+source.digest.slice(0,10)),
        link("打开发布页 ↗",source.url),element("span","　"),link("查看原始数据 ↗",source.data_url)),"cite"));
    } else if (source) p.append(link(part, source.url));
    else if (part.startsWith("**") && part.endsWith("**")) p.append(element("strong", part.slice(2, -2)));
    else p.append(part);
  }
  return p;
}
function dataFigure(chart) {
  const figure = element("figure", undefined, "data-figure");
  figure.append(element("figcaption",chart.title));
  for (const point of chart.points) {
    const bar = element("meter");
    bar.min = 0;
    bar.max = 1;
    bar.value = point.fraction;
    bar.setAttribute("aria-label",point.label+" "+point.value);
    const line = element("div");
    line.append(element("span",point.label),bar,element("span",point.value));
    figure.append(line);
  }
  figure.append(citedText("资料来源 "+chart.refs.map(r=>"["+r+"]").join(" "),"caption"));
  return figure;
}
function documentView(markdown) {
  const paper = element("div", undefined, "paper");
  let table = null;
  for (const line of markdown.split("\n").filter(Boolean)) {
    if (line.startsWith("|")) {
      if (/^\|[\s:|-]+$/.test(line)) continue;
      const first = !table;
      if (first) { table = element("table"); paper.append(table); }
      const tr = element("tr");
      for (const cell of line.slice(1,-1).split("|")) tr.append(element(first ? "th" : "td",cell.trim()));
      table.append(tr);
      continue;
    }
    if (table && state.row?.chart) paper.append(dataFigure(state.row.chart));
    table = null;
    const citation = /^\[([^\]]+)\]\((https:\/\/[^\s)]+)\)(.*)$/.exec(line);
    if (citation) {
      const p = element("p", undefined, "meta");
      p.append(link(citation[1], citation[2]), citation[3]);
      paper.append(p);
    } else if (line.startsWith("## ")) paper.append(element("h3", line.slice(3)));
    else if (line.startsWith("# ")) paper.append(element("h2", line.slice(2)));
    else if (line.startsWith("- ")) paper.append(citedText(line.slice(2), "metric"));
    else paper.append(citedText(line, line.startsWith("运行方式") ? "meta" : ""));
  }
  return paper;
}
function traceView(events) {
  const detail = element("details", undefined, "details");
  detail.append(element("summary", "查看逐章检索记录"));
  for (const e of events) {
    if (!["initial", "supplement"].includes(e.stage)) continue;
    const hits = e.returned.map(h => h.source + " · " + h.locator);
    detail.append(element("p", e.section + (e.stage === "initial" ? "检索" : "补查") + " · " +
      ([...new Set(hits)].join("、") || "没有命中资料")));
  }
  return detail;
}
function render(row) {
  state.row = row;
  $("canvas").classList.add("thread");
  $("breadcrumb").textContent = row.question;
  const article = $("conversation");
  article.hidden = false;
  article.replaceChildren(element("div", row.question, "user"),
    element("div", row.mode === "live" ? "光伏研究室 / " + row.model : "光伏研究室 / 离线演练", "byline"));
  if (row.spec?.turns?.length) {
    const thread = element("details",undefined,"details");
    thread.open = row.status === "planning";
    thread.append(element("summary","研究范围讨论"));
    for (const [i,turn] of row.spec.turns.entries()) {
      if (i) thread.append(element("p",turn.question,"user"));
      thread.append(element("p",turn.answer,"answer"));
    }
    article.append(thread);
  }
  if (row.status === "planning") {
    state.scope = row.spec.scope;
    state.target = row.spec.target;
    state.style = row.spec.style;
    state.outline = row.spec.outline || [];
    focusLabel();
    if (state.scope) article.append(element("p",state.scope,"caption"));
    if (state.outline.length) article.append(element("p","指定提纲 · "+state.outline.join(" / "),"caption"));
    article.append(element("p","目标约 "+row.spec.target+" 字。可以继续补充要求，也可以开始写作。","caption"),
      button("按这个范围写",()=>action("/write",{}),"action"));
  } else if (row.status === "running" && row.spec) {
    article.append(element("p",row.spec.progress || "已提交，正在准备研究任务…"));
  } else if (row.status === "running") {
    const done = row.completed || [];
    const next = row.focus.find(name => !done.includes(name));
    article.append(element("p", next ? "正在检索资料、编写「" + next + "」…" : "正在整理草稿…"),
      element("p", "已完成 " + done.length + " / " + row.focus.length + " 章", "caption"));
  } else if (row.status === "failed") {
    article.append(element("p", row.error), button("继续生成", () => action("/retry", {}), "action"));
    if (row.spec) article.append(button("调整范围后重写",() => {
      fresh();
      $("workflow").value = "discuss";
      $("prompt").value = row.question;
      state.scope = row.spec.scope;
      state.target = row.spec.target;
      state.style = row.spec.style;
      state.outline = [...(row.spec.outline || [])];
      focusLabel();
      controls();
    },"link"));
  } else {
    if (row.spec) {
      const info = element("details",undefined,"details");
      info.append(element("summary","取数记录 · 正文 "+row.length+" 字 / 目标 "+row.spec.target+" 字"));
      for (const n of row.retrieval) info.append(element("p",n.source+" · "+n.result));
      article.append(info,documentView(row.markdown));
      const download = element("a","下载 Markdown");
      download.href = "/api/research/" + row.id + "/markdown";
      article.append(download);
    } else article.append(documentView(row.markdown), traceView(row.events));
    const actions = element("div", undefined, "actions");
    if (row.spec && !row.approved) actions.append(button("润色草稿", () => {
      const editor = element("textarea");
      editor.className = "draft-editor";
      editor.rows = 16;
      editor.value = row.markdown;
      editor.setAttribute("aria-label","Markdown 草稿");
      const warning = element("p","可修改正文措辞。请保留段落、数字、单位和引用，原稿会保存在本机。");
      const save = button("保存润色稿", async () => {
        save.disabled = true;
        try {
          const latest = await api("/"+row.id+"/edit",{markdown:editor.value,revision:row.revision});
          $("dialog").close();
          render(latest);
        } catch(err) { warning.textContent = err.message; }
        finally { save.disabled = false; }
      },"action");
      dialog("润色 Markdown 草稿",warning,editor,save);
    },"link"));
    if (row.approved) {
      const download = element("a", "下载已核对的 PDF", "action");
      download.href = "/api/research/" + row.id + "/pdf";
      actions.append(download);
    } else actions.append(button("核对并导出 PDF", () => dialog("已核对这份草稿？",
      element("p", "请检查报告中的指标、单位及出处。确认后将保存本次核对件。"),
      button("确认并生成 PDF", () => { $("dialog").close(); action("/approve", {confirm: true}); }, "action")), "action"));
    article.append(actions);
    for (const turn of row.answers) article.append(element("div", turn.question, "user"),
      element("div", "模型答复 · 据本次草稿", "byline"), citedText(turn.answer, "answer"));
  }
  document.querySelectorAll("#history button").forEach(b => b.classList.toggle("current", b.dataset.key === row.id));
  controls();
}
function watch(row, version) {
  clearTimeout(state.timer);
  if (row.status !== "running") return;
  state.timer = setTimeout(async () => {
    try {
      const next = await api("/" + row.id);
      if (version !== state.version) return;
      render(next);
      watch(next, version);
    } catch (err) {
      if (version === state.version) { notice(err.message); watch(row, version); }
    }
  }, 1000);
}
async function select(key) {
  const version = ++state.version;
  clearTimeout(state.timer);
  nav(false);
  state.busy = false;
  notice("");
  try {
    const row = await api("/" + key);
    if (version !== state.version) return;
    window.history.replaceState(null, "", "#" + key);
    $("prompt").value = "";
    render(row);
    window.scrollTo(0, 0);
    watch(row, version);
  } catch (err) { if (version === state.version) notice(err.message); }
}
async function action(suffix, body) {
  if (state.busy) return;
  const version = state.version;
  const key = state.row?.id;
  state.busy = true;
  controls();
  notice(suffix === "/ask" ? "模型正在阅读草稿并答复…" : suffix === "/plan" || body.workflow === "discuss" ? "正在梳理你的研究需求…" : "正在提交…");
  try {
    const row = await api((key ? "/" + key : "") + suffix, body);
    if (version !== state.version) { await historyList(); return; }
    $("prompt").value = "";
    notice("");
    window.history.replaceState(null, "", "#" + row.id);
    render(row);
    watch(row, version);
    await historyList();
    if (suffix === "/ask") $("input-area").scrollIntoView({block:"end"});
  } catch (err) { if (version === state.version) notice(err.message); }
  finally { if (version === state.version) { state.busy = false; controls(); } }
}
$("composer").onsubmit = e => {
  e.preventDefault();
  const question = $("prompt").value.trim();
  if (!question) { notice("请写下研究问题。"); return; }
  if (state.row?.status === "planning") action("/plan",{question,target:null});
  else if (state.row) action("/ask", {question});
  else if ($("workflow").value === "fixture") action("",{question,mode:"fixture",focus:state.settings.sections});
  else action("",{question, workflow:$("workflow").value, scope:state.scope, target:state.target,style:state.style,outline:state.outline});
};
$("prompt").onkeydown = e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault(); $("composer").requestSubmit();
  }
};
async function init() {
  state.settings = await api("/settings");
  const model = state.settings.model;
  $("model-label").textContent = model || "模型未配置";
  $("model-info").classList.toggle("live", Boolean(model));
  for (const option of $("workflow").options) option.disabled = !model && option.value !== "fixture";
  $("workflow").value = model ? "discuss" : "fixture";
  $("workflow").onchange = controls;
  const originalKey = location.hash.slice(1);
  fresh();
  if (/^[a-f0-9]{32}$/.test(originalKey)) await select(originalKey);
}
controls();
init().catch(err => notice(err.message));
