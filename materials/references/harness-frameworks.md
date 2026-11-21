# Harness框架参考记录

查阅日期：2026-10-26。以下为官方资料核对及本组设计取舍，未安装、未跑通或验证这些框架，不代表已经选型。

| 参考项目 | 可核对的官方说明 | 本组借鉴与待验证项 |
| --- | --- | --- |
| DeepSeek Harness（dsh） | 基于Cordis的插件化开源Harness，使用Node.js启动；官方介绍提供执行轨迹视图 | 参考工具扩展与运行记录。先验证如何与Python后端衔接及适配GLM API；不能据此声称已经接入。README标注开发者预览与兼容性变更 |
| LangGraph | 状态图的检查点持久化、人工介入与故障恢复；文档区分内存和持久化检查点 | 对照章节状态和重启恢复；内存状态不作为重启恢复证据 |
| Deep Agents | 基于LangGraph的Harness，提供文件系统、上下文管理与自定义工具等能力 | 参考资料及工具组织；不自动扩展多智能体范围，先与简单流程对照 |

官方来源：

- [R6 DeepSeek Harness仓库README](https://github.com/deepseek-ai/deepseek-harness)：项目介绍、运行说明、开发者预览。
- [R6 DeepSeek官方产品介绍](https://deepseek.com/harness/)：插件扩展及执行轨迹展示。
- [R3 LangGraph持久化文档](https://docs.langchain.com/oss/python/langgraph/persistence)：检查点、存储和重启注意事项。
- [R7 Deep Agents仓库README](https://github.com/langchain-ai/deepagents)：能力列表及与LangGraph的关系。

报告正文第5页列候选参考，第7页列最小验证条件：模型与工具、参考检索、保存接续、内容导出。实际选型需要兼容、维护成本和结果记录，不用星标数或框架宣传证明业务效果。
