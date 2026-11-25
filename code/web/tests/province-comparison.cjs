// Use an isolated local app database. Run node with Playwright available and pass
// its localhost origin as the sole argument. BROWSER_EXECUTABLE can override Chromium.
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const {chromium} = require("playwright");

const baseURL = process.argv[2];
const origin = new URL(baseURL);
assert.ok(["127.0.0.1", "localhost", "[::1]"].includes(origin.hostname), "请提供隔离的本机服务地址");
const pictureDir = process.env.COMPARISON_SCREENSHOTS;

async function download(page, name) {
  const waiting = page.waitForEvent("download");
  await page.getByRole("link", {name, exact:true}).click();
  return fs.readFile(await (await waiting).path());
}

async function noPageOverflow(page) {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "页面横向溢出");
}

async function runPage(browser, width, height) {
  const ctx = await browser.newContext({viewport:{width,height}, baseURL, acceptDownloads:true});
  await ctx.route("**/*", route => new URL(route.request().url()).origin === origin.origin
    ? route.continue() : route.abort());
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", err => errors.push(err.message));
  try {
    await page.goto("/");
    await page.getByRole("button", {name:"分省数据对比"}).click();
    const submit = page.getByRole("button", {name:"生成对比报告"});
    await submit.waitFor();
    await noPageOverflow(page);
    await submit.click();
    const result = page.locator(".comparison-report");
    await result.waitFor();
    const key = new URL(page.url()).hash.slice(1);
    assert.match(key, /^[a-f0-9]{32}$/);
    const tr = result.locator("tbody tr");
    assert.deepEqual(await tr.locator('th[scope="row"]').allTextContents(), ["浙江","湖北","江西"]);
    const defaultCells = await tr.last().locator("td").allTextContents();
    assert.deepEqual(defaultCells.slice(1), ["17.6","-41.9","-59.5","-338.07%"]);
    await noPageOverflow(page);
    if (pictureDir) await page.screenshot({path:path.join(pictureDir,"province-comparison-" + width + ".png"), fullPage:true});
    const offline = !(await (await page.request.get("/api/research/settings")).json()).model;
    if (offline) assert.equal(await result.getByRole("button", {name:"继续研究这组数据"}).count(), 0);
    const md = await download(page, "下载 Markdown");
    const json = JSON.parse(await download(page, "计算明细 JSON"));
    const ranked = json.rows.find(row => row.region === "江西");
    assert.equal(defaultCells[0], ranked.before_rank == null ? "3" : "3 → 3");
    const pdf = await download(page, "下载 PDF");
    assert.equal(pdf.subarray(0,5).toString(), "%PDF-");
    assert.equal(json.markdown_sha256, crypto.createHash("sha256").update(md).digest("hex"));
    for (const s of json.sources) {
      assert.equal(await result.getByRole("link",{name:s.title}).getAttribute("href"), s.url);
      assert.equal(await result.locator("a").evaluateAll((links,href)=>links.some(l=>l.href===href),s.data_url), true);
    }
    await page.reload();
    await result.waitFor();
    assert.equal(await tr.count(), 3);
    await result.getByRole("button",{name:"调整对比条件"}).click();
    await page.getByLabel("统计期").selectOption("annual");
    await page.getByLabel("比较指标").selectOption("total_stock");
    await page.locator(".region-options summary").click();
    await page.getByRole("button",{name:"清空",exact:true}).click();
    await page.getByRole("checkbox",{name:"新疆",exact:true}).check();
    assert.equal(await submit.isDisabled(), true);
    await page.getByRole("checkbox",{name:"新疆兵团",exact:true}).check();
    await submit.click();
    await result.getByRole("heading",{name:"缺项或口径变化的地区"}).waitFor();
    assert.equal(await tr.count(), 0);
    assert.equal(await result.locator(".comparison-missing li").count(), 2);
    assert.match(await result.locator(".comparison-missing").innerText(),/2024.*新疆兵团/);
    await noPageOverflow(page);
    await result.getByRole("button",{name:"调整对比条件"}).click();
    await page.getByLabel("统计期").selectOption("three_quarters");
    await page.getByLabel("比较指标").selectOption("total_new");
    await page.locator(".region-options summary").click();
    await page.getByRole("button",{name:"清空",exact:true}).click();
    for (const region of ["河南","浙江","山东"]) {
      await page.getByRole("checkbox",{name:region,exact:true}).check();
    }
    await submit.click();
    await result.getByRole("rowheader",{name:"河南"}).waitFor();
    assert.deepEqual(await tr.locator('th[scope="row"]').allTextContents(), ["河南","浙江","山东"]);
    assert.deepEqual(await tr.locator("td:first-child").allTextContents(), ["3 → 1","2 → 2","1 → 3"]);
    if (width < 760) await page.getByRole("button",{name:"打开历史研究"}).click();
    await page.locator('#history button[data-key="' + key + '"]').click();
    await result.getByRole("heading",{name:json.plan.metric_label,exact:true}).waitFor();
    assert.equal(new URL(page.url()).hash, "#" + key);
    await noPageOverflow(page);
    assert.deepEqual(errors,[]);
    return {key, width, ranked:3, missing:2, rankChange:"河南 3 → 1", downloads:3, sha256:json.markdown_sha256};
  } finally {
    await ctx.close();
  }
}

