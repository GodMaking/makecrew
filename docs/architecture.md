# Architecture / 架构

## Responsibilities

四类职责构成最小闭环：

1. **Intent**：把用户意图变成目标和成功标准。
2. **Routing**：选择直达员工、项目主管或 CEO。
3. **Execution**：专业员工调用工具完成交付。
4. **Verification**：独立检查事实、质量、成本和发布条件。

任务台账（Task Ledger）为闭环提供可恢复状态；员工能力契约（Employee Profile）为路由提供可核验的 ID、Skill、工具和记忆范围。

CEO、主管和员工是可组合角色，不要求每个任务都经过全部角色。用任务规模决定流程深度。

## Codex Agent role mapping

MakeCrew maps directly onto the host's native Agent threads:

- `/root` is the current conversation and becomes the CEO layer only for explicit multi-task batches, cross-project decisions, or global resource conflicts.
- A supervisor Agent is a project-scoped coordinator. It owns decomposition, dependencies, concurrency, employee selection, waiting, conflict resolution, and result synthesis.
- Each employee Agent is one bounded specialist thread. It receives a task packet with its Skill IDs, tools, project context delta, file scope, budget, and acceptance gates.
- The QA Agent is an independent verification thread. It consumes employee deltas rather than full histories and reports evidence and unresolved risks back to the supervisor.

The host adapter creates or reuses the actual Codex threads. MakeCrew records the parent supervisor ID, employee Agent ID, thread identity, and structured result contract so the mapping remains inspectable across hosts. Independent write scopes should map to separate Worktrees; overlapping write scopes remain serial.

## Adaptive lifecycle

There is no mandatory full lifecycle. The router selects the smallest graph
that still protects quality:

```text
direct:    execute -> verify -> deliver
clarify:   intake -> route again
discovery: discovery -> execute -> verify -> deliver
guarded:   intake -> human_gate -> execute -> verify -> deliver
team:      execute:* (parallel) -> verify -> deliver
learning:  deliver -> learn  # only when a feedback/failure signal exists
```

失败进入 `rework`，必须附根因和改变后的实验；相同输入不得盲目重复。阻塞任务进入台账并可恢复，不通过复制完整历史来续接。

## Explicit workflow graph

`ai_company_os.workflow.build_workflow()` turns the selected route into a portable DAG. A full graph may look like:

```text
intake -> discovery -> human_gate -> execute:* -> verify -> deliver -> learn
                                  \-> execute:* -/
```

Optional nodes are controlled by `include_intake`, `include_discovery`,
`requires_confirmation`, and `include_learning`. Execute nodes share the latest
dependency and are grouped for parallel dispatch when independent. Each node declares an owner,
dependencies, and a minimum output contract. `ready_nodes()` calculates the
next runnable nodes from a compact completed-node set, so a host can resume at
the last checkpoint instead of replaying earlier model calls. A host may map
the graph to LangGraph, CrewAI Flows, AutoGen, or a custom queue; the MakeCrew
core remains dependency-free.

The `human_gate` is explicit and visible. It is used for the confirmation stage
and can be extended by an adapter for public publishing, payments, deletion,
or other irreversible actions. The graph describes the gate; the host records
the user's decision and performs the actual side effect.
