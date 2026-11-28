# 中期验证记录

2026-11-20、2026-11-21 与 2026-11-24 执行。数据是公开历史统计摘编。E1、E2、E9 使用 LangGraph 和固定离线决策。DeepSeek Harness 和 Pi 使用本机模拟模型，验证工具连接和结果回传。E7、E8 使用组长提供的智谱服务，分别验证两组资料联调和一次中断恢复。

本页编号在报告中统一引用为“中期 E1–E9”；[封版后验证](../../03-final/evidence/README.md)引用为“补充 E9–E12”。中期 E9 是独立复跑，补充 E9 是合成冲突试验。

[中期来源表](中期来源表.md) · [PDF](中期来源表.pdf)：崔大元于 2026-11-26 核对三项指标的数值、单位、统计期、官方链接与原文段落。

| 编号 | 环境与输入 | 观察结果与产物 |
| --- | --- | --- |
| E1 | LangGraph 1.2.24，工信部与国家能源局两份资料 | 3项指标都可定位，制造章补查一次找回价格指标。见[完整简报](光伏简报_完整资料.pdf)及[完整 trace](trace-full.json)。 |
| E2 | 同一 LangGraph 流程，仅保留工信部资料 | 装机查找和补查均为空，草稿保留1个待核实项，导出后仍标明缺项。见[缺资料简报](光伏简报_缺装机资料.pdf)及[缺资料 trace](trace-missing.json)。 |
| E3 | 开题摘录模式和 E1 使用相同数据 | [基线摘录](同源摘录基线.md)列出原始条目。E1增加章节、补查、来源定位和显式确认。此对照验证工作流差别。 |
| E4 | DeepSeek Harness 0.2.2-rc.5，SDK 接只读 MCP，模拟 Messages 服务 | 第二次请求带回了装机证据。见[DeepSeek 收据](deepseek-harness.json)。 |
| E5 | Pi 1.6.0，JSON 模式接只读扩展，模拟 Chat Completions 服务 | 第二次请求带回了装机证据，CLI 写出工具与任务事件。见[Pi 收据](pi-cli.json)。 |
| E6 | Python 3.12，既有基线及中期自动测试 | 18项基线测试、9项中期测试通过，包括同源完整与缺失、接口模拟、伪造编号拒绝、审阅保护和真实 Typst 导出。 |
| E7 | GLM-5.3-Flash，完整资料与缺装机资料 | 完整资料3项指标均可回查。缺装机资料时初查和补查均为空，PDF 保留1项待核实。一条不合规的附加观察被省略并记入 trace。 |
| E8 | GLM-5.3-Flash，第一章完成后主动退出进程，再以同一输入恢复 | 新进程跳过第一章，剩余章节跑完，生成的 PDF 通过导出检查。见[运行记录](glm-resume.json)。 |
| E9 | LangGraph fixture 离线流程，郭润航独立复跑完整资料与缺装机资料 | 同栏结果与 E7 一致：完整资料 2.78 亿千瓦 [NEA]；缺装机为待核实；两份制造指标均为 588 GW、价格同比下降 29.7%。见[完整资料 fixture PDF](光伏简报_郭润航fixture完整资料.pdf)、[缺装机 fixture PDF](光伏简报_郭润航fixture缺装机资料.pdf)及[同栏对照图](发电新增装机_同栏对照_郭润航fixture.png)。 |

E8 的中断由测试代码在第二章开始前注入。新进程若再次查询第一章则测试失败。运行记录中的 `resumed_sections` 为 1，待核实项为 0，第二章标记为从头重跑 1 次。

E9 由郭润航在 2026-11-24 用固定离线流程独立复跑，不调用真实模型。它验证同一模板、同一资料组合下的同栏可复现性；原说明见[郭润航_样张说明](郭润航_样张说明.md)。

E7 产物包括[完整资料 PDF](光伏简报_GLM完整资料.pdf)、[缺装机资料 PDF](光伏简报_GLM缺装机资料.pdf)、[完整资料 trace](glm-full.json)及[缺装机资料 trace](glm-missing.json)。该结果验证这一组固定资料的流程，扩大样本后再评估模型稳定性。

