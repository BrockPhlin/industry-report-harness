# 终期验证记录

2026-11-21，在中期光伏简报和按章恢复基础上验证三项改动。中期报告与展示仍对应当时的实现和测试记录。 [中期证据](../../02-midterm/evidence/README.md)

本页编号在系统设计报告中统一引用为“补充 E9–E12”。“补充 E9”是合成冲突试验，与中期目录新增的“中期 E9”独立复跑分别引用。

| 编号 | 输入和预期 | 实际结果与证据 |
| --- | --- | --- |
| E9 | 公开光伏资料加一条合成的装机记录。两条数值分开显示。 | 把装机标为待核实，保留两份资料和原文位置。篡改候选值后无法确认导出。未改动的 PDF 保留待核实状态。 [输入](../../../code/tests_midterm/fixtures/pv-conflict.json) · [运行记录](pv-conflict-trace.json) · [PDF 样张](光伏简报_冲突演示.pdf) |
| E10 | 本机 Chat Completions 测试服务发出 HTTP 200 响应头后，延迟返回第二章写作的正文。第一章含另一组人工构造的冲突。 | 首轮发出四个请求，第二章写作读超时。第一章只把可用的价格指标交给模型。恢复轮只发出第二章的两个请求，保留第一章冲突记录并导出 PDF。 [复现测试](../../../code/tests_midterm/test_final_options.py) |
| E11 | 对接真实 GLM-5.3-Flash，人为把客户端网络等待设为 0.1 秒。 | 第一次在第一章检索阶段超时，CLI 提示已保存 0 章。恢复默认等待时长后继续，导出 PDF。两次命令耗时分别为 0.488 秒和 23.429 秒，是单次观测。 [运行记录](glm-timeout.json) |
| E12 | 同一 CLI 改用风电模板和国家能源局风电资料，调用真实 GLM。 | 复用检索、生成、核对和导出流程。两章包含 3 个指标，每项都有出处。PDF 中的来源链接可点击。 [模板](../../../code/templates/wind-brief.json) · [资料](../../../code/examples/wind-2024.json) · [运行记录](wind-live-trace.json) · [PDF 样张](风电简报_GLM联调.pdf) |

E9 与 E10 的冲突值用于检验程序。对同一指标，系统按输入记录中的统计期、数值、单位原字段比较。任一字段表述不同就保留不同记录供人工判断，暂不做单位换算或自动裁决。E11 验证客户端超时后的恢复路径，未观测到服务商自然故障。E12 验证一组固定风电资料的复用。

共通过 18 项网页基线测试和 12 项简报测试。DeepSeek Harness 和 Pi 原有两个工具探针也各自复跑通过，均通过本机模拟模型完成两次请求与资料回传。

## 复现方式

在仓库根目录执行。按中期证据说明安装依赖及 Typst 后，用离线模式复现冲突和风电两个样张。

```sh
mkdir -p .build
sample=$(mktemp -d .build/final-demo-XXXXXX)
.venv/bin/python code/pv_brief.py run "$sample/conflict" --mode fixture --corpus code/tests_midterm/fixtures/pv-conflict.json
.venv/bin/python code/pv_brief.py approve "$sample/conflict" --confirm
.venv/bin/python code/pv_brief.py run "$sample/wind" --mode fixture --template code/templates/wind-brief.json --corpus code/examples/wind-2024.json
.venv/bin/python code/pv_brief.py approve "$sample/wind" --confirm
(cd code && ../.venv/bin/python -m unittest discover -s tests_midterm -v)
```

失败退出且有检查点时，保留任务目录及输入参数，以同一个模型地址和模型名运行原命令并追加 `--resume`。如原先指定了很短的 `--request-timeout`，恢复时可删除或调高该参数。尚未完成的章节可能重新发出模型请求。

风电数据取自国家能源局公开统计。 [2024 年可再生能源并网运行情况](https://www.nea.gov.cn/20250221/e10f363cabe3458aaf78ba4558970054/c.html)
