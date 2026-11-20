#set page(paper: "a4", margin: (x: 23mm, y: 22mm))
#set text(font: "LXGW WenKai", lang: "zh", size: 12pt, fill: rgb("#20313c"))
#set par(leading: 0.7em, spacing: 0.85em, justify: true)
#set heading(numbering: none)
#let green = rgb("#16635b")
#let slate = rgb("#445a64")
#let pale = rgb("#e8f3ef")
#let rule = rgb("#c4d8d4")
#show heading.where(level: 1): it => block(above: 15pt, below: 13pt, text(fill: green, weight: "bold", size: 22pt, it.body))
#show heading.where(level: 2): it => block(above: 13pt, below: 6pt, text(fill: green, weight: "bold", size: 15pt, it.body))
#let doc-table(columns, ..cells) = {
  set text(size: 10.4pt)
  set par(leading: 0.6em)
  table(columns: columns, fill: (_, y) => if y == 0 { pale },
    stroke: 0.5pt + rule, inset: (x: 6pt, y: 7pt), ..cells)
}
#let node(label, detail) = block(width: 100%, fill: pale, inset: 8pt, radius: 3pt)[
  #text(weight: "bold", fill: green, label) \ #text(size: 9.4pt, fill: slate, detail)
]
#let arrow = align(center + horizon, text(fill: green)[→])
#let flow(a, b, c) = grid(columns: (1fr, 18pt, 1fr, 18pt, 1fr), a, arrow, b, arrow, c)

#v(28mm)
#text(fill: green, weight: "bold", size: 14pt)[《软件工程管理》　第11组]
#v(5mm)
#text(size: 35pt, fill: rgb("#133f40"), weight: "bold")[系统设计报告]
#v(1mm)
#text(size: 20pt)[产业智能报告生成系统]
#v(6mm)
#line(length: 100%, stroke: 1.2pt + green)
#v(5mm)
中期范围　2024年中国光伏产业简报

组长　程文博

组员　田亦洁、李佳雨、许子萌、崔大元、郭润航

版本　v0.1　　日期　2026年11月20日

#v(7mm)
== 目录
#link(<scope>)[1　规划与范围　1] \
#link(<architecture>)[2　总体架构与核心流程　2] \
#link(<interface>)[3　模块、接口与数据　3] \
#link(<validation>)[4　验证成果　4] \
#link(<next>)[5　变化、分工与后续　5]

#pagebreak()
#counter(page).update(1)
#set page(
  header: align(right, text(fill: slate, size: 9pt)[第11组　系统设计报告]),
  footer: align(center, context text(fill: slate, size: 9pt, counter(page).display("1"))),
)

= 1　规划与范围 <scope>

== 1.1　研究员要完成的工作

研究员需要把公开统计整理成一份方便审阅的产业简报。开题计划面向多产业、多类型报告。中期用开题已经准备的2024年中国光伏样例，只验证“制造与价格”和“发电新增装机”两个章节。案例为历史统计，适合固定输入、复核结果和重跑测试。

光伏组件产量描述制造环节，光伏新增装机描述发电建设。两者的统计对象和单位不同。中期要求在输出中保留指标、时段、数值及单位，并能从出处回到原文段落。核对通过后，用一个版式输出 PDF，并保留 Markdown。

== 1.2　中期需求与验收条件

#doc-table((14%, 26%, 60%),
  [编号], [需求], [验收条件],
  [M1], [按章节生成], [两个章节各有指定指标，数据行可回到发布机构及原文位置。],
  [M2], [处理证据缺失], [某指标没有证据时补查一次，仍无结果则标为待核实。],
  [M3], [审阅和导出], [保留可编辑 Markdown，明确确认后生成 PDF。缺项在 PDF 中仍可见。],
  [M4], [复核执行过程], [记录各次工具调用、采用的证据编号与待核实项，可用 CLI 输出 JSON。],
)

== 1.3　框架调研如何影响设计

#doc-table((25%, 75%),
  [参考], [项目中的应用],
  [DeepSeek Harness], [实测 SDK 会话向 MCP 注册的光伏工具发起调用，再把工具结果送回模型端点。业务流程采用相同的工具与模型分离方式。],
  [Pi Agent Harness], [实测 Pi 自定义工具与 JSON 事件。项目 CLI 保留可单独运行的证据查询，并允许检查已保存的调用记录。],
  [DeepSeek chat-demo], [参考按次查看文件与 Markdown 输出的交互方式。本轮从 CLI 进入审阅，聊天式页面留作后续。],
  [LangGraph], [用条件边把补查写入流程约束。Python 原型可沿用开题的 Chat Completions 接口。],
)

#pagebreak()

