// Pass a localhost app with real archived data and an empty, model-free app.
// The optional write test only runs against a model named local-library-qa.
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const {chromium} = require("playwright");
const [active, offline] = process.argv.slice(2);
for (const url of [active,offline]) assert.ok(["localhost","127.0.0.1","[::1]"].includes(new URL(url).hostname));
const pictures = process.env.LIBRARY_SCREENSHOTS;

async function libraryTest(browser, width, height, baseURL, empty) {
  const context = await browser.newContext({baseURL,viewport:{width,height},acceptDownloads:true});
  await context.route("**/*", route => new URL(route.request().url()).origin === new URL(baseURL).origin
    ? route.continue() : route.abort());
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", err=>errors.push(err.message));
  const get = async route => {
    const response = await context.request.get("/api/research" + route);
    assert.equal(response.status(),200);
    return response.json();
  };
  try {
    const {reports} = await get("/references");
    const data = await get("/library");
    const {model} = await get("/settings");
    assert.ok(reports.some(r=>r.role === "industry") && reports.some(r=>r.role === "method"));
    await page.goto("/#library");
    const modal = page.getByRole("dialog",{name:"资料库"});
    await modal.locator(".library-card").first().waitFor();
    assert.equal(await modal.locator(".library-card").count(), reports.length);
    const first = reports.find(r=>r.role==="industry");
    const other = reports.find(r=>r.role==="method");
    const firstCard = modal.locator(".library-card").filter({has:page.getByRole("heading",{name:first.title,exact:true})});
    assert.ok((await firstCard.innerText()).includes(first.year + " 年出版"));
    assert.equal(await firstCard.getByRole("link").getAttribute("href"), first.url);
    await firstCard.locator("summary").click();
    assert.ok((await firstCard.innerText()).includes(first.sections[0].locator));
    await modal.getByRole("button",{name:"跨领域写法参考",exact:true}).click();
    assert.equal(await modal.locator(".library-card").count(), reports.filter(r=>r.role === "method").length);
    await modal.getByRole("button",{name:"全部",exact:true}).click();
    await modal.getByRole("heading",{name:first.title,exact:true}).waitFor();
    const widths = await modal.evaluate(el=>[el.scrollWidth,el.clientWidth,document.documentElement.scrollWidth,innerWidth]);
    assert.ok(widths[0] <= widths[1] + 1 && widths[2] <= widths[3] + 1, JSON.stringify(widths));
    if (pictures && !empty) await page.screenshot({path:path.join(pictures,"research-library-" + width + ".png")});
    if (empty) {
      assert.equal(model, null);
      assert.equal(await modal.getByRole("checkbox").count(),0);
      assert.match(await modal.innerText(),/配置模型后可为新研究选用报告/);
    }
    await modal.getByRole("button",{name:"原始数据",exact:true}).click();
    if (empty) {
      await modal.getByText(/本机还没有可查询的统计观测/).waitFor();
    } else {
      await modal.getByLabel("查询地区").selectOption("China");
      await modal.getByLabel("起始年份").fill("2020");
      await modal.getByLabel("结束年份").fill("2026");
      await modal.getByLabel("筛选指标").fill("光伏");
      await modal.getByRole("button",{name:"查询",exact:true}).click();
      const download = modal.getByRole("link",{name:"导出当前结果 CSV"});
      await download.waitFor();
      const url = new URL(await download.getAttribute("href"),baseURL);
      assert.equal(url.searchParams.get("metric"),"光伏");
      const waiting = page.waitForEvent("download");
      await download.click();
      const csv = await fs.readFile(await (await waiting).path(),"utf8");
      assert.match(csv,/region,year,metric,value,unit/);
      assert.match(csv,/China,20\d\d,[^\n]*光伏/);
    }
    await modal.getByRole("button",{name:"来源与政策"}).click();
    const sourceFilter = modal.getByLabel("筛选来源类别");
    await sourceFilter.selectOption("policy");
    if (empty) {
      await modal.getByText("本机还没有这一类来源。").waitFor();
    } else {
      const policies = data.sources.filter(s=>s.kind==="policy");
      assert.equal(await modal.locator(".source-record").count(), policies.length);
      const policy = policies.find(s=>s.passages > 0);
      assert.ok(policy);
      const card = modal.locator(".source-record").filter({has:page.getByRole("link",{name:policy.title,exact:true})}).first();
      assert.equal(await card.getByRole("link").getAttribute("href"),policy.url);
      await card.locator("summary").click();
      const passages = (await get("/library/" + policy.id + "/passages")).passages;
      await card.locator("blockquote").first().waitFor();
      assert.deepEqual(await card.locator("blockquote").allTextContents(), passages.map(p=>p.text));
    }
    await page.getByRole("button",{name:"关闭",exact:true}).click();
    await page.waitForFunction(()=>!location.hash);
    assert.equal(new URL(page.url()).hash, "");
    if (model === "local-library-qa") {
      await page.getByRole("button",{name:"参考报告",exact:true}).click();
      const selectFirst = modal.getByRole("checkbox",{name:"选用 " + first.title});
      const selectOther = modal.getByRole("checkbox",{name:"选用 " + other.title});
      await selectFirst.check();
      await selectOther.check();
      await modal.getByRole("button",{name:"保存选择"}).click();
      await page.getByRole("button",{name:"参考报告 · 2"}).waitFor();
      await page.getByLabel("研究问题",{exact:true}).fill("请比较光伏新增装机并注明口径。");
      await page.getByRole("button",{name:"发送问题"}).click();
      await page.getByRole("button",{name:"按这个范围写"}).waitFor();
      const id = new URL(page.url()).hash.slice(1);
      const row = await get("/" + id);
      assert.deepEqual(row.spec.reference_ids,[first.id,other.id]);
      assert.ok(row.spec.turns[0].answer.includes(first.title) && row.spec.turns[0].answer.includes(other.title));
      await page.reload();
      await page.getByRole("button",{name:"参考报告 · 2"}).click();
      assert.equal(await selectOther.isChecked(),true);
      const scope = {scope:"另一页更新的研究范围",target:row.spec.target,style:row.spec.style,
        outline:["另一页新写的章名"],source_groups:[]};
      assert.equal((await context.request.post("/api/research/" + id + "/scope",{data:scope})).status(),200);
      await selectOther.uncheck();
      await modal.getByRole("button",{name:"保存选择"}).click();
      await page.getByRole("button",{name:"参考报告 · 1"}).waitFor();
      assert.deepEqual((await get("/" + id)).spec.reference_ids, [first.id]);
      assert.deepEqual((await get("/" + id)).spec.outline, scope.outline);
      await page.locator("#focus-btn").click();
      assert.equal((await context.request.post("/api/research/" + id + "/scope",
        {data:{reference_ids:[other.id]}})).status(),200);
      await page.getByRole("button",{name:"保存",exact:true}).click();
      await page.getByRole("dialog").waitFor({state:"hidden"});
      assert.deepEqual((await get("/" + id)).spec.reference_ids, [other.id]);
    }
    assert.deepEqual(errors,[]);
    return {width,model,reports:reports.length,observations:data.observations,passages:data.passages,
      policies:data.sources.filter(s=>s.kind==="policy").length,selectionPersisted:model==="local-library-qa"};
  } finally { await context.close(); }
}

