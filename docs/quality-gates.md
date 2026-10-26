# Quality Gates / 质量门禁

## Universal checks

每项交付在标记完成前至少满足：目标明确、成功标准可验证、负责人明确、证据可访问、已知限制已说明。

## By delivery type

| Type | Required evidence |
|---|---|
| Development | Build/test result, key-flow verification, deployment or rollback state |
| Content | Audience problem, factual sources, opening hook, one clear call to action |
| Video | First-three-second review, readable captions, audio/visual clarity, approved script or storyboard |
| Design | Information hierarchy, target-size preview, brand consistency, export assets |
| Research | Source links, dates, evidence level, uncertainty boundaries |

## Rework loop

验收人写明哪项标准未满足、可复现证据和最小修改建议。`BatchScheduler` 默认每个任务最多派发两轮 QA 返工；超过上限或 QA 明确阻塞时，任务进入 `blocked_qa`，由项目主管重新检查任务范围、输入质量和负责人匹配。主管显式恢复后才继续派发，避免同一路径无限返工。

## 独立 Agent 复核与异常处理

Codex 宿主绑定 `spawn_subagent` 后，可在员工结果完成时调用 `CodexAdapter.request_qa_review(scheduler, task_id)`：MakeCrew 为复核生成稳定 `review_id`，以隔离线程派发给与执行员工不同身份的 QA Agent，只提供验收门、员工结构化结果、产物引用和必要文件范围。QA Agent 不接收执行员工完整对话，也不负责修改产物。

- `qa_review`：复核进行中；该任务的下游依赖保持等待。
- `passed`：必须带 `evidence_refs`，通过后任务回到 `done` 并放行依赖。
- `rework_required`：记录原因与证据，原任务进入 `review`；下游继续等待，原员工可重做。
- `blocked`：任务进入 `blocked_qa`，主管检查缺失输入、验收标准或负责人后显式恢复。
- 复核派发异常、无效 JSON、未知 verdict 或通过但缺少证据：记录异常并回到“员工已完成、QA 待复核”，不生成通过结论。
- 重复投递使用同一 `review_id` 作为 `idempotency_key`；旧 `review_id` 的迟到结果会被拒绝。该键供宿主去重，不等同 exactly-once。

`overview()` 分开展示 `awaiting_qa`、`qa_in_progress`、`rework` 和 `qa_blocked`。若宿主没有绑定 `spawn_subagent`，`request_qa_review()` 返回 `queued`，任务仍是 `done` 且列在 `awaiting_qa`；这表示 QA 接口未接通，不代表已经检查或通过。当前接口是显式调用契约，宿主需在需要质量门的完成路径上调用它并把 QA 回执交给 `complete_qa_review()`；MakeCrew 不会在没有宿主回调的情况下自行创建真实 Agent。

## QA 回归集

固定 10 案例和评分方式见 [`qa-regression.md`](qa-regression.md)。它用来对比 QA Agent / 提示词版本的判定准确率、误放行、误驳回和工具调用量；属于回归评估工具，不会替运行中的主管自动审查或重派任务。
