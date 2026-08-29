# Open-Source Benchmark / 开源方案借鉴

本页记录 MakeCrew 对公开项目和开放规范的定期对比。目标是吸收可验证的
机制，不复制代码、提示词、品牌或未经验证的宣传。链接和结论应在发布前重新核对。

## 结论先看

MakeCrew 选择做一层跨平台的任务入口和协调契约，而不是替代所有 Agent
运行时。核心路径保持本地、可序列化、低依赖；真实模型、工具、浏览器、沙箱、
安装器和追踪系统由宿主适配器接入。

## 对比表

| 来源 | 已观察机制 | MakeCrew 吸收 | 暂不照搬 |
|---|---|---|---|
| [Agent Skills specification](https://agentskills.io/specification) / [agentskills](https://github.com/agentskills/agentskills) | `SKILL.md`、名称/描述元数据、发现 -> 激活 -> 执行的渐进披露 | Skill ID、描述、来源和本地匹配；缺口才搜索；完整指令和资源按需加载 | 不绑定某一家模型或客户端 |
| [Anthropic Skills](https://github.com/anthropics/skills) | 可移植目录、示例 Skill、插件安装和资源分层 | 保持 Skill 自包含、版本化、可审计；安装与执行分离 | 不复制其专有文档处理实现 |
| [obra/superpowers](https://github.com/obra/superpowers) | 自动触发、需求澄清、计划、TDD、代码审查、完成前验证 | 把触发条件、验收和证据写入工作流；反馈后再进入学习 | 不把所有任务强制套进长开发流程 |
| [OpenSkills SDK](https://github.com/LingyiChen-AI/OpenSkills) | 三层披露、自动 Skill 调用、引用/脚本按需加载、沙箱 | 将“本地先匹配，外部候选等待用户选择”作为入口契约 | 沙箱由宿主执行器决定，不在零依赖内核伪造 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 持久执行、检查点、人审中断、短期/长期记忆、运行追踪 | 可序列化 DAG、任务台账、恢复、确认门禁、分层记忆 | 不强制引入 LangChain 运行时 |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | Agents as tools、handoffs、工具、护栏、人审、sessions、tracing | 宿主适配器保留工具、线程、交接、确认和观测接口 | 不绑定 OpenAI API 或模型 |
| [CrewAI](https://github.com/crewAIInc/crewAI) | Crews 与事件驱动 Flows 分离，结构化输出和追踪 | 单任务短路径、多任务批次、输出契约和用量记录 | 不为一个简单任务创建完整 Crew |
| [Microsoft AutoGen](https://github.com/microsoft/autogen) | 消息驱动运行时、AgentChat、AgentTool、MCP | 结构化差量交接和可替换消息适配器 | 不在核心引入分布式运行时 |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | 软件公司角色、SOP、阶段产物和协作 | 岗位能力契约、阶段产物、验收标准 | MakeCrew 不限定软件开发领域 |
| [sickn33/agentic-awesome-skills](https://github.com/sickn33/agentic-awesome-skills) | 大规模目录、发现、规划和本地控制面 | Skill 目录审计、候选来源、可解释选择和能力缺口 | 不把数千 Skill 默认加载进上下文 |
| [dsifry/metaswarm](https://github.com/dsifry/metaswarm) | 多 Agent、命令入口、TDD、质量门禁、任务追踪和自我改进 | 任务台账、预算、验收、回放和事件触发自进化 | 不预置固定 18 人团队或特定 CLI |

## 已落地机制

1. 每个清晰任务先匹配宿主报告的已安装 Skill 和本地方法。
2. 缺少关键 Skill 才调用 `skill_searcher(task, missing_skill_ids)`；候选带用途和来源，用户选择后才安装或启用。
3. 外部方法搜索用于本地无匹配、能力缺口或最新比较，不会静默改变范围。
4. Skill 元数据和完整指令分离；任务只加载所需内容，资源由 Skill 自己声明并按需读取。
5. 单任务在当前对话内完成；明确多任务才进入 CEO 批次；并发、依赖、预算和恢复均可检查。
6. 输出有独立验收、证据、失败原因和回放评分；自进化提案不能绕过审阅直接修改 Skill。

## 后续优先级

| 优先级 | 方向 | 完成标准 |
|---|---|---|
| P0 | 宿主 Skill 目录适配器 | 能读取名称/描述/版本/来源，返回安装状态和路径，不加载无关正文 |
| P0 | 可解释匹配 | 每个匹配项返回 `skill_id`、触发依据、缺口、来源和预计成本 |
| P1 | 统一安装确认 | 候选可选择安装、仅本次使用、跳过；安装后自动刷新清单 |
| P1 | 运行轨迹 | 记录路由、Skill、工具、Token/调用量、验收和用户决策，可导出脱敏记录 |
| P1 | 评测集 | 用固定任务集比较路由准确率、重复提问率、返工率、成本和完成时间 |
| P2 | 多宿主适配器 | Codex、Claude、Gemini、自建运行时共享同一任务/Skill/交接契约 |

这些优先级比增加更多员工角色更重要：用户是否能一次理解、安装、匹配、
执行并验证，决定 MakeCrew 是否会成为新用户愿意长期保留的基础 Skill。
