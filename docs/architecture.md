# Architecture / 架构

## Responsibilities

四类职责构成最小闭环：

1. **Intent**：把用户意图变成目标和成功标准。
2. **Routing**：选择直达员工、项目主管或 CEO。
3. **Execution**：专业员工调用工具完成交付。
4. **Verification**：独立检查事实、质量、成本和发布条件。

任务台账（Task Ledger）为闭环提供可恢复状态；员工能力契约（Employee Profile）为路由提供可核验的 ID、Skill、工具和记忆范围。

CEO、主管和员工是可组合角色，不要求每个任务都经过全部角色。用任务规模决定流程深度。

## Lifecycle

`intake -> route -> execute -> review -> deliver -> log`

失败进入 `rework`，必须附根因和改变后的实验；相同输入不得盲目重复。阻塞任务进入台账并可恢复，不通过复制完整历史来续接。
