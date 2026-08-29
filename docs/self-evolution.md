# Self-Evolution Layer / 自进化层

自进化层是每个任务验收后的固定闭环：把评分、反馈和根因转成可审阅的改进提案，再用历史任务回放验证提案效果。它默认只记录和建议，不直接覆盖员工 Skill、路由规则或项目文件。

## 循环

```text
任务执行 -> 验收评分 -> 记录反馈/根因 -> 生成提案
                                      -> 历史回放
                                      -> 候选平均分更高才采用
```

## 最小用法

```python
from ai_company_os import LearningEngine

engine = LearningEngine(".ai-company/learning.json")
engine.record(
    "T-001",
    employee_id="ENG-001",
    score=2,
    feedback="上线前漏了浏览器验证",
    root_cause="验收步骤遗漏",
)
proposals = engine.propose()  # 状态为 proposed，等待审阅
result = engine.propose_from_scores(
    proposals[0].proposal_id,
    baseline=[3, 3, 4],
    candidate=[4, 4, 4],
)[0]
assert result.status == "approved"
```

## 三个边界

- **证据优先**：提案必须关联任务 ID、反馈和根因，避免凭空“自我升级”。
- **范围隔离**：员工经验、项目经验和公司经验分开保存，避免错误经验污染全部员工。
- **可回滚**：提案先处于 `proposed`，通过回放后才是 `approved`；真正写入 Skill 由上层平台执行并保留版本。

当前实现提供记录、提炼、回放评分和 JSON 持久化接口，模型调用和平台写入由适配层负责。

## 与单任务入口的关系

`task-intake` 在执行前展示发现到的方法和 Skill；执行完成并通过验收后，
再将结果写入 `LearningEngine`。只有重复失败才生成提案，提案经过代表性
任务回放且候选平均分高于基线后才标记为 `approved`。批准不等于静默改写，
由 Skill 员工或宿主平台按版本提交变更并保留回滚点。
