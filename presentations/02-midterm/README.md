# 第11组中期材料

项目为产业智能报告生成系统。中期范围是2024年中国光伏产业简报。源码和材料按规划、修改代码、验证成果、总结与后续目标组织。

- [执行计划与拟议分工](../../team/中期执行计划.md)
- [系统设计报告 PDF](report/第11组_系统设计报告_v0.1.pdf) · [Typst 源文件](report/design.typ)
- [中期 PPTX](ppt/第11组_中期展示_v0.1.pptx) · [展示 PDF](ppt/第11组_中期展示_v0.1.pdf) · [逐页讲稿](ppt/讲稿.md) · [演示源码](ppt/slides.json)
- [运行和验证说明](evidence/README.md)

v0.1 为 2026-11-20 的中期工作稿。展示人暂拟郭润航，待小组确认。

设计报告从仓库根目录运行 `typst compile --font-path assets/fonts presentations/02-midterm/report/design.typ presentations/02-midterm/report/第11组_系统设计报告_v0.1.pdf` 构建。

展示使用 `tools/midterm/build_deck.mjs`。设置 `PRESENTATION_SKILL_DIR` 为已安装的 Presentations 技能目录，使用带 Artifact Tool 的运行时执行脚本。PPTX 备注与讲稿来自同一份 slides.json。展示 PDF 按验证后的 PPTX 一页一图导出。