## 复现

在仓库根目录运行，Python 3.10 或以上，PDF 导出另需 Typst。E3 的同源摘录已随本页归档；如需重跑当年的摘录实验，使用[当时的 CLI](https://github.com/BrockPhlin/industry-report-harness/blob/c801b3377e5ac26ea090d78c96a41ffe83292d10/code/pv_brief.py)。任务目录应为尚不存在的新路径。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r code/requirements-midterm.txt
mkdir -p .build/pv-demo
.venv/bin/python code/pv_brief.py run .build/pv-demo/full --mode fixture
.venv/bin/python code/pv_brief.py inspect .build/pv-demo/full
.venv/bin/python code/pv_brief.py run .build/pv-demo/missing --mode fixture --omit-source NEA
.venv/bin/python code/pv_brief.py inspect .build/pv-demo/missing --json
.venv/bin/python code/pv_brief.py evidence pv-new-capacity
```

如果生成中途中断，用相同的任务目录、模式和资料参数追加 `--resume`。每个完整章节写入同级隐藏检查点目录，重启时跳过已完成章。章节内尚未完成的请求可能重跑。运行记录用 `resume_retry` 标记重跑次数。自动测试模拟首章写作失败，核验同一输入可恢复，改换资料会被拒绝。更换资料、模板或模型路由后须使用新任务目录。恢复完成后可用 `inspect --json` 查看 `resumed_sections`。

先核对任务目录下的草稿及来源。可编辑审阅文字，使用可选参数 `--markdown 文件` 指定修订稿。确认后执行下方命令，生成核对 Markdown、PDF 与哈希收据。对有缺项的草稿，核对后的导出件会继续标明待核实。

```sh
.venv/bin/python code/pv_brief.py approve .build/pv-demo/full --confirm
(
  cd code
  ../.venv/bin/python -m unittest discover -s tests -v
  ../.venv/bin/python -m unittest discover -s tests_midterm -v
)
```

真实模型运行使用 `--mode live`。从 `code/.env.example` 配置完整 Chat Completions 地址、模型名和私有凭据。需要验证模型是否支持函数调用及 JSON 草稿输出。配置为空时程序报错，并且不会创建任务文件。

适配测试覆盖工具参数为 JSON 字符串、直接为对象两种响应形式，回传时把原工具结果和流程主动补查的证据分开。另用 CLI 经本机 HTTP 模拟服务重跑两种输入，完整资料有 0 项待核实，缺装机资料有 1 项待核实。具体参数以部署服务为准。 [Z.AI Chat Completion 接口](https://docs.z.ai/api-reference/llm/chat-completion) · [智谱工具调用指南](https://docs.bigmodel.cn/cn/guide/capabilities/function-calling)

框架对照可独立复现，使用 Node.js 22.19+ 和本机回环端口：

```sh
npm install --prefix .build/dsh-probe --ignore-scripts @deepseek-ai/dsh@0.2.2-rc.5
npm install --prefix .build/pi-probe --ignore-scripts @earendil-works/pi-coding-agent@1.6.0
.venv/bin/python tools/midterm/dsh_probe.py .build/dsh-probe/node_modules/.bin/dsh
.venv/bin/python tools/midterm/pi_probe.py .build/pi-probe/node_modules/.bin/pi
```

常规简报入口使用 Python LangGraph。两个 Node.js 试验使用各自的临时目录、合成凭据与本机模拟端点，均调用同一个资料检索实现。

## 中期集成分支复验（2026-11-29）

将四份成员供稿合入展示分支后，通过工作台的研究接口向 GLM-5.3-Flash 提交固定资料简报题。完成的两章草稿含 588 GW、组件价格同比下降 29.7% 和新增装机 2.78 亿千瓦，分别关联 MIIT、NEA。测试程序显式确认后取回 PDF，验证了从模型调用到导出的路径。此处的自动确认只检查软件流程，指标的人工核对依据见[来源表](中期来源表.md)。

同日复跑 DeepSeek Harness 0.2.2-rc.5 和 Pi 1.6.0 的只读工具实验。两边各出现两次模型请求，第二次均带回含 2.78 亿千瓦的 NEA 工具结果；模型端是本机模拟服务。

在不配置模型的新库里，桌面和手机尺寸的 Chrome 均完成了生成示例、打开 [NEA] 来源卡、确认、下载 PDF 和刷新后查看确认状态。首页可直接打开上表 E7 的两份归档 PDF。回归测试通过 14 项基线检查、126 项中期检查；12 句定向核查的结果见[核查与修订](../../../docs/报告核查与修订.md)。

同一天另走了一次「直接写报告」的自定义题目。目标 800 字，限定 2024 年中国制造统计，指定「国内组件产量」「组件价格及统计口径」两章。取数记录显示工信部一份原始发布联网入库，从中保存了 10 条证据；生成的正文按工作台口径为 859 字。[此次生成的 Markdown 原稿](工作台联网研究_2024年制造与价格.md)保留当时的用词和附表。正文答到了组件产量和价格，但自动选的附表讲多晶硅产量，偏离题目；修正后，用同一份运行记录和正文引用重算，附表改为组件产量 588 GW [E4]。

修复后，用相同问题再做一次真实模型研究，生成 2 章、正文 749 字，附表为组件产量 588 GW，指向 E4；程序记录本次联网核对时源文件内容未变。两次运行都以 800 字为目标。正文长度由模型生成，附表和来源由程序整理。

## v1.0 展示材料复核

Gemini 4 Carbon 先看了汇报顺序，建议及早交代六人的交接方式，并用一个真实的联网题说明工作台能做什么。第 2 页现在先交代找资料、按章写、核对这三步；第 3 页把联网题与固定资料的现场演示放在一起讲。模型工具回传、去掉装机来源和逐句核查仍按各自输入与观察结果分别说明。

Claude Opus 5.5 核对了桌面首页、来源卡和手机草稿的截图。按反馈放大了「来源 [NEA]」等按钮，明确标出真实 GLM 样张，并调整了手机顶栏。第二轮看图确认三处都已改善。截图评审用于改善课堂可读性；上述软件运行结果来自本机实测。

Carbon 第二轮审阅了修改后的讲稿、报告和 README 文字。技术页明确说清本机模拟服务验证的是工具回传，另两份对照样张使用真实 GLM；报告也将模型附加文字的处理写成读者可核对的具体行为。

## v1.1 架构图如何核对

两张框架图使用同一个查询 `pv-new-capacity`。这次用 E4、E5 对应的发布版本重新运行，两个结果 JSON 分别与归档回执逐字段一致。两次都发出两条本机模拟模型请求。E4 第二条请求带有原调用编号及国家能源局证据；E5 的执行结束事件表明工具已返回，还可从第二条请求核对究竟返回了哪条记录。这些观察来自实际运行框架。比较两种接法时，产业指标的来源始终是同一份国家能源局资料。

[DeepSeek Harness 对应版本的 MCP 工具桥](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.5/packages/mcp/mcp-client/src/tools.ts#L126-L177) · [Pi 对应版本的扩展接口](https://github.com/earendil-works/pi/blob/v1.6.0/packages/coding-agent/docs/extensions.md) · [Pi 的工具结果进入会话循环](https://github.com/earendil-works/pi/blob/v1.6.0/packages/agent/src/agent-loop.ts#L268-L308)

本组固定简报与联网研究分别按[章内状态图](../../../code/report_app/pv_agent.py)和[长报告的阶段编排](../../../code/report_app/long_report.py)运行。对架构图的两轮 Carbon 文字审阅集中在两个问题：讲者能否指明返回值怎样进入下一轮，以及缺资料时由哪一段程序保留“待核实”。图中箭头最终按代码、E4/E5 回执和 E7 成稿核对。
