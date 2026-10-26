# Task Ledger / 任务台账

任务台账是 MakeCrew 的可恢复执行层。它保存任务摘要、负责人、状态事件和工具用量，不保存完整聊天历史。

## 状态流转

```text
pending -> in_progress -> review -> done
                    \\-> blocked -> in_progress
任意未完成状态 -> cancelled
```

不允许跳过状态随意改写。例如，已完成任务不能重新标记为执行中；需要返工时应创建新任务或保留清晰的事件记录。

## 最小用法

```python
from ai_company_os import TaskLedger, TaskStatus

ledger = TaskLedger(".ai-company/tasks.json")  # 可选：启用重启后恢复
task = ledger.create(
    "开发网站",
    project="demo-site",
    assignee="ENG-001",
    budget={"tool_calls": 10, "rounds": 6},
)
ledger.transition(task.task_id, TaskStatus.IN_PROGRESS, note="开始实现")
ledger.record_usage(task.task_id, tool_calls=2, rounds=1)
ledger.transition(task.task_id, TaskStatus.BLOCKED, note="等待部署凭据")
ledger.resume(task.task_id)
print(ledger.snapshot(task.task_id))
```

## 设计原则

- **可恢复**：重启后读取快照即可继续，不要求重放整段对话。
- **可审计**：每次状态变化都有事件和备注。
- **可控成本**：任务记录工具调用和轮次，超过预算时由上层主管暂停。
- **轻量优先**：不传路径时是内存台账；传入 JSON 路径时自动保存并在重新创建 `TaskLedger` 后恢复。应用层也可将 `export()` 写入 SQLite 或自己的数据库。

## 批次运行证据链

`BatchScheduler` 为每个批次生成 `run_id`，并支持可选 JSONL 追踪文件。启用 `trace_path` 后，会逐条追加任务创建、启动、派发请求、宿主回执/异常、完成、失败与 QA 事件；不启用时，事件只保存在本次 scheduler 实例内存中。

```python
from ai_company_os import BatchScheduler

scheduler = BatchScheduler(trace_path=".makecrew/runs/current.jsonl")
scheduler.add("设计方案", task_id="T1", project="crm")
scheduler.add(
    "实现接口",
    task_id="T2",
    project="crm",
    parent_task_id="T1",
    depends_on=["T1"],
)
```

每条事件关联 `run_id`、`task_id`、`parent_task_id`、主管/员工 Agent、线程、尝试次数、模型（宿主回执有返回时）、产物引用和 QA 结果。`artifact_refs` 只取员工结果中显式提供的路径；不会把摘要、提示词或聊天记录复制进追踪文件。宿主创建线程或派发回调抛出异常时会记录异常，并将任务留在 `waiting_host`，由调用方决定何时重试。QA 通过 `record_qa(..., status="passed" | "rework_required" | "blocked", reason=..., evidence_refs=...)` 记录，驳回/阻塞必须附原因。QA 只接受已完成员工结果：`passed` 保持 `done`；`rework_required` 转入 `review`，后续 `dispatch_ready()` 可重派；`blocked` 转入 `blocked_qa`，等待主管显式调用 `resume()`。默认最多允许两轮 QA 返工；超过上限后也进入 `blocked_qa`，由主管重新检查任务范围、输入和负责人，避免无限返工。每次 QA 结果写入 `qa_history`，跨重启保留；返工任务再次完成后，最新 QA 状态重置为 `not_run`，等待复核。`overview()["awaiting_qa"]` 单独标出员工已完成、QA 尚未运行的任务，避免把员工完成与质量放行混为一谈。

CLI 可用 `makecrew batch-dispatch ... --trace-path .makecrew/runs/current.jsonl` 开启 JSONL 记录。模型、宿主 run ID 和线程数据只会在宿主回执提供时出现；字段留空表示这次执行没有回传该项，不代表系统补猜。

每个任务包还带稳定的 `idempotency_key`（`run_id:task_id`），同一派发的传输重试会复用它。宿主应据此去重外部副作用；这提供可识别的重复投递，不构成 exactly-once 承诺。`JsonCheckpointStore` 保存宿主提交的节点状态；宿主负责决定重试时机和副作用去重。批次状态默认驻留进程内，指定 `state_path` 后可由 `BatchScheduler` 持久化和恢复。

## 批次状态持久化与恢复

需要跨进程续作时，可给 `BatchScheduler` 指定 `state_path`。每次关键状态变化会通过临时文件替换原子写回；重新启动后用 `BatchScheduler.restore()` 载入，并重新绑定当前宿主的线程/派发回调：

```python
state_path = ".makecrew/runs/crm-batch.json"
scheduler = BatchScheduler(
    state_path=state_path,
    trace_path=".makecrew/runs/crm-batch.jsonl",
    agent_dispatcher=host.dispatch,
    thread_adapter=host.open_employee_thread,
)
# 首次运行时 add(...) 并调用 dispatch_ready()

# 进程重启后：
resumed = BatchScheduler.restore(
    state_path,
    agent_dispatcher=host.dispatch,
    thread_adapter=host.open_employee_thread,
)
resumed.dispatch_ready()
```

恢复时，保存为 `running` 的任务会转成 `waiting_host`，写入 `task_interrupted_on_restore` 事件；终态任务保持终态，不会再次派发。重发沿用原 `run_id` 和幂等键。若宿主在上次调用中已完成外部副作用但回执丢失，宿主应按幂等键查询或去重后再处理重发；`RetryPolicy` 的上限和重试时机仍由宿主控制。`max_qa_reworks` 单独控制 QA 驳回返工次数，不替代宿主的瞬时错误重试策略。

持久化文件包含任务描述、任务包、结构化员工结果、产物引用和 QA 记录，不含完整对话历史。它可能承载业务敏感内容，应放在本地私有目录并避免写入凭证；同一状态文件由一个调度器进程独占写入。新建 scheduler 遇到已有状态文件会报错并保留原文件，恢复请显式调用 `restore()`。未设置 `state_path` 时仍使用进程内状态。
