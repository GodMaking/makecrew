# Getting Started / 5 分钟上手

这套方法不依赖特定模型、插件或编程语言。你只需要能创建几个独立对话，或使用支持多个 Agent 的工具。

## 运行本地 MVP

需要 Python 3.10 或更高版本。直接在仓库目录运行：

```bash
python -m ai_company_os.cli "开发网站并准备上线，同时研究用户并写宣传文案"
python -m ai_company_os.web
```

也可以安装成命令：

```bash
python -m pip install -e .
ai-company-route "整理竞品资料并写一页结论"
ai-company-demo
```

MVP 使用本地规则生成计划，不上传任务内容。接入真实模型或工具时，再按 `docs/platform-adapters.md` 配置对应员工。

## 方式 A：三个独立对话

1. 新建一个对话，粘贴 `roles/ceo.md`，命名为“CEO 总控”。
2. 为每个长期项目新建一个对话，粘贴 `roles/project-manager.md`，并附上该项目的 `context-pack.md`。
3. 按需要为开发、研究、文案、设计等岗位建对话，粘贴 `roles/worker.md`，再补充岗位专属工具说明；不需要的岗位先不创建，同一岗位可按项目复制多个。
4. 你把跨项目目标发给 CEO；明确的单项工作直接发给专业员工。

## 让主管真正派单

路由计划和实际执行分成两步。宿主平台（例如 Codex 或其他 Agent 运行时）
提供一个 dispatcher 后，`CrewOrchestrator` 会读取 `.makecrew/employee-registry.json`：

```python
from ai_company_os import CrewOrchestrator

def send_to_employee(employee_id, payload):
    # 连接宿主平台的员工对话/API，并返回 status、summary、evidence
    return {"status": "completed", "summary": "员工交付结果"}

result = CrewOrchestrator("./my-ai-workspace", dispatcher=send_to_employee).dispatch(
    "开发网站并准备上线", project="demo-site"
)
```

规则是：已有匹配员工优先；没有匹配岗位时生成 `TEMP-XXXXXXXX` 临时员工；
同类任务稳定重复后调用 `promote(employee_id)` 升级为长期自定义员工，
一次性任务则调用 `archive(employee_id)` 归档。CEO 只做决策和派单，
不会因为缺少专业岗位而默默代做。

## 默认单任务入口

新开一个 Codex 对话后，使用 `task-intake` 做轻量分流，而不是固定走完整流程：

- 明确、常规、可回退的任务直接执行，再验收和交付；
- 只有缺少会改变结果的信息时才提问；总数 0-N，每轮 1-3 个，按需多轮；
- 每个清晰任务先匹配本地已安装 Skill 和方法；缺少匹配 Skill 时搜索候选并让用户选择；
- 需要最新比较、本地无匹配或存在能力缺口时扩大方法搜索；
- 用户要求先看方案，或任务涉及公开、高成本、不可逆动作时才等待确认；
- 单任务需要多个专业能力时，在当前对话形成动态专家组；
- 差评、验收失败、返工、重复问题或明确复盘时才触发学习记录。

这条路径不经过 CEO，不创建额外员工对话，也不复制完整历史。

只有你一次发来多个独立任务，或明确要求并发处理时，才使用 CEO 批量模式：
CEO 为每项任务复用已有员工，缺岗位时自动创建对应的新对话，并行派发后统一汇报。

### 多任务的并发控制

批量任务先登记依赖，再派发可执行节点。示例：

```bash
makecrew batch-dispatch --project demo-site --max-concurrency 2 \
  --total-tool-calls 12 --depends-on T3=T1,T2 \
  T1::研究用户 T2::修复登录页 T3::准备发布说明
```

`BatchScheduler` 会复用同一项目中同一员工的线程；依赖、并发或预算不满足时任务留在等待状态。运行中可调用 `set_max_concurrency()` 调整上限，用 `pause()/resume()` 暂停和恢复，用 `cancel()` 取消，用 `mark_failed()` 记录失败原因。CLI 只生成宿主适配器的派发清单，真实对话创建和执行由平台适配器完成。

## 方式 B：一个对话模拟完整流程

当平台不方便创建多个对话时，把 `roles/ceo.md`、`roles/project-manager.md` 和 `roles/worker.md` 作为三个角色段落放进同一系统提示词，并要求模型在每个任务开头输出当前路由。小任务仍走直达员工模式。

## 第一个任务

复制 `templates/task-card.md`，填写目标和验收标准，然后发送：

```text
请按任务卡判断路由。先给出负责人、协作岗位、交付物和验收标准；方案得到确认后再执行高成本步骤。
```

## 记忆建立

每个长期项目只维护一份上下文包。把稳定规则写进去，把临时讨论留在任务记录。项目换人时，交接上下文包和最近一次差量交接即可。

## 最小可用配置与扩展

```text
1 个 CEO
1 个项目主管（每个长期项目一个）
1 个验收员
0 个或若干专业员工（按任务需要增加）
```

先用一个项目跑通，再增加岗位；岗位数量由用户决定，不以数量作为效果指标。

已有工作区可用下面的命令增量添加自定义员工：

```bash
makecrew add-employee --path ./my-ai-workspace --id MKT-001 --name "增长员工" --department "增长" --skills "渠道分析,复盘" --tools "web_search,browser"
```

注册表会拒绝重复 ID，并保护 `CEO-001`、`PM-001`、`QA-001`。自定义员工的项目记忆范围、Skill 和工具由你填写，后续再接入对应平台。
