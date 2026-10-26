# QA 回归集

MakeCrew 自带 10 个固定、盲测式 QA 案例，用同一组输入对比不同 QA Agent、模型或提示词版本。案例覆盖：

1. 证据完整、产物正确，正常通过；
2. 缺少验收证据；
3. 产物引用指向错误文件；
4. 必需产物缺失；
5. 多个 Agent 的结论冲突；
6. 前置依赖仍被阻塞；
7. 引用存在但不支持验收标准；
8. 已达到返工上限，缺陷仍存在；
9. 一轮返工后修复完成；
10. 关键测试仍失败。

## 运行方式

先导出不含标准答案的案例包：

```bash
makecrew qa-regression --export-cases .makecrew/qa-regression/cases.json
```

让待评估的 QA Agent 逐条读取 `cases`，每个案例输出一个 `status`：`passed`、`rework_required` 或 `blocked`。把结果保存为 JSON：

评估时固定使用同一判断规则：依赖状态为 `blocked` 时判 `blocked`；仍有缺陷且返工次数已达到上限时判 `blocked`；产物缺失/路径不符、验收项缺证据或证据不支持标准、Agent 结论冲突、关键测试失败时判 `rework_required`；其余情况判 `passed`。只按案例输入判断，不补造证据。

```json
{
  "run_id": "qa-run-2026-10-26-a",
  "model": "QA-MODEL-ID",
  "prompt_version": "qa-v1",
  "results": [
    {
      "case_id": "QA-01",
      "status": "passed",
      "tool_calls": 2,
      "reason": "验收项均有对应证据，产物路径匹配"
    }
  ]
}
```

`run_id`、`model` 和 `prompt_version` 会作为报告元数据保留。`tool_calls` 应填宿主侧观测值，而不是让 Agent 自行估算；任一记录缺失调用量时，报告会将总调用量标记为 `null`。对比版本时使用相同案例和采集口径，再执行：

```bash
makecrew qa-regression --results .makecrew/qa-regression/results.json
```

结果包含：

- `verdict_accuracy`：正确判定数 / 固定 10 案例；未提交的案例按未命中计入；
- `false_accept_count`：标准答案要求返工或阻塞，实际却判为通过的数量；
- `false_reject_count`：标准答案为通过，实际却判为返工或阻塞的数量；
- `actual_pass_rate`：实际判为通过的比例；
- `tool_calls_total`：完整提交且每条都有调用量时的总调用数；数据缺失时为 `null`，并列出缺项。

本回归集是结构化合成样例，用于检查判定流程在固定边界条件下是否退化；它不是跨行业质量标准，也不代替真实项目验收。当前报告只提供可比较的测量值，不设置统一放行阈值；阈值应按具体项目的误放行成本和调用预算另行确定。评分器不调用模型、不启动 Agent，也不自动返工。
