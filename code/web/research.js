"use strict";

const $ = id => document.getElementById(id);
const state = {settings: null, focus: [], row: null, version: 0, timer: null, busy: false};
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
  $("focus-btn").textContent = state.focus.length === 1 ? "☷ " + state.focus[0] : "☷ 选章节";
}
$("focus-btn").onclick = () => {
  const labels = state.settings.sections.map(name => {
    const label = element("label", undefined, "opt");
    const input = element("input");
    input.type = "checkbox";
    input.value = name;
    input.checked = state.focus.includes(name);
    label.append(input, name);
    return label;
  });
  const apply = button("使用所选重点", () => {
    const selected = labels.map(l => l.firstChild).filter(i => i.checked).map(i => i.value);
    if (!selected.length) { warning.textContent = "请至少选一项。"; return; }
    state.focus = selected;
    focusLabel();
    $("dialog").close();
  }, "action");
  const warning = element("p", "每个选中的重点会单独查资料、写成一章。");
  dialog("这份简报写哪些章节？", warning, ...labels, apply);
};
$("sources").onclick = () => {
  const rows = state.settings.sources.flatMap(s => [
    element("h3", s.publisher), link(s.title, s.url), element("p", s.published_at + " · " + s.locator)]);
  dialog("本次可检索的资料", ...rows);
};
$("model-info").onclick = () => {
  const model = state.settings.model;
  dialog("模型连接", element("p", model ? "服务端已配置 " + model + "。选择「用模型生成」后，模型会请求资料并撰写章节。" :
    "服务端尚未配置模型。请在 code/.env 设置 MODEL_ENDPOINT、MODEL_NAME 和 MODEL_API_KEY 后重启服务。"),
    element("p", "选择「离线演练」可用固定样例走一遍流程。"));
};
function controls() {
  const row = state.row;
  const readyToAsk = row && row.status === "ready" && row.mode === "live";
  $("composer").hidden = Boolean(row && !readyToAsk);
  $("mode").hidden = $("focus-btn").hidden = Boolean(row);
  $("send").title = row ? "发送追问" : "生成研究草稿";
  $("prompt").placeholder = row ? "就这份报告继续提问…" : "输入研究问题，或选下方的示例…";
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
  state.focus = [...state.settings.sections];
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
document.querySelectorAll("[data-focus]").forEach(b => b.onclick = () => {
  state.focus = [b.dataset.focus];
  focusLabel();
  $("prompt").value = b.textContent.replace("↗", "").trim();
  $("prompt").focus();
});
function citedText(text, style) {
  const p = element("p", undefined, style);
  const pieces = text.split(/(\*\*[^*\n]+\*\*|\[[\w-]+\])/g);
  for (const part of pieces) {
    const source = state.settings.sources.find(s => "[" + s.id + "]" === part);
    if (source) p.append(link(part, source.url));
    else if (part.startsWith("**") && part.endsWith("**")) p.append(element("strong", part.slice(2, -2)));
    else p.append(part);
  }
  return p;
}
function documentView(markdown) {
  const paper = element("div", undefined, "paper");
  for (const line of markdown.split("\n").filter(Boolean)) {
    const citation = /^\[([^\]]+)\]\((https:\/\/[^\s)]+)\)(.*)$/.exec(line);
    if (citation) {
      const p = element("p", undefined, "meta");
      p.append(link(citation[1], citation[2]), citation[3]);
      paper.append(p);
    } else if (line.startsWith("## ")) paper.append(element("h3", line.slice(3)));
    else if (line.startsWith("# ")) paper.append(element("h2", line.slice(2)));
    else if (line.startsWith("- ")) paper.append(citedText(line.slice(2), "metric"));
    else paper.append(element("p", line, line.startsWith("运行方式") ? "meta" : ""));
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
  if (row.status === "running") {
    const done = row.completed || [];
    const next = row.focus.find(name => !done.includes(name));
    article.append(element("p", next ? "正在检索资料、编写「" + next + "」…" : "正在整理草稿…"),
      element("p", "已完成 " + done.length + " / " + row.focus.length + " 章", "caption"));
  } else if (row.status === "failed") {
    article.append(element("p", row.error), button("继续生成", () => action("/retry", {}), "action"));
  } else {
    article.append(documentView(row.markdown), traceView(row.events));
    const actions = element("div", undefined, "actions");
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
  notice(suffix === "/ask" ? "模型正在阅读草稿并答复…" : "正在提交…");
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
  if (state.row) action("/ask", {question});
  else action("", {question, mode: $("mode").value, focus: state.focus});
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
  $("mode").querySelector('[value="live"]').disabled = !model;
  $("mode").value = model ? "live" : "fixture";
  const originalKey = location.hash.slice(1);
  fresh();
  if (/^[a-f0-9]{32}$/.test(originalKey)) await select(originalKey);
}
controls();
init().catch(err => notice(err.message));
