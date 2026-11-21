# 中期验证记录

2026-11-20 与 2026-11-21 执行。数据是公开历史统计摘编。E1、E2 使用 LangGraph 和固定离线决策。DeepSeek Harness 和 Pi 使用本机模拟模型，验证工具连接和结果回传。E7 使用组长提供的智谱服务，完成两组真实模型联调。

| 编号 | 环境与输入 | 观察结果与产物 |
| --- | --- | --- |
| E1 | LangGraph 1.2.24，工信部与国家能源局两份资料 | 3项指标都可定位，制造章补查一次找回价格指标。见[完整简报](光伏简报_完整资料.pdf)及[完整 trace](trace-full.json)。 |
| E2 | 同一 LangGraph 流程，仅保留工信部资料 | 装机查找和补查均为空，草稿保留1个待核实项，导出后仍标明缺项。见[缺资料简报](光伏简报_缺装机资料.pdf)及[缺资料 trace](trace-missing.json)。 |
| E3 | 开题摘录模式和 E1 使用相同数据 | [基线摘录](同源摘录基线.md)列出原始条目。E1增加章节、补查、来源定位和显式确认。此对照验证工作流差别。 |
| E4 | DeepSeek Harness 0.2.2-rc.5，SDK 接只读 MCP，模拟 Messages 服务 | 第二次请求带回了装机证据。见[DeepSeek 收据](deepseek-harness.json)。 |
| E5 | Pi 1.6.0，JSON 模式接只读扩展，模拟 Chat Completions 服务 | 第二次请求带回了装机证据，CLI 写出工具与任务事件。见[Pi 收据](pi-cli.json)。 |
| E6 | Python 3.12，既有基线及中期自动测试 | 18项基线测试、7项中期测试通过，包括同源完整与缺失、接口模拟、伪造编号拒绝、审阅保护和真实 Typst 导出。 |
| E7 | GLM-5.3-Flash，完整资料与缺装机资料 | 完整资料3项指标均可回查。缺装机资料时初查和补查均为空，PDF 保留1项待核实。一条不合规的附加观察被省略并记入 trace。 |

E7 产物包括[完整资料 PDF](光伏简报_GLM完整资料.pdf)、[缺装机资料 PDF](光伏简报_GLM缺装机资料.pdf)、[完整资料 trace](glm-full.json)及[缺装机资料 trace](glm-missing.json)。该结果验证这一组固定资料的流程，扩大样本后再评估模型稳定性。

## 复现

在仓库根目录运行，Python 3.10 或以上，PDF 导出另需 Typst。固定依赖与开题基线分装。任务目录应为尚不存在的新路径。

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
