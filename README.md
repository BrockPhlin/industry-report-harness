# 第11组产业智能报告项目协作目录

## 目录与内容

```text
code/                         可运行的Python基线、静态页面、实际测试
team/                         开题任务与已安排的学期职责
presentations/
  01-opening/report/          本次报告Markdown源码与PDF
  01-opening/ppt/             本次幻灯片JSON源码、可编辑PPTX、PDF
  01-opening/speech/          逐页演讲稿Markdown与可打印PDF
  02-midterm/report/          中期报告预留，仅.gitkeep
  02-midterm/ppt/             中期PPT预留，仅.gitkeep
  03-final/report/            终期报告预留，仅.gitkeep
  03-final/ppt/               终期PPT预留，仅.gitkeep
materials/course-slides/      老师课件定位与使用边界
materials/references/         选题、评分细则、课程指纹与公开来源
materials/课程内容映射.csv    课件页码、课程概念、项目证据与汇报位置
docs/                        架构解释、基线边界、后续扩展与上传说明
tools/                       报告与PPT生成工具
assets/                      本次模板字体与校名资源，保留来源说明
```

## 跑基线

需要Python 3.10或更高版本，应用运行和测试只用标准库，无需安装业务依赖。在本目录打开终端：

```bash
python3 code/run.py
```

浏览器打开 http://127.0.0.1:8000 。录入原文并保存，勾选资料，输入主题，选择“资料摘录演示”，生成草稿并下载Markdown。SQLite自动创建在忽略目录code/runtime，重启后记录保留。示例资料在code/examples/demo-source.json，标明为人工构造，不能当真实产业数据。

另有[公开统计人工整理样例](code/examples/public-sources.json)：光伏两份、新能源汽车一份，含发布机构、日期和原始链接。它是历史事实的简短转述，非网页全文；可将其中的`title`、`publisher`、`published_at`、`url`、`body`逐份录入页面。先用两份光伏资料试生成，核对588GW对应组件产量、2.78亿千瓦对应新增装机。来源、操作与检查边界见[T5代码交接记录](docs/T5代码交接与核验.md)。

可选模型模式：把code/.env.example复制为code/.env，填写完整MODEL_ENDPOINT、MODEL_NAME和MODEL_API_KEY，再启动。使用Chat Completions兼容格式，模型由团队自行选择。未配置时明确报错，不静默切换成摘录。只有选择模型模式才发送资料到所配置服务。真实模型未做联调验证。

```bash
cd code
python3 -m unittest discover -s tests -v
```

基线已经提供资料持久化、一次性生成、来源快照、历史记录和Markdown下载。复杂Harness、恢复重试、审批流程、图表、PDF/DOCX导出、权限与业务评测留作后续工作。基本功能测试不等于课程系统测试报告或产业效果证明。

## 改本次报告与PPT

当前开题材料为项目计划书v1.5与PPTX v1.4，入口见 [本次开题材料](presentations/01-opening/README.md)。报告作者编辑report/report.md，PPT作者可修改对应ppt/slides.json并重新生成，或直接编辑PPTX；本次职责以team/claims.csv为准。

运行 `python3 tools/build_pdfs.py` 生成报告和展示PDF，`python3 tools/build_speech.py`生成逐页演讲稿，需要tools/requirements.txt中的材料依赖。`node tools/build_slides.mjs`读取同一幻灯片源码生成PPTX；直接编辑PPTX无需该SDK。字体与跨环境构建说明见tools/README.md。

## 资料与证据

已阅读组长提供的P4、P5课件，按实际页码填写课程映射，加入三级WBS、责任矩阵、三点估算与关键路径。原课件保留在提供位置，仓库仅保存文件指纹与应用映射；公开例子和官方Harness来源见materials/references/research-notes.md。

当前展示共12页，配有逐页演讲稿；真实调研、模型验证及团队确认需按进展补充；任何测试、访谈、会议和真实模型结果都须由实际记录支持。初始化由AI辅助，接手代码的成员需读docs/code-guide.md、运行测试并记录理解、修改与核验。

协作方式见 [仓库协作说明](docs/上传说明.md)，接口与数据流见 [代码接手指南](docs/code-guide.md)。学号、私有课件、密钥和运行数据库按实际访问权限处理。

新稿生成并逐页检查通过后删除旧生成稿，仅保留当前PDF/PPTX及对应源码；历史版本通过Git查阅。

共同维护方式：成员在各自分支按任务修改，PR交叉检查后由组长确认合并，再同步最新版本；协作截图和具体步骤见开题展示第9页、计划书§5.1与docs/上传说明.md。
