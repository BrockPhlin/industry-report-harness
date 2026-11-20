# 第11组中期材料

项目为产业智能报告生成系统。中期范围是2024年中国光伏产业简报。源码和材料按规划、修改代码、验证成果、总结与后续目标组织。

- [执行计划与拟议分工](../../team/中期执行计划.md)
- [系统设计报告 PDF](report/第11组_系统设计报告_v0.2.pdf) · [Markdown 源文件](report/report.md)
- [中期 PPTX](ppt/第11组_中期展示_v0.2.pptx) · [展示 PDF](ppt/第11组_中期展示_v0.2.pdf) · [逐页讲稿](ppt/讲稿.md) · [演示源码](ppt/slides.json)
- [运行和验证说明](evidence/README.md)

v0.2 更新于 2026-11-21。PPT 和设计报告沿用开题模板，已纳入 GLM-5.3-Flash 的两组联调结果。展示人暂拟郭润航，待小组确认。

从仓库根目录运行 `python3 tools/midterm/build_materials.py` 构建设计报告、展示 PDF 与讲稿。材料构建依赖在 `tools/requirements.txt`。

编辑版 PPTX 使用 `node tools/build_slides.mjs --midterm`。设置 `PRESENTATION_SKILL_DIR` 为已安装的 Presentations 技能目录，使用带 Artifact Tool 的运行时。PPTX、备注、展示 PDF 与讲稿共用 slides.json。
