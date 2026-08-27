# Delta Handoff / 差量交接

```yaml
from: ""
to: ""
task_id: ""
as_of: ""
status: done | blocked | needs_decision
goal: ""
completed:
  - ""
evidence:
  - ""
changed_files_or_outputs: []
decisions_needed: []
risks_or_limits: []
recommended_next_action: ""
context_delta: []
```

只传自上次同步后新增或变化的内容。接收方需要完整背景时，读取项目上下文包，而不是要求发送者复制整段历史。
