# Changelog

## Unreleased

### Added
- `task-intake` Skill：单任务在当前对话内完成需求澄清、Skill/工具规划、确认和执行。
- 单任务方法/Skill 发现阶段，以及验收后的自进化记录、提案和回放契约。
- `plan_batch()`：显式多任务请求继续使用 CEO 批量拆分和并发调度。
- 单任务最多三项关键澄清问题、执行简报和不可逆操作确认门禁。
- `BatchScheduler`：依赖图、动态并发上限、批次/任务预算、员工线程复用、暂停恢复、取消和失败记录。
- 可序列化工作流图：节点依赖、并行组、输出契约、持久检查点和人审中断点；单任务简报会直接携带该图。

### Changed
- MakeCrew 默认推荐单任务入口，CEO 调度保留给多任务并发和跨项目决策。
- 单任务入口从固定流水线改为自适应分流：常规任务直达执行；澄清、方法发现、确认、动态专家组和学习节点按触发条件加入。
- 澄清从“总共最多三问”升级为 0-N：每轮 1-3 个、稳定问题 ID、跨轮去重、领域缺口注入，以及用户授权默认值后的提前结束。
- GitHub 中英文首页集中展示需求澄清、动态调度、记忆、Token 成本、验收、恢复、预算和自进化等已实现优势。
- Skill/方法发现升级为本地优先：每个清晰任务先匹配已安装 Skill 和本地方法，缺口再搜索外部候选并等待用户选择；新增 `resolve_skills()` 和 Skill 搜索适配器契约。

## 0.2.0 - 2026-08-28

- Added role prompts for CEO, project lead, and specialist workers.
- Added task, context, and delta-handoff templates.
- Added routing, memory, architecture, and cost-control guidance.
- Added website, content-growth, and knowledge-base examples.
- Added a five-minute setup guide, copy-ready prompt pack, platform adapters, and FAQ.
- Added an employee registry, first-task walkthrough, contribution guide, and security notes.
- Added a dependency-free Python MVP with rule-based routing, CLI output, local web demo, and tests.
- Added local HTTP integration coverage and documented the MVP execution boundary and extension path.