async function completedReport(browser, url) {
  const address = new URL(url);
  assert.ok(["localhost","127.0.0.1","[::1]"].includes(address.hostname));
  const key = address.hash.slice(1);
  assert.match(key, /^[a-f0-9]{32}$/);
  const page = await browser.newPage();
  try {
    const row = await (await page.request.get(address.origin + "/api/research/" + key)).json();
    assert.ok(row.writing_references.length);
    await page.goto(url);
    const panel = page.locator(".used-references");
    await panel.locator("summary").first().click();
    assert.deepEqual(await panel.locator("h4").allTextContents(), row.writing_references.map(r=>r.title));
    for (const [index,report] of row.writing_references.entries()) {
      const card = panel.locator(".library-card").nth(index);
      assert.equal(await card.getByRole("link").getAttribute("href"),report.url);
      await card.locator("summary").click();
      for (const section of report.sections) assert.ok((await card.innerText()).includes(section.lesson));
    }
    return row.writing_references.map(r=>r.title);
  } finally { await page.close(); }
}

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE || undefined});
  try {
    const desktop = await libraryTest(browser,1366,940,active,false);
    const mobile = await libraryTest(browser,390,844,active,false);
    const empty = await libraryTest(browser,390,844,offline,true);
    const snapshots = process.env.LIBRARY_SAVED_REPORT ? await completedReport(browser,process.env.LIBRARY_SAVED_REPORT) : [];
    console.log(JSON.stringify({desktop,mobile,empty,snapshots},null,2));
  } finally { await browser.close(); }
})().catch(err=>{console.error(err);process.exitCode=1;});
