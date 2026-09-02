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

也可以先运行 `makecrew codex-audit --supervisor-id PM-001`，查看当前主管
身份、已接通的宿主回调、缺失项和并发建议。该检查不创建 Agent、不发送消息，
适合安装或重启后先做一次连接自检。

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
