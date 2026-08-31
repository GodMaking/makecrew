# Platform Adapters / 平台适配

## ChatGPT / Codex

- 将角色文件放入自定义指令、项目说明或独立对话的首条消息。
- 将项目上下文包作为项目文件或固定参考资料。
- 需要真实浏览器、代码仓库、设计或视频操作时，为对应员工启用平台已有工具，并在任务卡写明工具范围。

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

调度器负责依赖图、并发上限、预算、暂停/恢复/取消和状态汇总；适配器负责实际创建对话、发送最小任务包、接收结果并回写 `mark_done()` 或 `mark_failed()`。

## 工具与 Skill 配置原则

按岗位配置能力，而不是把所有工具塞给每个员工：开发员工配置代码、测试和部署工具；研究员工配置搜索、文档和引用工具；内容员工配置文案、图像和视频工具；Skill 员工配置文件系统、搜索和 Skill 加载/验证能力。变更工具前先记录版本和回滚方法。
