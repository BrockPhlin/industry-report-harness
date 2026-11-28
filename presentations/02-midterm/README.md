# 第11组中期汇报 · 光伏产业报告生成系统

**主讲人：程文博。** 展示从一个可以现场检验的问题开始：2024 年全国光伏发电新增装机写成 2.78 亿千瓦，这个数从哪里来？去掉国家能源局资料后，交给研究员的 PDF 里还会写这个数吗？用同一个指标，可以比较两套开源框架怎样交回证据，再看本组的程序怎样补查、写报告并交人核对。

| 要做的事 | 打开什么 |
| --- | --- |
| 上台展示 | [可编辑 PPTX](ppt/第11组_中期展示_v1.1.pptx) · [展示 PDF](ppt/第11组_中期展示_v1.1.pdf) · [逐页讲稿](ppt/讲稿.md) |
| 提交系统设计报告 | [报告 PDF](report/第11组_系统设计报告_v1.1.pdf) · [可编辑 TeX](report/第11组_系统设计报告_v1.1.tex) · [正文源稿](report/report.md) |
| 演示前排练 | [启动工作台](../../README.md) · [完整讲稿](briefing/中期汇报完整讲稿.md) · [展示框架](ppt/中期PPT框架.md) |
| 回答技术追问 | [技术供稿](briefing/许子萌_中期技术供稿.md) · [框架工具回传、模型运行与中断恢复记录](evidence/README.md) |
| 核对数据和缺项 | [三项指标及出处](evidence/中期来源表.md) · [真实 GLM 完整资料](evidence/光伏简报_GLM完整资料.pdf) · [真实 GLM 缺装机资料](evidence/光伏简报_GLM缺装机资料.pdf) · [独立离线同栏复跑](evidence/郭润航_样张说明.md) |

教室投影可以直接打开展示 PDF，文字与矢量图按提交版排好。要改框内文字或挪动箭头，用可编辑 PPTX；编辑电脑可从[项目字体目录](../../assets/fonts)安装开题模板所用字体。

## 三张技术图怎样读

| 展示页 | 图中要追的问题 | 可单独放大查看 |
| --- | --- | --- |
| 第 4 页 · DeepSeek Harness | 模型要求查装机时，谁执行检索？原始数据怎样回到下一轮请求？ | [MCP 工具调用图](ppt/media/deepseek-harness-mcp.svg) · [本机工具回执 E4](evidence/deepseek-harness.json) |
| 第 5 页 · Pi CLI | 同一个检索怎样注册成工具？从哪些事件能看出它已执行并返回？ | [扩展与事件图](ppt/media/pi-cli-events.svg) · [本机工具回执 E5](evidence/pi-cli.json) |
| 第 6 页 · 本组系统 | 固定简报和自定义联网研究分别从哪里取数？研究员何时核对并导出？ | [工作台运行架构图](ppt/media/report-runtime.svg) · [真实模型样张与运行记录](evidence/README.md) |

## 谁交了什么

程文博负责范围、集成、应用联调和主讲。田亦洁把需求和验收写入系统设计报告，李佳雨完成展示供稿，崔大元核对原始数字和出处，许子萌整理智能体的流程和工具接口，郭润航用两种输入独立复跑，提交同栏样张。报告和讲稿都可以追到各自交接的材料。

| 交接件 | 可查记录 |
| --- | --- |
| 系统设计报告 | [田亦洁的 PR #10](https://github.com/BrockPhlin/industry-report-harness/pull/10) |
| 展示稿及演示证据 | [李佳雨的 PR #11](https://github.com/BrockPhlin/industry-report-harness/pull/11) · [郭润航的复跑对照图](evidence/发电新增装机_同栏对照_郭润航fixture.png) |
| 指标来源表 | [崔大元的 PR #12](https://github.com/BrockPhlin/industry-report-harness/pull/12) |
| 框架与流程技术稿 | [许子萌的 PR #13](https://github.com/BrockPhlin/industry-report-harness/pull/13) |

[组员准备手册](briefing/第11组_中期组员准备手册.pdf)和[原执行计划](../../team/中期执行计划.md)保留了交接前的安排。中期 E9 是郭润航的独立复跑；后续冲突、超时和跨领域试验在[补充验证](../03-final/evidence/README.md)单独编号。
