import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const directory = path.join(root, "presentations/02-midterm/ppt");
const bundle = path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies");
const modules = process.env.ARTIFACT_NODE_MODULES || path.join(bundle, "node/node_modules");
const skill = process.env.PRESENTATION_SKILL_DIR;
if (!skill) throw new Error("Set PRESENTATION_SKILL_DIR to the installed presentation skill directory");
process.env.RUNTIME_NODE_MODULES ||= modules;
const { FileBlob, Presentation, PresentationFile } = await import(pathToFileURL(path.join(modules, "@oai/artifact-tool/dist/artifact_tool.mjs")));
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, "container_tools/artifact_tool_utils.mjs")));
const require = createRequire(path.join(modules, "../package.json"));
const { GlobalFonts } = require("@napi-rs/canvas");
const { PDFDocument } = require("pdf-lib");
for (const [file, name] of [["LXGWWenKai-Regular.ttf", "LXGW WenKai"], ["SmileySans-Oblique.ttf", "Smiley Sans Oblique"]]) {
  if (!GlobalFonts.registerFromPath(path.join(root, "assets/fonts", file), name)) throw new Error("Font registration failed: " + name);
}

const spec = JSON.parse(await fs.readFile(path.join(directory, "slides.json"), "utf8"));
const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const dark = "#123C3C", green = "#16635B", body = "#213440", slate = "#42615E";
const paper = "#F6F8F5", white = "#FFFFFF", pale = "#D5E5DD";
const titleFont = "Smiley Sans Oblique", font = "LXGW WenKai";

