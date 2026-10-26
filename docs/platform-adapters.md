# Platform Adapters / 平台适配

## ChatGPT / Codex

- 将角色文件放入自定义指令、项目说明或独立对话的首条消息。
- 将项目上下文包作为项目文件或固定参考资料。
- 需要真实浏览器、代码仓库、设计或视频操作时，为对应员工启用平台已有工具，并在任务卡写明工具范围。

### Codex 原生 Agent 适配器

MakeCrew 不重新实现 Codex 的 Agent 生命周期。`CodexAdapter` 将父 Agent
作为主管、每个原生子 Agent 作为员工，并把最小任务包交给宿主回调：

```python
from ai_company_os import BatchScheduler, CodexAdapter

def spawn_subagent(prompt, metadata):
    # 用宿主提供的原生子 Agent 创建能力；返回 thread_id 和可选 agent_id
    return {"status": "accepted", "thread_id": "CODEX_THREAD_ID", "agent_id": metadata["agent_id"]}

def send_to_thread(thread_id, prompt):
    # 用宿主提供的线程发送能力；不要复制完整历史
    return {"status": "accepted", "run_id": "CODEX_RUN_ID"}

adapter = CodexAdapter(
    supervisor_id="PM-001",
    supervisor_thread_id="CODEX_SUPERVISOR_THREAD",
    spawn_subagent=spawn_subagent,
    send_to_thread=send_to_thread,
)
scheduler = BatchScheduler(
    supervisor_id="PM-001",
    thread_adapter=adapter.open_employee_thread,
    agent_dispatcher=adapter.dispatch,
    max_concurrency=3,
)
scheduler.add("修复登录页", task_id="T1", project="demo", file_scope=["src/login.tsx"])
dispatch = scheduler.dispatch_ready()[0]
# 宿主收到员工 JSON 后：
adapter.complete(scheduler, "T1", {"summary": "完成", "evidence": ["test.log"]})
summary = adapter.summarize(scheduler)
```

`spawn_subagent` 只在该员工没有已注册线程时调用；同一员工/项目/主管的后续
任务复用线程并通过 `send_to_thread` 发送差量。回调缺失时，适配器返回
`queued` 及缺失能力名称，不会把计划伪装成已执行。`audit()` 可在启动时检查
回调是否接通；建议先用 `max_concurrency=3`，再依据宿主限制调整。

### 独立 QA Agent 复核

需把 QA 接入任务完成流程时，宿主在员工结果写入后调用 `request_qa_review()`；QA Agent 使用新隔离线程，不复用执行员工的上下文：

```python
task = adapter.complete(scheduler, "T1", employee_result)
review = adapter.request_qa_review(scheduler, "T1")
# 宿主等待独立 QA Agent 返回结构化 JSON 后：
checked = adapter.complete_qa_review(
    scheduler,
    "T1",
    {
        "status": "completed",
        "run_id": "QA_HOST_RUN_ID",
        "model": "QA_MODEL",
        "result": {
            "status": "passed",  # 或 rework_required / blocked
            "reason": "逐项验收说明",
            "evidence_refs": ["reports/qa-evidence.json"],
        },
    },
    review_id=review["review_id"],
)
```

`request_qa_review()` 只把验收标准、结构化员工结果和产物引用交给 QA Agent；`passed` 必须有证据引用。复核期间同一任务的下游依赖停留等待；返工时原任务进入 `review`，通过后依赖才可继续。宿主回调缺失、派发异常或 QA 输出结构不合格时，不会写入通过结论；任务留在 QA 待复核状态并保存错误原因。`review_id` 同时作为稳定幂等键，迟到或过期的结果会被拒绝。

该流程由宿主显式调用，不会因仅安装 MakeCrew 就自动创建 Codex 子 Agent。部署前应确认 `spawn_subagent` 已绑定，并在真实宿主完成链路中接入 `request_qa_review()` 与 `complete_qa_review()`；单元测试使用模拟回调，不代表桌面端已连接。