= 2　总体架构与核心流程 <architecture>

#flow(node("任务入口", "选择模式，读取模板与资料"), node("LangGraph 编排", "初查、条件补查、组装草稿"), node("核对及导出", "人工确认，Typst 生成 PDF"))
#v(7pt)
#flow(node("资料工具", "返回证据和原文定位"), node("模型适配", "发起工具调用与章节草稿"), node("运行记录", "保存调用、选用证据与缺项"))
#text(size: 10pt, fill: slate)[图1　中期模块关系。编排层调用资料工具和模型适配器，结果写入本地任务目录。]

== 2.1　执行环境

原型从 Python CLI 启动，模板和公开证据为仓库内 JSON。常规路径由 LangGraph 1.2.24 编排。正式 PDF 使用独立 Typst 模板，系统以 JSON 数据向模板传递 Markdown 各块内容。两个 Node.js 框架试验在独立本机进程和临时目录运行，复用项目的只读证据函数。

== 2.2　一次报告如何生成

#flow(node("模型请求指标", "按章节模板给出指标编号"), node("程序核对覆盖", "缺项补查一次，仍缺则登记"), node("生成指标行", "采用命中的证据，记录缺项"))
#text(size: 10pt, fill: slate)[图2　每个章节独立执行。从草稿进入人工核对后，才可确认导出。]

每章初查由模型请求产生。程序限定可查指标，检查工具结果是否覆盖模板要求，再决定是否补查。模型收到工具返回的数据后选择本章引用并可给出简短口径观察。程序直接从证据记录写入数值行，观察与事实行分开显示。离线模式用固定决策替换模型响应，以便重跑两个分支。

== 2.3　中期设计取舍

LangGraph 负责流程和分支，模型负责资料请求和辅助表述。每章最多两次本地查询。证据源使用公开的固定样例，便于对照和复核。真实接口失败时终止当前运行。可恢复的按章检查点属于后续工作，现阶段持久化范围为一次成功生成的产物及确认记录。

#pagebreak()

= 3　模块、接口与数据 <interface>

== 3.1　主要接口

#doc-table((28%, 35%, 37%),
  [接口], [输入], [输出与失败处理],
  [`pv_brief.py run`], [新任务目录、运行模式、可选排除的来源], [草稿、同源摘录、trace。目录已存在或模型缺配置时终止。],
  [`search_evidence`], [章节内允许的指标编号], [命中证据及原始出处。查不到返回空，框架可复用同一函数。],
  [`ChatWriter`], [章节约束、资料工具、工具返回], [工具请求及章节选择。拒绝非法调用、未命中编号和不合规观察。],
  [`pv_brief.py inspect`], [任务目录，接受 `--json`], [展示检索、补查、采用证据和待核实项。],
  [`pv_brief.py approve`], [任务目录、显式确认、可选修订稿], [校对后的 Markdown、PDF、确认哈希。拒绝挪动或改写关键指标、出处和缺项。],
)

== 3.2　源、任务与核对记录

#doc-table((22%, 42%, 36%),
  [实体], [核心字段], [关系或保存方式],
  [来源], [来源 ID、机构、标题、发布日期、链接、原文定位], [一份来源可对应多个证据条目。样例保存于 JSON。],
  [指标证据], [指标 ID、时段、数值、单位、来源 ID], [工具返回指标与关联来源。缺项有独立状态。],
  [章节模板], [章节标题、必需指标、解释口径], [一个报告模板有多个章节。每章使用自己的指标范围。],
  [任务记录], [模式、来源范围、阶段、命中编号、待核实项], [存入本地 trace。批准时核对草稿和任务记录。],
  [核对产物], [Markdown、PDF、状态、Markdown 哈希], [同一份核对 Markdown 作为版式渲染输入。],
)

任务目录按所有者本地权限读写，生成与导出先写临时目录，完成后再发布。模型凭据由环境或私有配置提供，调用记录保存受控字段。导出把内容当作数据读取，不赋予模板执行用户输入的权限。当前确认是本地工作流动作，责任人身份和审批记录需要后续接入。

#pagebreak()

= 4　验证成果 <validation>

== 4.1　用相同资料复现

以同一组公开历史资料分别运行开题摘录和当前工作流。对照项目为章节结构、来源定位与缺项处理，生成结果存入中期证据目录。资料完整与故意移除国家能源局资料构成两项业务用例。

