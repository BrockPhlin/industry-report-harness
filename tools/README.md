# 材料源码与构建

报告源：presentations/01-opening/report/report.md；PPT内容源：presentations/01-opening/ppt/slides.json。源码和模板已按本次六项待认领任务更新。

`python3 tools/build_pdfs.py`生成7页报告PDF与12页展示PDF，需要ReportLab等材料依赖，见requirements.txt。程序显式检查表格和页面是否溢出；改模板结构时同步修改分页检查。

`node tools/build_slides.mjs`生成原生可编辑文字和表格的PPTX，并在.build保存预览与验证收据。使用@oai/artifact-tool及@napi-rs/canvas，默认读取Codex托管运行环境；可用ARTIFACT_NODE_MODULES、ARTIFACT_TOOL_MODULE、PRESENTATION_SKILL_DIR、RUNTIME_PYTHON指定。该SDK不是应用运行依赖，不承诺公开npm可安装。团队可直接编辑PPTX，不依赖此生成器。

每次变更后人工检查页面。若直接编辑PPTX，应记录该稿为主，避免生成器覆盖手工修改。本目录所有源文件与资源都在内部，不依赖原桌面软需或父目录。字体来源见assets/README.md。
