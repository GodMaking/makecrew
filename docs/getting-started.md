# MakeCrew / 5 分钟上手

MakeCrew 不依赖特定模型、插件或编程语言。单个清晰任务可以留在一个对话中；只有多个独立任务、跨项目决策或需要并发时，才使用多个 Agent/对话。

## 给宿主 AI 的标准安装提示词

将下面整段发给你的 Codex、Claude、Gemini 或其他支持 Skill 的 AI。它负责读取仓库、检查宿主能力、保留现有配置并完成最小验证：

```text
请安装并配置 MakeCrew：https://github.com/GodMaking/makecrew

安装前：
1. 读取 README.md、skills/makecrew/SKILL.md、skills/task-intake/SKILL.md、
   docs/getting-started.md 和 docs/platform-adapters.md。
2. 盘点当前平台支持的 Skill、工具、文件系统、搜索、对话/线程和执行器。
3. 读取已有普通对话、员工、项目记忆和配置；保留原内容，不覆盖、搬动或删除。

配置：
1. 启用 MakeCrew 和 task-intake 作为入口 Skill（按当前平台支持的安装方式）。开发网站、应用或产品时，按需加载 `product-delivery`。
2. CEO-001、PM-001、QA-001 和专业岗位都只是可选模板；没有员工时先提出建议，不自动创建。
3. 为每个岗位写明 Skill、工具、记忆范围、输出契约和验收标准。
4. 配置本地 Skill 清单：每个清晰任务先本地匹配；缺少关键 Skill 时只搜索候选，
   展示用途和来源，等我选择后再安装或使用。

验证：
1. 清晰单任务：应本地匹配后直达执行。
2. 缺少 Skill：应返回候选和用户选择，不应静默安装。
3. 模糊需求：每轮问 1-3 个关键问题，总数 0-N，直到可执行。
4. 多任务：应生成 CEO 批次、依赖、并发和预算计划。

创建任一员工或新对话前，先列出创建理由、职责、所需 Skill、工具、记忆范围、预计成本和影响，
等我明确同意后再创建。请报告：实际启用的 Skill、员工和工具映射、四项测试结果、未接入能力、
权限/文件变更和回滚方法。没有真实证据的项目标记为“待宿主配置”。
```

安装提示词只负责配置，不授权宿主扩大任务范围；公开发布、付费、删除和其他不可逆动作仍需单独确认。

安装完成后，宿主 AI 应立即在当前对话用大白话告诉用户：MakeCrew 已就绪；
说明轻量模式、基础团队模式和按需创建员工模式；说明原有普通对话、员工、项目记忆和配置会保留；
说明单个清晰任务留在当前对话，缺少员工时先给出理由和成本，用户同意后才创建。
这段欢迎说明每个工作区只展示一次，不发送每日重复通知。

## 安装后触发方式

完整说明见 [`auto-trigger.md`](auto-trigger.md)。

Skill 支持主动和自动两种触发方式。用户可以在 Codex 输入 `$makecrew` 或
`$task-intake`，明确要求先澄清需求、匹配能力并展示方案。自动匹配依赖 Skill
描述，适合补充触发，但不保证每个新对话都会加载。要让新对话稳定先走需求入口，
在 Codex Home 执行：

```bash
makecrew install-codex-global-intake --codex-home CODEX_HOME
```

命令会在 `AGENTS.md` 追加带标记的规则，保留原有内容并在首次修改时生成备份。
重启 Codex 后，对网站、应用、产品、视频、文档、活动和自动化等多步骤任务，
宿主应先澄清并展示 Skills、工具、流程、验收标准、成本和风险，等用户确认后再执行；
简单查询、读取和状态检查保持直达。

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

## 方式 A：多个员工对话（仅在需要时）

1. 不要为安装自动新建对话。需要跨项目统筹时，先审阅 `CEO-001` 提案；同意后再新建一个对话，粘贴 `roles/ceo.md`，命名为“CEO 总控”，或绑定你指定的已有对话。
2. 为每个长期项目按需创建项目主管对话，粘贴 `roles/project-manager.md`，并附上该项目的 `context-pack.md`；创建前同样先展示提案并等待同意。
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

第一次运行会返回 `status: awaiting_employee_approval` 和
`employee_proposals`，例如提案 ID 为 `ENG-001`。把提案展示给用户并得到同意后，
再这样派发：

```python
result = CrewOrchestrator("./my-ai-workspace", dispatcher=send_to_employee).dispatch(
    "开发网站并准备上线", project="demo-site", approved_employee_ids=["ENG-001"]
)
```

规则是：已有匹配员工优先；没有匹配岗位时返回 `employee_proposals`，
提案包含理由、职责、Skill、工具、记忆范围、成本和影响，并将状态设为
`awaiting_employee_approval`。用户批准对应 ID（或明确批准全部）后再次派发，
系统才创建员工或新对话。同类任务稳定重复后可调用 `promote(employee_id)` 升级为长期自定义员工，
一次性任务则调用 `archive(employee_id)` 归档。CEO 只做决策和派单，不会因为缺少专业岗位而默默代做。

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
CEO 为每项任务复用已有员工；缺岗位时先汇总员工提案并等待一次批准，批准后再并行派发。

### 多任务的并发控制

批量任务先登记依赖，再派发可执行节点。示例：

```bash
makecrew batch-dispatch --project demo-site --max-concurrency 2 \
  --total-tool-calls 12 --depends-on T3=T1,T2 \
  T1::研究用户 T2::修复登录页 T3::准备发布说明
```

`BatchScheduler` 会复用同一项目中同一员工的线程；依赖、并发或预算不满足时任务留在等待状态。运行中可调用 `set_max_concurrency()` 调整上限，用 `pause()/resume()` 暂停和恢复，用 `cancel()` 取消，用 `mark_failed()` 记录失败原因。CLI 只生成宿主适配器的派发清单，真实对话创建和执行由平台适配器完成。

在 Codex 中，一个子 Agent 就是一个 MakeCrew 员工；负责拆分、派发、等待和汇总的父 Agent 是主管。`BatchScheduler` 会把每项任务输出为带有主管 ID、员工 ID、Skill、工具、项目上下文差量、依赖、文件范围和验收门禁的 `task_packet`。宿主通过 `agent_dispatcher(thread_id, task_packet)` 将任务交给原生 Codex Agent，员工完成后只需回传结论、证据、风险和下一步，主管再统一反馈给用户。

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
