# 公开项目借鉴记录

本项目参考了公开仓库的产品形态和文档，不复制其代码或品牌。记录这份对比是为了让后续取舍可追踪。

> 调研更新：2026-08-30。以下结论来自各项目公开 README/文档；项目版本、托管服务和模型支持会变化，使用前应重新核对官方文档。新增的详细基准见 [`open-source-benchmark.md`](open-source-benchmark.md)。

| 公开项目 | 观察到的机制 | 本项目采用的部分 | 当前取舍 |
|---|---|---|---|
| [ClawCompany](https://github.com/Claw-Company/clawcompany) | 角色模板、分层记忆、工具目录、按任务选模型 | 员工能力契约、工具列表、项目记忆范围 | 先保持无第三方依赖，再接入模型适配器 |
| [Bopo](https://github.com/bopodev/bopo) | 项目/问题单、审批、预算、心跳、运行记录 | 任务状态台账、严格状态流转、预算与用量快照 | 先用 JSON/内存接口，后续再接数据库和心跳服务 |
| [auto-co](https://github.com/NikitaDmitrieff/auto-co-meta) | 共享共识文件、周期运行、重启后接续 | 差量交接、可恢复任务、接力式状态 | 不默认后台自动循环，避免无意消耗模型额度 |
| [Sandora](https://github.com/kyoo-147/Sandora) | 员工权限、工具范围、审批门禁、审计 | 能力契约、发布类动作确认、验收门禁 | 保留轻量路由核心，逐步增加权限策略 |

## 本轮检索到的相近项目

| 项目 | 公开能力信号 | 对 MakeCrew 的借鉴 | 不直接照搬的原因 |
|---|---|---|---|
| [LangGraph](https://github.com/langchain-ai/langgraph) | 低层状态图、持久执行、故障后从检查点恢复、人审中断、短期/长期记忆 | 把流程从一串文字升级为可序列化 DAG；在执行前暴露中断点和依赖 | MakeCrew 要保持模型无关、零第三方依赖，不绑定 LangChain 运行时 |
| [CrewAI](https://github.com/crewAIInc/crewAI) | 将自主协作的 Crews 与事件驱动的 Flows 分开；结构化输出、护栏、追踪 | 单任务走短路径，多任务走显式 Flow；交付物使用结构化契约；保留用量和事件观测接口 | 不把每个任务都包装成 Crew，避免管理轮次和 Token 成本膨胀 |
| [Microsoft AutoGen](https://github.com/microsoft/autogen) | Core 层消息传递与事件驱动运行时，AgentChat 提供群聊/团队模式，支持 AgentTool 和 MCP | 为宿主适配器预留消息、工具和结果回写边界；员工之间传结构化差量消息 | MakeCrew 的核心先保持同步、可测试，不强制引入分布式运行时 |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | 以软件公司角色和 SOP 组织需求、产品、架构、工程产物 | 将“岗位”落实为输入/输出契约和阶段性产物，而不是只写角色人设 | MakeCrew 覆盖研究、内容、设计等通用任务，不限定软件开发链路 |
| [ChatDev 2.0 / DevAll](https://github.com/OpenBMB/ChatDev) | 无代码工作流画布、可配置 Agent/Workflow、实时日志、人审反馈、回放与经验改进 | 增加可视化工作流数据、回放入口和人审节点；自进化保留证据和版本 | 不复制其前端、运行时或提示词；本项目先交付轻量 Python 内核 |
| [Letta](https://github.com/letta-ai/letta) | 有状态 Agent、跨会话记忆、桌面/服务端/消息渠道 | 继续区分公司、项目、任务三层记忆；员工线程按项目复用 | 不把聊天历史全部塞进上下文，避免记忆膨胀和隐私扩散 |
| [OpenHands Agent Canvas](https://github.com/OpenHands/OpenHands) | 自托管控制中心，多 Agent 后端，GitHub/Slack/Notion 等自动化和 Webhook | 将 Codex/Claude/自建运行时视为可替换 host adapter；为事件触发和后台任务留接口 | 不默认开启后台自动化；发布、外部写入和高成本动作仍需用户确认 |
| [AgentScope](https://github.com/agentscope-ai/agentscope) | Pipeline、事件流、上下文压缩、细粒度权限、人审、沙箱、持久化与团队协作 | 把工具权限、上下文压缩、暂停/恢复列为适配器能力，而非员工提示词口号 | 这些是宿主运行时能力，MakeCrew 只定义可移植的契约 |
| [CAMEL](https://github.com/camel-ai/camel) | 有状态记忆、工具集成、规模化 Agent、数据生成和评测 | 把评测、证据和成本作为长期指标，支持未来批量回放 | 规模化模拟不是个人工作台的默认需求，不预置百万 Agent |

## 形成的架构决定

1. **双路径而不是固定官僚层级**：单一明确任务在当前对话内澄清、发现、确认、执行和验收；只有多任务、跨项目或存在依赖时才启用 CEO/主管批次。
2. **显式 DAG 而不是“员工互相聊天”**：每个节点有负责人、依赖、输出契约和检查点；独立员工节点可以并行，验收节点必须等待所有分支。
3. **人审是可见的中断点**：公开发布、付款、删除和其他高成本动作先停在 `human_gate`，确认记录为状态，而不是靠提示词暗示。
4. **记忆分层且差量传递**：公司规则、项目上下文和任务记录分开保存；跨员工只传结论、证据、风险和下一步。
5. **自进化必须可回放**：失败反馈先聚合成提案，再用代表性任务比较基线/候选评分；没有提升就保留原方案。
6. **宿主能力通过适配器接入**：模型、浏览器、代码沙箱、消息渠道、追踪系统都由平台适配器提供，MakeCrew 不假装已经执行。

## 当前实现对应关系

- `ai_company_os/workflow.py` 输出可序列化的节点图、并行组、检查点和人审中断点。
- `plan_request()` 把该图放入单任务执行简报；`BatchScheduler` 继续负责多任务依赖、并发、预算和员工线程复用。
- `LearningEngine` 保持提案/回放/人工采用流程，不会因为新增工作流图而静默改写 Skill。
- 真实执行仍由 `CrewOrchestrator` 的宿主 dispatcher 或批次 `thread_adapter` 完成。

## 明确不照搬的部分

- 不复制仓库源码、提示词原文、视觉资产或产品品牌。
- 不把“有多个角色”当作真实协作；每个派单都必须有交付物和验收证据。
- 不默认启动无限循环或后台任务；自动化必须有预算、暂停和人工确认入口。
- 不把完整对话广播给所有员工；只传项目上下文和差量交接。

## 本次落地

- `EmployeeProfile`：固定员工 ID、技能、工具、状态和记忆范围。
- `TaskLedger`：支持 `pending/in_progress/blocked/review/done/cancelled`，记录事件、用量和预算。
- JSON 持久化：传入路径后，重启 `TaskLedger` 可以恢复任务状态。
- Web 演示：展示员工能力、恢复策略和差量交接模式。
- Workflow 图：展示节点依赖、并行分支、检查点和人审中断点。
