# Changelog

## Unreleased

### Added
- Codex 原生 Agent 适配器：将父 Agent 映射为主管、子 Agent 映射为员工，支持线程复用、最小任务包、结构化结果回写和主管汇总。
- `makecrew codex-audit`：在连接宿主回调前检查主管身份、缺失能力和并发建议。
- AgentFlow OS 品牌与 AI 可发现性入口：保留 MakeCrew、`makecrew` 命令、Skill ID 和 GitHub 地址作为兼容别名。
- `task-intake` Skill：单任务在当前对话内完成需求澄清、Skill/工具规划、确认和执行。
- 单任务方法/Skill 发现阶段，以及验收后的自进化记录、提案和回放契约。
- `plan_batch()`：显式多任务请求继续使用 CEO 批量拆分和并发调度。
- 单任务最多三项关键澄清问题、执行简报和不可逆操作确认门禁。
- `BatchScheduler`：依赖图、动态并发上限、批次/任务预算、员工线程复用、暂停恢复、取消和失败记录。
- 可序列化工作流图：节点依赖、并行组、输出契约、持久检查点和人审中断点；单任务简报会直接携带该图。
- `skill-audit`：在发布或更新前审计 Skill 元数据、命名、目录一致性和渐进披露布局。
- `review-and-critique`：在开发里程碑、合并前和发布前提供带文件证据的独立审查契约。
- `checkpoint-recovery`：提供紧凑检查点、幂等保存和有界失败重试，支持宿主在重启后继续任务。

### Changed
- 项目对外品牌由 MakeCrew 更新为 AgentFlow OS（智流工作系统），突出自适应需求入口、Skill 发现、Agent 路由和可验收执行。
- 新手安装教程升级为可复制的宿主 AI 安装提示词：先盘点平台能力、保护已有配置、按平台启用入口 Skill，并用四类小任务验证真实接入状态。
- README、英文 README、Skill 卡片、Python 包描述和 GitHub 定位统一为“本地优先 Skill 匹配的跨平台 AI 工作入口”，突出单任务短路径与多任务调度的边界。
- MakeCrew 默认推荐单任务入口，CEO 调度保留给多任务并发和跨项目决策。
- 单任务入口从固定流水线改为自适应分流：常规任务直达执行；澄清、方法发现、确认、动态专家组和学习节点按触发条件加入。
- 澄清从“总共最多三问”升级为 0-N：每轮 1-3 个、稳定问题 ID、跨轮去重、领域缺口注入，以及用户授权默认值后的提前结束。
- GitHub 中英文首页集中展示需求澄清、动态调度、记忆、Token 成本、验收、恢复、预算和自进化等已实现优势。
- Skill/方法发现升级为本地优先：每个清晰任务先匹配已安装 Skill 和本地方法，缺口再搜索外部候选并等待用户选择；新增 `resolve_skills()` 和 Skill 搜索适配器契约。
- Skill 解析结果增加渐进式披露策略：启动只读元数据，匹配后加载指令，引用和脚本按需加载。

## 0.2.0 - 2026-08-28

- Added role prompts for CEO, project lead, and specialist workers.
- Added task, context, and delta-handoff templates.
- Added routing, memory, architecture, and cost-control guidance.
- Added website, content-growth, and knowledge-base examples.
- Added a five-minute setup guide, copy-ready prompt pack, platform adapters, and FAQ.
- Added an employee registry, first-task walkthrough, contribution guide, and security notes.
- Added a dependency-free Python MVP with rule-based routing, CLI output, local web demo, and tests.
- Added local HTTP integration coverage and documented the MVP execution boundary and extension path.
