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

## Explicit workflow graph

`ai_company_os.workflow.build_workflow()` turns a route into a portable DAG:

```text
intake -> discovery -> human_gate -> execute:* -> verify -> deliver -> learn
                                  \-> execute:* -/
```

The execute nodes share one confirmation dependency and are grouped for
parallel dispatch when they are independent. Each node declares an owner,
dependencies, and a minimum output contract. `ready_nodes()` calculates the
next runnable nodes from a compact completed-node set, so a host can resume at
the last checkpoint instead of replaying earlier model calls. A host may map
the graph to LangGraph, CrewAI Flows, AutoGen, or a custom queue; the MakeCrew
core remains dependency-free.

The `human_gate` is explicit and visible. It is used for the confirmation stage
and can be extended by an adapter for public publishing, payments, deletion,
or other irreversible actions. The graph describes the gate; the host records
the user's decision and performs the actual side effect.