#doc-table((25%, 31%, 44%),
  [验证], [观察点], [实际结果],
  [E1　完整资料], [制造、价格和新增装机共三项], [初查返回组件产量，补查找到价格，另一章返回新增装机。三项均有证据。],
  [E2　缺少装机资料], [初查和补查是否有数据], [两次均空，草稿和 PDF 保留一个待核实项。],
  [E3　同源摘录对照], [检查输入相同], [摘录列出原始条目。当前版本增加章节约束、调用记录、原文定位与确认导出。],
  [E4　DeepSeek Harness], [SDK、MCP、模拟模型], [工具返回条目随第二次请求发回本机端点。],
  [E5　Pi CLI], [JSON 模式、自定义工具、模拟模型], [返回相同证据，且得到工具执行完成事件与结束事件。],
  [E6　回归与失败校验], [执行 Python 测试及 Typst 导出], [18项基线测试和7项中期测试通过。验证包括不合规证据拒绝、审阅保护和 PDF 导出。],
)

== 4.2　结果可解释的范围

E1、E2 使用实际 LangGraph 流程与固定决策，证明程序按约束运行。E4、E5 分别运行真实框架和模拟模型服务，验证接入与工具结果回传。真实 GLM 接入在当前环境缺配置，真实模型质量、延时和费用均待测。终期可用相同数据比较单次模型与 Agent，人工逐条核对指标、时段、来源支持和缺项保留情况。

== 4.3　代表性失败模式

证据缺失时，补查上限为一次，保留待核实项。工具编号超出章节范围时终止该次任务。模型输出引用未返回的编号时拒绝草稿。改动已保护的数值、来源或缺项时，程序要求回到原稿核对。导出失败时不会产生完成收据。

#pagebreak()

= 5　变化、分工与后续 <next>

== 5.1　需求、设计、实现与验证

#doc-table((13%, 39%, 48%),
  [编号], [实现], [对应证据],
  [M1], [JSON 模板、资料函数、LangGraph 草稿节点], [E1，三项结构化证据保留原文链接。],
  [M2], [覆盖检查、补查节点、缺项记录], [E2，移除来源后补查为空，仍显示待核实。],
  [M3], [Markdown 审阅、确认命令、Typst 模板], [E1、E2、E6，比较导出件与收据。],
  [M4], [CLI 的 inspect、框架探针], [E1、E2、E4、E5，定位工具返回与下一次请求。],
)

== 5.2　按 Agent 任务组织中期交接

拟由程文博协调范围与验收，田亦洁维护模板和需求，崔大元完善证据工具，许子萌接编排与真实模型，李佳雨负责人工审阅和 PDF，郭润航负责失败用例、证据与演示。交接以指标字段、接口样例、输出与验证记录为准。拟于11月23日周一课后确认，11月27日联调，11月29日彩排。展示日期以课程通知为准。

开题阶段的课程映射与公开光伏样例已进入本轮材料和原型。原始提交分别为 `8dff737`、`aafb9a2`，两次交付可按提交核对。中期由各成员完成的实际交接将在发生后记录。

== 5.3　中期后优先事项

- 先运行真实模型的完整资料和缺资料用例，积累人工核对的样本并记录调用开销。
- 实现按章保存与恢复。用中断测试证明恢复后不重复生成已完成章节。
- 用第二个能源简报验证资料与模板能否复用，评估扩展模板与版式的成本。

== 5.4　AI 使用与复核

AI 辅助实现代码、编写测试和制作材料。工程结果以实际命令、运行产物和自动测试为依据。公开统计与框架能力回到官方资料核对。小组需要复核范围、业务口径和答辩中的结论，真实协作记录在相应任务产生后补入。

#pagebreak()

= 参考资料与版本记录

- #link("https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/sdk")[DeepSeek Harness SDK] 与 #link("https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/mcp/mcp-client")[MCP 客户端]。
- #link("https://github.com/earendil-works/pi/tree/main/packages/coding-agent")[Pi coding agent CLI] 与 #link("https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md")[扩展文档]。
- #link("https://github.com/deepseek-ai/chat-demo")[DeepSeek chat-demo]。
- #link("https://docs.langchain.com/oss/python/langgraph/graph-api")[LangGraph Graph API]。
- #link("https://wap.miit.gov.cn/gyhxxhb/jgsj/dzxxsnew/xyyx/art/2025/art_1717bf6fa0a34311a2c347fb9623e607.html")[工信部　2024年全国光伏制造行业运行情况]。
- #link("https://www.nea.gov.cn/20250221/e10f363cabe3458aaf78ba4558970054/c.html")[国家能源局　2024年可再生能源并网运行情况]。

证据 E1 至 E6 的复现命令、调用记录和样张见仓库中期目录下的 evidence。

正文篇幅　5页。Typst 源稿对应 PDF 提取文本共3,341个非空白字符，含正文表格与图注。

v0.1，2026年11月20日。收敛到光伏简报，补充框架比较、技术设计和离线证据。保留开题文件作为原计划对照。
