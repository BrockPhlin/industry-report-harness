// Run against an isolated local app. A local PDF export requires Typst.
// MIDTERM_SCREENSHOTS is an optional existing directory for presentation captures.
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");

const url = new URL(process.argv[2]);
assert.ok(["localhost","127.0.0.1","[::1]"].includes(url.hostname));

async function verify(browser, name, width, height) {
  const context = await browser.newContext({baseURL:url.origin,viewport:{width,height},deviceScaleFactor:1,acceptDownloads:true});
  await context.route("**/*", route => new URL(route.request().url()).origin === url.origin ? route.continue() : route.abort());
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", err=>errors.push(err.message));
  async function screenshot(label) {
    if (process.env.MIDTERM_SCREENSHOTS) await page.screenshot({
      path:path.join(process.env.MIDTERM_SCREENSHOTS,label + "-" + name + ".png")});
  }
  async function noOverflow() {
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  }
  try {
    await page.goto("/");
    const run = page.getByRole("button",{name:"生成示例简报"});
    await run.waitFor();
    await page.locator(".cover-number").first().waitFor();
    assert.deepEqual(await page.locator(".cover-number b").allTextContents(),["588","2.78"]);
    const samples = page.getByRole("region", {name:"真实 GLM 样张"});
    for (const loc of ["/samples/2024-full.pdf","/samples/2024-missing.pdf"]) {
      const sampleLink = samples.locator('a[href="' + loc + '"]');
      assert.ok((await sampleLink.boundingBox()).height >= 44);
      const sample = await context.request.get(loc);
      assert.equal((await sample.body()).subarray(0,5).toString(),"%PDF-");
    }
    const menu = page.getByRole("button",{name:"打开研究菜单"});
    if (width <= 560) await menu.click();
    await page.getByRole("button",{name:"离线示例可用"}).click();
    await page.getByRole("dialog",{name:"模型连接"}).waitFor();
    await page.getByRole("button",{name:"关闭",exact:true}).click();
    if (width <= 560) await page.getByRole("button",{name:"关闭历史研究"}).click();
    assert.ok(await page.locator("#offline-info").isVisible());
    assert.ok(await page.locator("#composer").isHidden());
    await noOverflow();
    await screenshot("home");
    const created = page.waitForRequest(req=>req.method()==="POST"&&new URL(req.url()).pathname==="/api/research");
    await run.click();
    const payload = (await created).postDataJSON();
    assert.equal(payload.mode,"fixture");
    assert.deepEqual(payload.focus,["制造与价格","发电新增装机"]);
    const report = page.locator(".brief-sheet");
    await report.waitFor({timeout:30000});
    const key = new URL(page.url()).hash.slice(1);
    const row = async ()=>(await (await context.request.get("/api/research/" + key)).json());
    assert.match((await row()).markdown,/588 GW/);
    assert.equal(await report.locator(".fact-line").count(),3);
    assert.ok(await page.locator("#breadcrumb").evaluate(el=>el.scrollWidth <= el.clientWidth + 1));
    for (const line of await report.locator(".fact-line").all()) {
      const value = await line.locator("strong").boundingBox();
      const control = await line.getByRole("button",{name:/来源/}).boundingBox();
      assert.ok(control.height >= (width <= 560 ? 44 : 32));
      assert.ok(control.y >= value.y + value.height - 1);
    }
    await noOverflow();
    await screenshot("brief");
    await report.getByRole("button",{name:"来源 [NEA]",exact:true}).click();
    const card = page.getByRole("dialog",{name:"NEA · 核对来源"});
    await card.waitFor();
    assert.match(await card.innerText(),/2.78 亿千瓦/);
    assert.match(await card.innerText(),/（三）光伏发电建设和运行情况/);
    assert.match(await card.getByRole("link").getAttribute("href"),/^https:\/\/www\.nea\.gov\.cn\//);
    assert.match(await report.locator(".fact-line.checking").textContent(), /2.78 亿千瓦/);
    await screenshot("source");
    await page.getByRole("button",{name:"关闭",exact:true}).click();
    await report.locator(".fact-line.checking").waitFor({state:"detached"});
    await report.getByRole("button",{name:"核对并导出 PDF"}).click();
    await page.getByRole("button",{name:"确认并生成 PDF"}).click();
    const file = report.getByRole("link",{name:"下载已核对的 PDF"});
    await file.waitFor();
    assert.equal((await row()).approved,true);
    await page.evaluate(()=>scrollTo(0,0));
    await screenshot("approved");
    const downloaded = page.waitForEvent("download");
    await file.click();
    assert.equal((await fs.readFile(await (await downloaded).path())).subarray(0,5).toString(),"%PDF-");
    await page.reload();
    await report.getByRole("link",{name:"下载已核对的 PDF"}).waitFor();
    assert.deepEqual(errors,[]);
    return {viewport:[width,height],sources:["MIIT","NEA"],metrics:3,approved:true,verifiedPDF:true};
  } finally {await context.close();}
}

// Simulate an interrupted worker and a rejected submission on the loopback app.
async function failureStates(browser) {
  const page = await browser.newPage({baseURL:url.origin});
  try {
    await page.route("**/api/research/settings", route=>route.abort(), {times:1});
    await page.goto("/");
    await page.getByRole("button",{name:"重新连接"}).click();
    await page.locator(".cover-number").first().waitFor();
    const key = "00000000000000000000000000000002";
    const task = {id:key,status:"failed",mode:"live",question:"中断的研究",error:"上次运行中断，可从已完成的章节继续。"};
    await page.route("**/api/research/" + key, route=>route.fulfill({json:task}));
    await page.goto("/#" + key);
    await page.getByRole("heading",{name:"生成已中断"}).waitFor();
    assert.equal(await page.getByRole("button",{name:"继续生成"}).isDisabled(),true);
    await page.getByRole("button",{name:"新建研究"}).click();
    await page.route("**/api/research",route=>route.request().method()==="POST"
      ? route.fulfill({status:503,json:{error:{message:"测试服务暂不可用"}}}) : route.continue());
    const run = page.getByRole("button",{name:"生成示例简报"});
    await run.click();
    await page.getByText("测试服务暂不可用").waitFor();
    assert.equal(await run.isEnabled(),true);
  } finally {await page.close();}
}

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE || undefined});
  try {
    console.log(await verify(browser,"desktop",1440,960));
    console.log(await verify(browser,"mobile",390,844));
    await failureStates(browser);
  } finally { await browser.close(); }
})().catch(err=>{console.error(err);process.exitCode=1;});
