# Task Ledger / 任务台账

任务台账是 AI Company OS 的可恢复执行层。它保存任务摘要、负责人、状态事件和工具用量，不保存完整聊天历史。

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
