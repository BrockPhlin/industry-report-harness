# 材料源码与构建

报告源在presentations/01-opening/report/report.md；幻灯片内容、坐标、讲述与用时在对应ppt/slides.json。当前版本见presentations/01-opening/README.md。工作目录仅放当前生成稿；新稿校验通过后删除旧PDF/PPTX，历史由Git保留。

## 数据与计算

- team/wbs.csv是三级WBS的21个叶子任务；semester-plan.csv是父工作包与分摊。两表逐包、逐人合计一致，共268计划人时。
- team/core-schedule.json保存6项活动、依赖、工期与PERT情景。`python3 tools/plan_math.py`先拓扑排序，前推最早时刻、后推最晚时刻，再计算总浮动；依赖循环、未知前置或非法工期直接失败。当前关键路径23工作日，缓冲3日；O/M/P为40/52/88人时，PERT期望56、标准差8。它是核心流程试排，未覆盖完整资源平衡。
- assets/opening/example-data.json保存公开例子的数值、单位和原始链接。图表使用小数比例0.135/-0.297并显示百分比，避免把13.5误当1350%。prototype-record.json记录截图模式、输入与源码版本，不证明真实模型效果。

## 生成与检查

`python3 tools/build_speech.py`读取slides.json的speech、cue、seconds字段，生成逐页演讲稿Markdown和4页打印PDF；正文同PPT备注，来源链接不混入朗读部分。每页最多安排3张幻灯片的讲稿，排版溢出会报错。

`python3 tools/build_pdfs.py`读取Markdown与slides.json，先生成四张技术图，再生成10页计划书和12页可选中文字的展示PDF，依赖requirements.txt。Markdown仅支持受控的标题、段落、表格、图片和HTTPS链接；篇幅或版面超限会停止。示例图、恢复流程与进度图复用幻灯片源码，避免另抄数值。

`node tools/build_slides.mjs`用@oai/artifact-tool生成可编辑PPTX。表格、柱状图及技术流程由原生对象组成，流程节点、连线和文字可编辑；图表内嵌当前公开数据快照。候选文件先检查几何、字体、原生对象及重新导入，成功后替换当前输出；私有逐页预览和收据位于.build/slides。

SDK属于材料构建依赖，业务运行不需要它。默认读取Codex托管环境；ARTIFACT_NODE_MODULES、ARTIFACT_TOOL_MODULE、PRESENTATION_SKILL_DIR、RUNTIME_PYTHON可指定路径。仓库附LXGW WenKai与Smiley Sans Oblique及许可。PPTX与展示PDF分别生成，发布前必须逐页检查两者；检查不能证明产业事实或原生PowerPoint渲染。

`python tools/build_deck.py`是团队早期python-pptx备选，仅支持旧版文字、表格、流程、图片，尚不支持本稿新增图表和矩形对象；不能用于覆盖当前输出。直接编辑PPTX后应同步slides.json或明确更换唯一内容源。

`python3 tools/check_package.py`检查当前版本文件、链接、分工、页数、WBS合计及排期。`python3 -m unittest discover -s tests -v`在code目录运行应用基线测试；模型响应为模拟值，不能替代真实模型与业务验证。

`python3 tools/measure_source_payload.py`用临时数据库中的构造资料比较列表JSON字节数，只依赖标准库，不证明运行速度或产业分析质量。

PDF沿用组长改好的无版本号文件名，版本与日期在文档内标明；PPTX以版本号区分，更新检查通过后删旧稿。报告中的技术图按slides.json的id定位，插入协作页不会导致取错进度图。

team/semester-timeline.json保存第7页的阶段起止与工作内容；课表节点来源为课程介绍PDF文件顺序第47页《课时安排》。阶段内日期为组内暂排，示意条不按实际天数比例绘制。当前包检查会核对阶段数据与幻灯片文字一致。

计划书首张为标题与可点击目录，9个目录链接指向第2—10页。受控图片标记可用{width=70%}等比例缩放，范围25%—100%；缩放图在页面中居中。成本表保留计划工时和实际费用记录方式，不填无依据现金上限。

`node tools/build_image_slides.mjs`把当前展示PDF逐页栅格化为2560×1440 PNG，再生成每页仅有一张图片的PPTX，备注来自slides.json。源PDF须先更新；页面数或宽高不符时终止。纯图片版和可编辑版用途不同，两者均作为当前交付保留。
