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

## 组内材料

- [中期准备材料](presentations/02-midterm/README.md)有组员手册、设计报告框架、PPT 框架和完整讲稿。
- [实测样张与运行记录](presentations/03-final/evidence/README.md)记录了资料冲突、超时恢复和风电简报复用。
- 组员在各自分支修改，提交 PR 后互相检查，由组长确认合并。
