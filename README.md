# 第11组产业智能报告项目协作目录

这是准备上传到团队仓库的独立内容目录。仅程文博已确认负责统筹，其余五项由成员各自认领。此目录没有嵌套.git，不包含父目录的提交历史；上传时以本目录内容作为远程仓库根目录即可，不要上传整个桌面文件夹。

## 先认领，再交付

- [本次六项任务及验收交接](team/本次任务与认领.md)
- [成员与任务认领表](team/claims.csv)
- [长期模块认领建议](team/长期分工.md)
- [老师课件与汇报内容映射表](materials/课程内容映射.csv)

除组长外，不预设谁写报告、做PPT、汇报、整理课程资料或接手基线代码。五项任务原则上各由一人认领，领取后填写姓名、日期、截止时间；协作和交叉检查可以另外记录。

## 目录与内容

```text
code/                         可运行的Python基线、静态页面、实际测试
team/                         本次任务认领与长期职责待认领表
presentations/
  01-opening/report/          本次报告Markdown源码与PDF模板
  01-opening/ppt/             本次幻灯片JSON源码、可编辑PPTX、PDF模板
  02-midterm/report/          中期报告预留，仅.gitkeep
  02-midterm/ppt/             中期PPT预留，仅.gitkeep
  03-final/report/            终期报告预留，仅.gitkeep
  03-final/ppt/               终期PPT预留，仅.gitkeep
materials/course-slides/      老师课件入口，当前为空
materials/references/         已有选题说明和课程评分细则
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

可选模型模式：把code/.env.example复制为code/.env，填写完整MODEL_ENDPOINT、MODEL_NAME和MODEL_API_KEY，再启动。使用Chat Completions兼容格式，模型由团队自行选择。未配置时明确报错，不静默切换成摘录。只有选择模型模式才发送资料到所配置服务。真实模型未做联调验证。

```bash
cd code
python3 -m unittest discover -s tests -v
```

基线已经提供资料持久化、一次性生成、来源快照、历史记录和Markdown下载。复杂Harness、恢复重试、审批流程、图表、PDF/DOCX导出、权限与业务评测留作后续工作。基本功能测试不等于课程系统测试报告或产业效果证明。

## 改本次报告与PPT

报告作者编辑presentations/01-opening/report/report.md，PPT作者可直接修改可编辑PPTX，或修改ppt/slides.json并重新生成。开题模板采用第11组信息，职责均按待认领处理，旧的实名分配未复制进来。

运行 `python3 tools/build_pdfs.py` 生成报告和展示PDF，需要tools/requirements.txt中的材料依赖。PPT源代码的生成入口为tools/build_slides.mjs，使用Codex的@oai/artifact-tool运行环境；直接编辑PPTX无需该SDK。详细说明见tools/README.md。

## 资料与证据

老师课件尚未提供到此目录。资料整理任务的负责人应先上传允许共享的课件，填写实际文件名、版本与页码，再把课堂概念映射到项目安排和汇报页，不能根据评分细则虚构老师上课原话。

报告和PPT是可填写模板，包含待补信息；任何测试、访谈、会议和真实模型结果都须由实际记录支持。初始化由AI辅助，接手代码的成员需读docs/code-guide.md、运行测试并记录理解、修改与核验。

上传前阅读 [仓库上传说明](docs/上传说明.md)。学号、私有课件、密钥和运行数据库按实际访问权限处理。此目录未自动创建远程仓库、发送邀请或上传任何材料。
