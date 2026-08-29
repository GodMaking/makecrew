# Changelog

## Unreleased

### Added
- `task-intake` Skill：单任务在当前对话内完成需求澄清、Skill/工具规划、确认和执行。
- `plan_batch()`：显式多任务请求继续使用 CEO 批量拆分和并发调度。
- 单任务最多三项关键澄清问题、执行简报和不可逆操作确认门禁。
- `BatchScheduler`：依赖图、动态并发上限、批次/任务预算、员工线程复用、暂停恢复、取消和失败记录。

### Changed
- MakeCrew 默认推荐单任务入口，CEO 调度保留给多任务并发和跨项目决策。

## 0.2.0 - 2026-08-28

- Added role prompts for CEO, project lead, and specialist workers.
- Added task, context, and delta-handoff templates.
- Added routing, memory, architecture, and cost-control guidance.
- Added website, content-growth, and knowledge-base examples.
- Added a five-minute setup guide, copy-ready prompt pack, platform adapters, and FAQ.
- Added an employee registry, first-task walkthrough, contribution guide, and security notes.
- Added a dependency-free Python MVP with rule-based routing, CLI output, local web demo, and tests.
- Added local HTTP integration coverage and documented the MVP execution boundary and extension path.