任务包带有稳定的 `idempotency_key`（`run_id:task_id`）。超时后重发同一任务时，
宿主应按此键去重外部副作用；它代表可重复投递的关联键，不是宿主自动提供的
exactly-once 保证。回调异常会留下 trace 并把任务置为 `waiting_host`；宿主可以用
`JsonCheckpointStore` 保存紧凑节点状态，再通过 `RetryPolicy` 决定是否从检查点续作。
批次状态可由 `BatchScheduler.restore(state_path, ...)` 重建；宿主需重新绑定回调并负责
外部副作用去重。

当前 `CodexAdapter` 仍是完整请求/回执边界；另有两个不发请求的协议事件适配器，用于将 OpenAI Responses 与 Anthropic Messages 的实际流事件归一化。它们不替代 Codex 回调，也不是厂商 SDK 或完整模型客户端。

### OpenAI Responses 与 Anthropic Messages 工具流

OpenAI 官方 Responses 流使用 `response.output_item.added` 提供 function-call 的 item/call 身份，使用 `response.function_call_arguments.delta` 发送参数片段，并以 `response.function_call_arguments.done` 提供最终参数；事件带 `sequence_number`。该 `done` 事件本身不放行工具：它也可能出现在中断或不完整响应中。`OpenAIResponsesToolStreamAdapter` 按 response ID 与序号去重增量，并校验最终参数字符串和累计片段一致；只有收到成功的 `response.completed` 后才返回可路由调用列表。

Anthropic 官方 Messages 流以 `message_start`、`content_block_start`、`content_block_delta` 和 `content_block_stop` 表示消息及工具块生命周期；`input_json_delta.partial_json` 是片段，块结束时才解析。`AnthropicMessagesToolStreamAdapter` 只接收 `tool_use` 客户端工具块，忽略文字、thinking、`server_tool_use` 和未知事件；`error` 事件会显式报错。块结束仍不放行工具，只有完整 `message_stop` 且最终 `stop_reason` 为 `tool_use` 才返回工具调用列表。该事件格式没有文档化的逐事件序号，因此 adapter 使用进程内生成的事件 ID，宿主需将每个 SSE 事件投递一次；若消息中途断开，就重启整个任务，不将重放片段拼接到现有 adapter，也不把半截 JSON 当成可执行参数。

```python
from ai_company_os import (
    AnthropicMessagesToolStreamAdapter,
    OpenAIResponsesToolStreamAdapter,
)

openai_stream = OpenAIResponsesToolStreamAdapter()
for event in openai_event_dicts:
    calls = openai_stream.feed(event)
    if calls is not None:  # 仅 response.completed 会返回工具调用
        for call in calls:
            # 宿主再按工具 schema、权限策略及副作用幂等规则检查后路由。
            route_validated_tool_call(call)
openai_stream.finish()  # 缺少成功终止事件或参数未完成时会抛 IncompleteToolCallError

anthropic_stream = AnthropicMessagesToolStreamAdapter()
for event in anthropic_event_dicts:
    calls = anthropic_stream.feed(event)
    if calls is not None:  # 仅完整 message_stop 会返回工具调用
        for call in calls:
            route_validated_tool_call(call)
anthropic_stream.finish()
```

两个 adapter 均只接收已解码的字典事件，不联网、不执行工具，也不代替宿主做 JSON Schema、权限或业务校验。任何流式中断时，宿主应丢弃该次 adapter 内的部分参数；用 `BatchScheduler.restore(state_path, ...)` 恢复已保存的任务状态，再以原 `run_id:task_id` 幂等键重派任务。OpenAI 可用 response ID 与 `sequence_number` 识别同一流中的重复事件；Anthropic 当前 adapter 没有稳定的逐事件重放去重，重试整条任务并由宿主对外部副作用按任务幂等键去重。

