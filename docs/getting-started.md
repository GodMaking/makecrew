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