// The comparison itself and its downloads use the real server above. Intercept
// the model-facing controls here to exercise both submit paths without any paid calls.
async function composerContract(browser, key) {
  const ctx = await browser.newContext({baseURL});
  const page = await ctx.newPage();
  const fail = {status:400,json:{error:{message:"已收到测试请求"}}};
  const bodies = [];
  await page.route("**/api/research/settings", async route => {
    const response = await route.fetch();
    await route.fulfill({json:{...await response.json(),model:"本机界面测试"}});
  });
  await page.route("**/api/research", async route => {
    if (route.request().method() !== "POST") return route.continue();
    bodies.push(route.request().postDataJSON());
    return route.fulfill(fail);
  });
  try {
    await page.goto("/#" + key);
    const resume = page.getByRole("button",{name:"继续研究这组数据"});
    await resume.click();
    await page.getByRole("link",{name:"已附上这份对比报告"}).waitFor();
    assert.equal(await page.locator("#attached-link").getAttribute("href"), "#" + key);
    for (const word of ["江西","湖北","浙江","上半年","集中式光伏"]) {
      assert.ok((await page.locator("#prompt").inputValue()).includes(word));
    }
    const question = "请解释三省该指标的不同变化。";
    await page.locator("#prompt").fill(question);
    for (const workflow of ["direct","discuss"]) {
      await page.locator("#workflow").selectOption(workflow);
      const sent = page.waitForResponse(r=>r.url().endsWith("/api/research")&&r.request().method()==="POST");
      await page.getByRole("button",{name:"发送问题"}).click();
      await sent;
      const body = bodies.at(-1);
      assert.equal(body.workflow, workflow);
      assert.equal(body.comparison_id, key);
      assert.equal(body.question, question);
    }
    await page.getByRole("button",{name:"移除",exact:true}).click();
    assert.equal(await page.locator("#attached-comparison").isHidden(),true);
    await page.locator('#history button[data-key="' + key + '"]').click();
    await resume.click();
    await page.getByRole("button",{name:"新建研究",exact:false}).click();
    assert.equal(await page.locator("#attached-comparison").isHidden(), true);
  } finally {
    await ctx.close();
  }
}

// A model-free long-report fixture exercises citation rendering. Its references
// come from the actual comparison the preceding browser test saved.
async function citationNavigation(browser, key, savedId) {
  const ctx = await browser.newContext({baseURL});
  try {
    const sample = "00000000000000000000000000000001";
    const page = await ctx.newPage();
    let ref = "E1";
    if (savedId) {
      const child = await (await ctx.request.get("/api/research/" + savedId)).json();
      key = child.spec.comparison_id;
      const used = child.evidence.find(s => s.comparison_id === key && child.markdown.includes("[" + s.ref + "]"));
      assert.ok(used, "正文应引用一条由对比报告计算的证据");
      ref = used.ref;
    }
    const row = await (await ctx.request.get("/api/research/" + key)).json();
    const {sources, plan} = row.comparison;
    if (!savedId) await page.route("**/api/research/" + sample, route => route.fulfill({json:{
      id:sample, question:"对比证据界面样本", mode:"live", model:"界面测试", status:"ready",
      markdown:"# 引用检查\n数据见两期原表[E1]。", length:8, revision:"test",
      spec:{target:800,comparison_id:key}, retrieval:[], answers:[], evidence:[{
        ref:"E1", comparison_id:key, sources, title:plan.metric_label, locator:plan.period_label,
        publisher:"测试样本", text:"两期观测值", digest:row.revision, fetched:row.created
      }]
    }}));
    await page.goto("/#" + (savedId || sample));
    const parent = page.getByRole("link",{name:"查看本次研究所用的对比报告"});
    assert.equal(await parent.getAttribute("href"), "#" + key);
    await page.getByRole("button",{name:"[" + ref + "]",exact:true}).first().click();
    const dialog = page.getByRole("dialog");
    for (const [i, name] of ["前期原表","后期原表"].entries()) {
      assert.equal(await dialog.getByRole("link",{name:new RegExp(name)}).getAttribute("href"), sources[i].data_url);
    }
    await dialog.getByRole("link",{name:"打开原对比报告"}).click();
    await page.locator(".comparison-table").waitFor();
    assert.equal(new URL(page.url()).hash, "#" + key);
    assert.equal(await dialog.isVisible(), false);
    return {report:savedId || "fixture", ref, originalSources:sources.map(s=>s.year), parent:key};
  } finally {
    await ctx.close();
  }
}

(async () => {
  const browser = await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE || undefined});
  try {
    const desktop = await runPage(browser,1366,940);
    const mobile = await runPage(browser,390,844);
    await composerContract(browser, desktop.key);
    const citation = await citationNavigation(browser, desktop.key, process.env.COMPARISON_RESEARCH_ID);
    console.log(JSON.stringify({desktop,mobile,composer:["direct","discuss","remove","reset"],
      citation},null,2));
  } finally {
    await browser.close();
  }
})().catch(err=>{console.error(err);process.exitCode=1;});