协议字段依据官方文档（查阅日期：2026-10-26）：[OpenAI Responses streaming events](https://platform.openai.com/docs/api-reference/responses-streaming)、[Anthropic Messages streaming](https://docs.anthropic.com/en/api/messages-streaming)。

### 规范化增量工具参数

宿主接入支持流式工具调用的模型时，可先把厂商事件映射成统一增量事件，再交给
`ToolCallDeltaAssembler`。`arguments_delta` 是新增片段，不是累计快照；适配器应显式识别
厂商事件类型，不能把两种语义混用。`complete=true` 代表该调用的参数流已完整。

```python
from ai_company_os import ToolCallDeltaAssembler

assembler = ToolCallDeltaAssembler()
assembler.feed({
    "event_id": "evt-1",
    "call_id": "call-7",
    "name_delta": "search",
    "arguments_delta": '{"offset":',
})
ready_to_route = assembler.feed({
    "event_id": "evt-2",
    "call_id": "call-7",
    "arguments_delta": '0,"limit":10}',
    "complete": True,
})
if ready_to_route is not None:
    # 宿主在这里做工具策略校验并调用对应工具。
    pass
assembler.finish()  # 若流中断且仍有未完成调用，会报告 pending call IDs
```

事件需带稳定 `event_id` 与 `call_id`。相同 ID、相同内容的事件会去重；同 ID 不同内容会报错。
多个调用可以交错到达，各自独立累积。参数需在完成事件到达时解析为 JSON 对象，否则不会产出
可路由调用。该组件只拼装和验证规范化事件，不解析任何厂商协议、不执行工具，也不替代宿主
的工具调用幂等处理。Codex 完整请求/回执边界与上面的两个模型协议事件适配器各自独立。

也可以先运行 `makecrew codex-audit --supervisor-id PM-001`，查看当前主管
身份、已接通的宿主回调、缺失项和并发建议。该检查不创建 Agent、不发送消息，
适合安装或重启后先做一次连接自检。

### CEO 线程轮换适配器

CEO 接班需要宿主额外绑定 `open_supervisor_thread`、`set_thread_pinned` 和 `set_thread_archived`。MakeCrew 内核生成和校验接班包；宿主负责真实的新建、置顶和归档动作：

```python
from ai_company_os import CeoContinuityManager, CodexAdapter

continuity = CeoContinuityManager("WORKSPACE")
adapter = CodexAdapter(
    supervisor_id="CEO-001",
    supervisor_thread_id="OLD_THREAD_ID",
    send_to_thread=host.send_to_thread,
    open_supervisor_thread=host.open_supervisor_thread,
    set_thread_pinned=host.set_thread_pinned,
    set_thread_archived=host.set_thread_archived,
)
result = adapter.rollover_ceo(continuity, current_state_snapshot)
```

`send_to_thread` 的结果应包含 `verification` 对象，字段为 `project_ids`、`task_ids`、`decision_ids`、`risk_ids` 和 `handoff_digest`。回调缺失时返回 `pending_host_adapter`；新线程未返回校验时返回 `awaiting_candidate_verification`。这两种状态都不会切换本地活动 CEO 指针。宿主不应把本地接班文件存在当成线程已创建的证据。

## Claude

- 将 CEO 或岗位提示词放入 Project Instructions。
- 每个长期项目建立一个 Project，上传该项目的上下文包和验收标准。
- 跨项目协作时只粘贴差量交接，不粘贴全部聊天记录。

## Gemini / 其他对话模型

- 把角色提示词放在系统指令或首条固定消息。
- 如果平台只有一个对话，使用“一个对话模拟完整流程”方式。
- 工具调用能力由平台决定；将可用工具名称写入专业员工的岗位说明。

## 自建 Agent 框架

将任务卡作为结构化输入，将路由结果作为状态机：`intake -> route -> execute -> review -> deliver -> log`。每个 Worker 接收最小上下文包，交接使用 YAML 或 JSON 差量对象。

单任务澄清时，宿主模型先判断仍有哪些会改变结果的缺口，并以
`material_gaps=[{"question_id", "prompt", "reason"}]` 传给 `plan_request()`。
每轮展示 1-3 项；用户回答后把已解决 ID 写入 `answered_question_ids`，直到
`clarification.ready` 为 `true`，或用户授权使用默认值。用户的答案应通过
`answers={question_id: value}` 一并传回；仅传 ID 的旧适配器仍可运行，但无法
把回答内容带入后续方案。

需求清晰后，宿主应把实际已安装 Skill ID 传入 `installed_skill_ids`。
`plan_request()` 先做本地匹配；存在缺口时，再把缺失 ID 传给
`skill_searcher(task, missing_skill_ids)`。搜索结果至少包含 `skill_id`、`name`、
`description` 和 `source`。`candidates_found` 状态只展示候选，用户选择后由宿主安装，
安装完成再刷新本地清单。

```python
result = plan_request(
    task,
    installed_skill_ids=host.list_installed_skill_ids(),
    skill_searcher=lambda task, missing: host.search_skills(task, missing),
    method_searcher=lambda task, domains: host.search_methods(task, domains),
)
```

批量并发时实现线程适配器并传给 `BatchScheduler`：

```python
def open_thread(employee_id, project, role):
    # 在宿主平台查找或创建该员工在该项目的对话
    return {"thread_id": "HOST_THREAD_ID", "reused": False}
```

在 Codex 适配器中，`BatchScheduler.supervisor_id` 表示主管 Agent；`dispatch_ready()` 返回的每个 `task_packet` 就是发给一个员工 Agent 的最小输入。任务包包含 `file_scope`；独立写入任务应映射到独立 Worktree，共享文件范围应保持串行。若提供 `agent_dispatcher(thread_id, task_packet)`，调度器会把任务包直接交给 Codex 原生 Agent，并在 `host_dispatch` 中保留宿主回执。员工完成后，宿主把 `summary`、`evidence`、`risks` 和 `next_steps` 传给 `mark_done(result=...)`，主管通过 `aggregate_results()` 获取紧凑汇总。不要把完整员工历史复制给主管或其他员工。

调度器负责依赖图、并发上限、预算、暂停/恢复/取消和状态汇总；适配器负责实际创建对话、发送最小任务包、接收结果并回写 `mark_done()` 或 `mark_failed()`。

## 工具与 Skill 配置原则

按岗位配置能力，而不是把所有工具塞给每个员工：开发员工配置代码、测试和部署工具；研究员工配置搜索、文档和引用工具；内容员工配置文案、图像和视频工具；Skill 员工配置文件系统、搜索和 Skill 加载/验证能力。变更工具前先记录版本和回滚方法。

## P0 机制适配器

MakeCrew 提供三个可选的轻量契约，不改变现有单任务路径：

- `skill-audit` / `audit_skill_directory()`：启动或更新 Skill 时检查 `SKILL.md` 的名称、描述、目录一致性和 `references/`、`scripts/`、`assets/` 渐进披露目录。运行 `makecrew skill-audit --path SKILLS_DIR`。
- `skill-inventory` / `inventory_skill_directory()`：仅返回 Skill 名称、描述、路径、状态和资源布局，供宿主路由；指令正文、引用和脚本按匹配结果再加载。运行 `makecrew skill-inventory --path SKILLS_DIR`。
- `review-and-critique`：开发里程碑、合并前或发布前接入独立审查器；普通查询跳过。审查结果必须包含严重程度、文件证据、修复建议和复核状态。
- `checkpoint-recovery` / `JsonCheckpointStore`：宿主在节点边界保存紧凑状态和幂等键，重启后读取最新节点；`RetryPolicy` 只允许有界、可重试失败从最近检查点继续。

宿主接入时可替换存储和审查实现，但应保留 `task_id`、`node_id`、`idempotency_key`、`resume_from` 和失败原因字段，避免把“已生成计划”误报为已执行。
