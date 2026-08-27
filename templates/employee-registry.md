# Employee Registry / 员工注册表

每个员工一行。注册表是路由索引，不保存完整对话历史。

| id | name | department | skills | projects | memory_location | status | escalation_to |
|---|---|---|---|---|---|---|---|
| W-001 | [开发员工] | 工程 | [代码/测试/部署] | [项目名] | [项目上下文包] | active | [项目主管] |
| W-002 | [运营员工] | 增长 | [研究/分析/平台] | [项目名] | [项目上下文包] | active | [内容主管] |
| W-003 | [验收员工] | 质量 | [检查清单/浏览器验证] | [项目名] | [质量记录] | active | [项目主管] |

## Registration rules

- `skills` 写能力类别，不写无法验证的宣传语。
- `projects` 写当前负责范围，避免一个员工被无边界调用。
- `memory_location` 指向项目上下文包或平台项目，不复制完整聊天记录。
- `status` 使用 `active`、`paused`、`retired`；停用员工不参与新任务。
