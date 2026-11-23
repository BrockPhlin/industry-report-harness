# 产业智能报告生成系统（第11组）

输入一个光伏研究问题，系统按地区和年份查公开统计，保存本次用过的数据，并逐章生成可以核对出处的 Markdown 报告。网页支持先讨论范围，再确认写作，也可以直接下指令。CLI 保留固定样例，供组内对照和离线验证。

## 在本地跑一次

以下以 Python 3.12 为例。导出 PDF 需要安装 Typst，离线示例无需配置 API 密钥。请在仓库根目录执行。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r code/requirements-midterm.txt
mkdir -p .build
demo=$(mktemp -d .build/pv-demo-XXXXXX)
.venv/bin/python code/pv_brief.py run "$demo/full" --mode fixture
.venv/bin/python code/pv_brief.py inspect "$demo/full"
```

核对 `$demo/full/draft.md` 后，运行以下命令确认并导出。PDF 保存在 `$demo/full/reviewed/brief.pdf`。

```sh
.venv/bin/python code/pv_brief.py approve "$demo/full" --confirm
```

想换成真实模型或复跑缺资料的情况，可以照着[验证记录里的命令](presentations/02-midterm/evidence/README.md)操作。

## 在网页里使用

装好 Python 依赖后即可打开网页并选择「离线样例」。如需联网研究，将 `code/.env.example` 复制为 `code/.env`，在本机填写 Chat Completions 地址、模型名和密钥。

```sh
.venv/bin/python code/run.py --port 8765
```

打开 <http://127.0.0.1:8765/>。选择「先聊一聊」可补充读者、年份、地区和想回答的问题，点「按这个范围写」后开始取数。选择「直接写报告」会立即规划、取数并写作。「范围与篇幅」可设 800 至 10000 字的正文目标，也可在指令中写明字数。表格、资料来源和目录另计。

在「范围与篇幅」还可以按行填写章名，例如先写全国新增装机，再比较浙江和江苏的分布式并网，最后列出园区规划要补查的数据。系统按给定顺序写作。某章生成中断时，可以从上次写完的章节继续。

在「范围与篇幅」也可限定资料来源，例如只使用国家能源局分省并网原表。「资料库」可按地区、年份、指标和发布机构筛选，并导出带原始出处及指纹的 CSV。

国内资料包括国家能源局分省并网年表、上半年表、前三季度表和利用率原表、国家统计局规上工业太阳能发电和光伏电池产量月表、制造统计和正式政策文件。国际资料包括 IEA PVPS 全球趋势和中国调查、IRENASTAT 纯光伏装机、IRENA 发电成本、OWID 的发电与成本数据、联合国 Comtrade 的年度商品贸易额，以及 Eurostat 的欧洲自中国进口月表。全年与前三季度、单月与年内累计、进口欧元与出口美元各自保留。遇到接口限流或原文无法访问，系统会列出资料缺口或说明使用的历史快照。

读报告时，点正文中的证据编号可核对当时取到的原文或数值。核对前可以润色措辞、下载 Markdown，确认后导出 PDF。参考报告只用于安排章节、表格和来源说明。

联网研究报告生成后，展开「核查正文与资料修订」，可以看哪些句子的数字与引用有出入，以及本机资料库更新后哪些原句需要重看。把同一版正文和证据记录一起下载，还能交给组员离线核对。[操作与实测结果](docs/报告核查与修订.md)

## 组内材料

- [夜间迭代记录](docs/光伏工作台迭代记录.md)记录各轮取数、改动和验证结果。
- [代码接手指南](docs/code-guide.md)说明网页如何取数、逐章写作和恢复中断的任务。
- [中期准备材料](presentations/02-midterm/README.md)有组员手册、设计报告框架、PPT 框架和完整讲稿。
- [实测样张与运行记录](presentations/03-final/evidence/README.md)记录了资料冲突、超时恢复和风电简报复用。
- 组员在各自分支修改，提交 PR 后互相检查，由组长确认合并。
