# Adaptive Routing / 自适应单任务分流

MakeCrew 不要求每个新对话执行同一条流水线。`task-intake` 先做一次本地轻量判断，再生成本次任务真正需要的工作流节点。

## 分流表

| 识别结果 | 触发信号 | 实际路径 | 用户确认 |
|---|---|---|---|
| `direct` | 目标清楚、常规、可回退 | 执行 -> 验收 -> 交付 | 不增加确认轮次 |
| `clarify` | 缺少会改变结果的信息 | 每轮询问 1-3 个关键问题 -> 检查剩余缺口 -> 按需继续 | 回答问题或授权 AI 决定 |
| `discovery` | 明确要求搜索、调研、比较、推荐、借鉴方法/Skill | 方法与 Skill 发现 -> 执行 -> 验收 -> 交付 | 同时要求先看方案时确认 |
| `plan_first` | 用户明确说“先给方案”“先别执行”等 | 形成方案 -> 用户确认 -> 执行 -> 验收 -> 交付 | 需要一次确认 |
| `guarded` | 公开发布、付款、删除、投放、战略或资源决策 | 目标/影响/回滚 -> 用户确认 -> 执行 -> 验收 -> 交付 | 需要一次确认 |
| `team` | 一个任务同时需要多个专业领域 | 当前对话动态专家组 -> 并行执行 -> 统一验收 -> 交付 | 取决于动作性质 |
| `batch` | 用户一次提交多个独立任务 | CEO 拆分 -> 复用员工线程 -> 并行/依赖调度 -> 汇总验收 | 批次方案确认 |

## 为什么这样更省 Token

- 常规任务跳过需求复述、外部搜索、候选方案比较和确认往返。
- 已安装且匹配的 Skill 直接使用；出现能力缺口时才扩大搜索。
- 单任务的多个专业能力留在当前对话内，减少 CEO 转述和重复背景。
- 多个独立任务才建立批次，并只向员工发送最小任务包。
- 普通成功任务结束于交付；出现质量信号时才进入学习闭环。

## 澄清何时结束

问题总数没有固定上限，实际范围是 0-N；每轮限制在 1-3 个，避免一次抛出过长问卷。满足任一条件后结束：

1. 目标、使用者、现有基础、关键约束、交付深度和验收标准达到可执行清晰度；
2. 用户明确授权 AI 采用默认值或最佳实践；
3. 剩余信息只影响次要细节，可以在第一版交付后再调整。

每个问题都有稳定 `question_id`。宿主把已回答 ID 传回 `answered_question_ids`，下一轮会跳过已解决问题；`clarification.max_total_questions` 为 `null`，表示总数没有硬上限。内置规则提供通用缺口，宿主 AI 还可以通过 `material_gaps` 增加任意数量的领域专属问题，系统负责去重和分轮。

## 用户如何控制路径

用户始终可以用自然语言覆盖自动判断：

```text
直接做，按现有项目规范处理。
先给我方案，不要开始制作。
先搜索目前更合适的方法和 Skill，再给我比较。
这五个任务交给 CEO 并行安排，统一汇报。
这次验收失败了，记录原因并进入自进化复盘。
```

## 示例

### 1. 常规修复

```text
修复登录页表单校验并补测试，项目目录为 demo。
```

结果：`direct`。直接选择工程 Skill 和工具，执行后提交测试证据。

### 2. 真正模糊的需求

```text
帮我做个网站。
```

结果：`clarify`。每轮询问用途、现有项目、完成标准等最关键的 1-3 项，回答后继续检查剩余缺口。

### 3. 方法研究

```text
搜索并比较适合本地知识库的开源 RAG 方案。
```

结果：`discovery`。调用可用搜索器，记录来源与取舍，再交付比较结果。

### 4. 先看方案

```text
先给方案不要执行：重新设计产品首页。
```

结果：`plan_first`。先给方案和验收标准，确认后进入制作。

### 5. 生产发布

```text
把当前版本发布到生产环境。
```

结果：`guarded`。展示目标、版本、验证和回滚信息，确认后发布。

## 自进化触发条件

以下任一信号出现时，工作流加入 `learn` 节点。`task-intake` 会识别常见反馈词，宿主也可以显式传入 `learning_signal=True`：

- 用户明确差评；
- 验收失败；
- 任务返工；
- 同类问题重复出现；
- 用户明确要求复盘或训练员工。

学习层记录任务 ID、评分、反馈和根因。重复证据生成小范围提案；提案经过历史任务回放，候选得分更高后再进入审阅。

## Python 接口

```python
from ai_company_os import plan_request

direct = plan_request("修复登录页表单校验并补测试，项目目录为 demo")
assert direct["mode"] == "direct"
assert direct["execute"] is True

plan = plan_request("先给方案：重新设计产品首页")
assert plan["mode"] == "plan_first"
assert plan["execute"] is False

approved = plan_request("先给方案：重新设计产品首页", confirmed=True)
assert approved["execute"] is True

review = plan_request(
    "修复登录页表单校验并补测试，项目目录为 demo",
    learning_signal=True,
)
assert review["learning_loop"]["enabled_for_this_task"] is True

automatic_review = plan_request("登录页修复结果不合格，需要返工并复盘")
assert automatic_review["learning_loop"]["trigger_reason"] == "task_feedback"

gap = plan_request(
    "整理本地知识库索引",
    capability_gap=True,
)
assert gap["discovery"]["reason"] == "capability_gap"

first = plan_request("帮我做个网站")
second = plan_request(
    "帮我做个网站",
    clarification_round=2,
    answered_question_ids=first["clarification"]["question_ids"],
)
assert set(first["clarification"]["question_ids"]).isdisjoint(
    second["clarification"]["question_ids"]
)

domain_review = plan_request(
    "整理本地知识库索引",
    material_gaps=[
        {
            "question_id": "citation-format",
            "prompt": "索引需要保留哪种引用格式？",
            "reason": "引用格式影响索引结构",
        }
    ],
)
assert domain_review["mode"] == "clarify"
```
