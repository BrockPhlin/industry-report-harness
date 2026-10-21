'use strict';
const $ = (id) => document.getElementById(id);
let sourceCache = [];
function announce(message, error = false) { $('message').textContent = message; $('message').dataset.error = String(error); }
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message || '请求失败');
  return body;
}
function make(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
async function loadSources(selected) {
  const keep = selected || new Set([...document.querySelectorAll('input[name="source_id"]:checked')].map(n => n.value));
  sourceCache = await api('/api/sources');
  $('sources').replaceChildren();
  if (!sourceCache.length) { $('sources').append(make('p', '暂无资料，请先录入原文。', 'empty')); return; }
  sourceCache.forEach(source => {
    const item = make('div', undefined, 'source-item'); const label = make('label', undefined, 'source-check');
    const input = make('input'); input.type = 'checkbox'; input.name = 'source_id'; input.value = source.id; input.checked = keep.has(source.id);
    label.append(input, make('span', source.title, 'source-title'));
    item.append(label, make('div', `${source.publisher || '机构未填'} / ${source.published_at || '日期未填'} / ${source.body.length}字`, 'source-meta'));
    $('sources').append(item);
  });
}
async function loadReports() {
  const reports = await api('/api/reports'); $('reports').replaceChildren();
  if (!reports.length) $('reports').append(make('p', '尚无报告。', 'empty'));
  reports.forEach(report => {
    const button = make('button', `${report.topic} · ${report.mode === 'model' ? '模型' : '摘录'} · ${report.created_at}`);
    button.type = 'button'; button.addEventListener('click', () => showReport(report.id).catch(e => announce(e.message, true)));
    $('reports').append(button);
  });
}
async function showReport(id, report) {
  const value = report || await api(`/api/reports/${encodeURIComponent(id)}`);
  $('report-content').textContent = value.markdown;
  $('warnings').textContent = value.warnings.join(' '); $('warnings').hidden = !value.warnings.length;
  $('download').href = `/api/reports/${encodeURIComponent(value.id)}/download`; $('download').hidden = false;
  $('evidence').replaceChildren(); $('evidence-panel').hidden = false;
  value.sources.forEach((source, index) => {
    const section = make('div', undefined, 'evidence-source');
    section.append(make('h3', `[S${index + 1}] ${source.title}`), make('p', `${source.publisher || '机构未填'} / ${source.published_at || '日期未填'}`), make('pre', source.body));
    // Treat source URL as display text; never insert arbitrary source HTML.
    if (source.url) section.append(make('p', `原始链接：${source.url}`));
    $('evidence').append(section);
  });
}
$('source-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
  try {
    const data = Object.fromEntries(new FormData(event.target));
    const result = await api('/api/sources', { method: 'POST', body: JSON.stringify(data) });
    const selected = new Set([...document.querySelectorAll('input[name="source_id"]:checked')].map(n => n.value)); selected.add(result.id);
    event.target.reset(); await loadSources(selected); announce('资料已保存，并加入当前选择。');
  } catch (error) { announce(error.message, true); } finally { button.disabled = false; }
});
$('report-form').addEventListener('submit', async event => {
  event.preventDefault(); $('generate').disabled = true;
  try {
    const data = Object.fromEntries(new FormData(event.target));
    data.source_ids = [...document.querySelectorAll('input[name="source_id"]:checked')].map(n => n.value);
    if (!data.source_ids.length) throw new Error('请先选择资料。');
    announce(data.mode === 'model' ? '正在等待模型服务返回，基线不会自动重试。' : '正在根据原文生成摘录草稿…');
    const result = await api('/api/reports', { method: 'POST', body: JSON.stringify(data) });
    await showReport(result.id, result); await loadReports(); announce('草稿已保存，请核对原文与引用后使用。');
  } catch (error) { announce(error.message, true); } finally { $('generate').disabled = false; }
});
$('refresh').addEventListener('click', () => loadSources().catch(e => announce(e.message, true)));
Promise.all([loadSources(), loadReports()]).catch(e => announce(`读取失败：${e.message}`, true));
