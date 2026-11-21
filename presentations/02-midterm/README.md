# 第11组中期材料

项目为产业智能报告生成系统。中期范围是2024年中国光伏产业简报。源码和材料按规划、修改代码、验证成果、总结与后续目标组织。

- [执行计划与拟议分工](../../team/中期执行计划.md)
- [系统设计报告 PDF](report/第11组_系统设计报告_v0.4.pdf) · [Markdown 源文件](report/report.md)
- [中期 PPTX](ppt/第11组_中期展示_v0.4.pptx) · [展示 PDF](ppt/第11组_中期展示_v0.4.pdf) · [逐页讲稿](ppt/讲稿.md) · [演示源码](ppt/slides.json)
- [运行和验证说明](evidence/README.md)

v0.4 共 7 页，先讲光伏例子，再讲流程、实测、分工和下一步。结果页注明了模拟框架测试与真实 GLM 的中断恢复测试。开题蓝白模板沿用。第 4 页嵌入两份真实 GLM 导出样张的同一栏，现场可直接对照；讲稿留 20 秒用于翻页和停顿。封面按当前拟定的郭润航预填。

从仓库根目录运行 `python3 tools/midterm/build_materials.py` 构建设计报告、展示 PDF 与讲稿。材料构建依赖在 `tools/requirements.txt`。

编辑版 PPTX 使用 `node tools/build_slides.mjs --midterm`。设置 `PRESENTATION_SKILL_DIR` 为已安装的 Presentations 技能目录，使用带 Artifact Tool 的运行时。PPTX、备注、展示 PDF 与讲稿共用 slides.json。