function text(slide, value, x, y, w, h, style = {}) {
  const shape = slide.shapes.add({ geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none", line: { fill: "none", width: 0 } });
  shape.text = value;
  shape.text.style = { fontSize: 30, typeface: font, color: body,
    verticalAlignment: "middle", wrap: "none", autoFit: "none",
    insets: { left: 0, right: 0, top: 0, bottom: 0 }, ...style };
}
function rule(slide, x, y, w, fill = pale) {
  slide.shapes.add({ geometry: "rect", position: { left: x, top: y, width: w, height: 1.5 },
    fill, line: { fill: "none", width: 0 } });
}

function rows(slide, entries) {
  const height = entries.length === 4 ? 82 : 98;
  entries.forEach(([label, note], index) => {
    const y = 258 + index * height;
    rule(slide, 76, y, 1120);
    text(slide, label, 76, y + 9, 286, height - 15, { fontSize: 30, bold: true, color: green });
    text(slide, note, 380, y + 9, 816, height - 15, { fontSize: 29 });
  });
}

function lower(slide, lines = [], y = 594) {
  lines.forEach((line, index) => text(slide, line, 76, y + index * 35, 1130, 34,
    { fontSize: 25, color: slate }));
}

function addSlide(item, index) {
  const slide = deck.slides.add();
  slide.background.fill = item.kind === "cover" ? dark : paper;
  if (item.kind === "cover") {
    text(slide, item.lead, 76, 75, 1100, 46, { fontSize: 30, color: "#D4E7DD" });
    text(slide, item.title, 76, 193, 1120, 105, { typeface: titleFont, color: white, fontSize: 77 });
    text(slide, item.subject, 76, 330, 1120, 60, { color: "#E3F3E8", fontSize: 42 });
    rule(slide, 76, 448, 1120, "#629C8B");
    text(slide, "组长  程文博    组员  田亦洁、李佳雨、许子萌、崔大元、郭润航", 76, 469, 1120, 42,
      { color: white, fontSize: 28 });
    text(slide, "展示人（拟）  郭润航", 76, 526, 1120, 42, { color: white, fontSize: 28 });
    text(slide, "v0.1  ·  2026年11月20日", 76, 642, 770, 26, { color: "#D4E7DD", fontSize: 19 });
  } else {
    text(slide, item.phase, 76, 54, 1100, 34, { color: green, fontSize: 24, bold: true });
    text(slide, item.title, 76, 108, 1120, 68, { color: dark, typeface: titleFont, fontSize: 49 });
    text(slide, item.lead, 76, 199, 1130, 39, { color: slate, fontSize: 30 });
    if (item.kind === "flow") {
      item.steps.forEach(([label, detail], i) => {
        const x = 76 + i * 382;
        rule(slide, x, 300, 330, green);
        text(slide, label, x, 317, 330, 54, { fontSize: 33, bold: true, color: green });
        text(slide, detail, x, 385, 323, 82, { fontSize: 28, wrap: "square", verticalAlignment: "top" });
        if (i < 2) text(slide, "→", x + 330, 320, 45, 48, { color: green, fontSize: 32 });
      });
      lower(slide, item.lower, 540);
    } else if (item.kind === "demo") {
      item.procedure.forEach((line, i) => text(slide, (i + 1) + "   " + line, 79, 267 + i * 64, 1100, 50, { fontSize: 32 }));
      rule(slide, 76, 487, 1120, green);
      text(slide, item.outcome, 76, 511, 1120, 63, { fontSize: 43, bold: true, color: green });
      lower(slide, ["现场演示使用离线流程验证，保留实际生成的输出。"], 599);
    } else if (item.kind === "metrics") {
      item.metrics.forEach(([number, label], i) => {
        const x = 76 + i * 382;
        rule(slide, x, 274, 336, green);
        text(slide, number, x, 295, 339, 95, { color: green, fontSize: 73, typeface: titleFont });
        text(slide, label, x, 408, 344, 55, { fontSize: 25, wrap: "square", verticalAlignment: "top" });
      });
      lower(slide, item.lower, 534);
    } else {
      rows(slide, item.rows);
      lower(slide, item.lower);
    }
    rule(slide, 76, 660, 1120);
    text(slide, "第11组  中期展示", 76, 666, 265, 27, { color: slate, fontSize: 17 });
    text(slide, String(index + 1).padStart(2, "0") + " / " + String(spec.slides.length).padStart(2, "0"),
      1070, 666, 125, 27, { color: slate, fontSize: 17, alignment: "right" });
  }
  slide.speakerNotes.text = [item.speech, ...(item.sources || [])].join("\n");
}

spec.slides.forEach(addSlide);
await fs.mkdir(path.join(root, ".build/midterm"), { recursive: true });
const build = await fs.mkdtemp(path.join(root, ".build/midterm/deck-"));
const candidatePath = path.join(build, "candidate.pptx");
const validated = path.join(build, "validated");
await fs.mkdir(validated);
const finalPath = path.join(validated, "result.pptx");
await (await PresentationFile.exportPptx(deck)).save(candidatePath);
const helper = (file) => path.join(skill, "container_tools", file);
await finalizePresentation({
  workspaceDir: root, candidatePath, finalPath,
  explicitTotalSlideCount: spec.slides.length,
  pythonExecutable: process.env.RUNTIME_PYTHON || path.join(bundle, "python/bin/python3"),
  integrityValidatorPath: helper("inspect_presentation_package_integrity.py"),
  layoutValidatorPath: helper("inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-heading-fit"],
  fontPolicy: { basis: "design", families: [font, titleFont] },
  verifyArtifactToolImport: true, receiptPath: path.join(build, "validation.json"),
});
const output = path.join(directory, "第11组_中期展示_" + spec.version + ".pptx");
const pdfOutput = output.replace(/\.pptx$/, ".pdf");
const rendered = await PresentationFile.importPptx(await FileBlob.load(finalPath));
const pdf = await PDFDocument.create();
pdf.setTitle("第11组中期展示");
for (const [i, slide] of rendered.slides.items.entries()) {
  const raster = await rendered.export({ slide, format: "png", scale: 2 });
  const png = await raster.arrayBuffer();
  await fs.writeFile(path.join(build, "slide-" + (i + 1) + ".png"), Buffer.from(png));
  const graphic = await pdf.embedPng(png);
  const page = pdf.addPage([960, 540]);
  page.drawImage(graphic, { x: 0, y: 0, width: 960, height: 540 });
}
await fs.writeFile(pdfOutput + ".tmp", await pdf.save());
await fs.copyFile(finalPath, output + ".tmp");
await fs.rename(output + ".tmp", output);
await fs.rename(pdfOutput + ".tmp", pdfOutput);
const speech = ["# 第11组中期展示讲稿", "", "全程7分钟。演示环境使用离线决策和公开资料。"];
for (const [index, item] of spec.slides.entries()) {
  speech.push("", "## " + (index + 1) + "　" + item.title + "（" + item.seconds + "秒）", "", item.speech);
  if (item.kind === "demo") speech.push("", "操作顺序见[中期验证记录](../evidence/README.md)，使用缺少国家能源局资料的任务。");
}
await fs.writeFile(path.join(directory, "讲稿.md"), speech.join("\n") + "\n");
console.log(output);
