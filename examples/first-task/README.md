# First Task / 首次演示：一天交付一个小网站

这是一个不依赖具体模型的演示。把下面的任务卡发给 CEO，总控会先拆解并请求确认，再由项目主管组队。

## Task card

```yaml
id: DEMO-001
title: "制作一个单页产品介绍网站"
project: "demo-site"
goal: "交付一个可在本地预览的响应式单页"
success_criteria:
  - "移动端和桌面端都能打开"
  - "包含标题、功能列表、行动按钮"
  - "有可复现的预览或截图"
owner: "demo-project-lead"
collaborators: [product, frontend, reviewer]
route: project_lead
inputs: ["产品简介", "品牌颜色", "参考链接"]
constraints: ["先给方案，不直接制作最终稿"]
deliverables: ["页面源码", "预览地址或截图", "验收记录"]
approval_required: true
status: todo
acceptance:
  reviewer: "independent-reviewer"
  checks: ["核心流程可用", "移动端不溢出", "无敏感信息"]
```

## CEO 首条消息

```text
请按 AI Company OS 处理 DEMO-001。先输出路由、岗位、依赖、交付物和验收门禁；我确认后再执行制作。
```

## 预期交接

项目主管完成拆解后，用 `templates/handoff.md` 向各员工发送最小上下文；验收员只接收成功标准和交付物，不接收制作过程的全部历史。
