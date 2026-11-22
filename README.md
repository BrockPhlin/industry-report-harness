# 产业智能报告生成系统（第11组）

用公开资料生成能查回原文的产业简报，目前以2024年中国光伏为主。系统按章查指标，缺资料就标为“待核实”。研究员核对 Markdown 草稿后，再确认导出 PDF。

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

安装上面的 Python 依赖后，在仓库根目录运行 `.venv/bin/python code/run.py --port 8766`，浏览器打开 <http://127.0.0.1:8766/>。要用真实模型，把 `code/.env.example` 复制为 `code/.env`，在本机填写完整的 Chat Completions 地址、模型名和密钥，再启动服务。仓库忽略该配置文件。未配置时可选离线演练。

网页默认检索工信部、国家能源局两份已整理的 2024 年光伏统计。输入问题，选择「制造与价格」或「发电新增装机」，即可按章生成草稿。展开检索记录能看到每章用到的原文位置。真实模型支持就草稿继续追问，追问内容单独保存在对话中。核对草稿后点击「核对并导出 PDF」。历史研究保存在本机，刷新后可继续查看。原有资料录入及摘录功能保留在 `/baseline`。

## 组内材料

- [中期准备材料](presentations/02-midterm/README.md)有组员手册、设计报告框架、PPT 框架和完整讲稿。
- [实测样张与运行记录](presentations/03-final/evidence/README.md)记录了资料冲突、超时恢复和风电简报复用。
- 组员在各自分支修改，提交 PR 后互相检查，由组长确认合并。
