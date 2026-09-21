# Memory Model / 记忆模型

## Three layers

- **Company memory**：长期偏好、角色边界、成本和质量规则。
- **Project memory**：项目目标、路径、技术栈、决策、风险和完成定义。
- **Task memory**：本次输入、执行记录、交付物、验收意见。

默认只注入公司记忆和所属项目上下文包；跨项目协作通过差量交接。项目长期员工继续使用原对话，不用 CEO 重述全部历史。

## Retention

完成任务后把稳定决策提升到项目记忆，把一次性细节留在任务记录。定期归档已失效路径、旧方案和重复失败，避免上下文膨胀。

## CEO continuity / CEO 接班

`CEO-001` 是稳定角色 ID，对话线程只是该角色的一代运行载体。CEO 的关键运行状态必须写入 `.makecrew/`，不能只留在聊天历史：

- `company-memory.md`：稳定偏好和公司级规则；
- `portfolio-index.json`：活动项目索引；
- `decision-log.jsonl`：重要决策流水；
- `tasks.json` 与项目控制塔：未完成任务、依赖、预算和风险；
- `employee-registry.json`：员工身份与状态；
- `ceo-continuity.json`：活动 CEO 线程、代次和待处理接班；
- `handoffs/CEO-HANDOFF-*.json`：带摘要校验的紧凑接班包。

上下文低于 70% 正常使用；70%-85% 压缩已完成内容；85%-95% 准备接班；达到 95% 时，先完成接班再承接复杂任务。接班包只保存当前项目、未完成任务、活动决策、高风险、预算、员工状态、下一步和证据引用，不保存完整聊天。新 CEO 必须回传这些对象的 ID 与接班包摘要，通过校验后才更新活动线程指针。
