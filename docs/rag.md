# RAG / 作用域检索

AgentFlow OS 的 RAG 层负责“按身份和项目取需要的知识”，不负责把所有对话或文件全部塞进上下文。

## 当前 MVP

`ai_company_os.rag` 提供无第三方依赖的可移植基线：

- `KnowledgeRecord`：内容、来源、项目、状态、证据等级和可见角色；
- `RetrievalScope`：调用者角色、项目范围、结果数量和字符预算；
- `HybridRetriever`：关键词/中文双字短语匹配、标题加权、有效状态过滤和新鲜度加分；
- `RetrievalHit.citation()`：返回记录 ID、标题、来源、更新时间、证据等级和作用域；
- `Retriever` / `HostRagAdapter`：供宿主接入 BM25、向量库或远程搜索服务。

示例：

```python
from ai_company_os.rag import HybridRetriever, KnowledgeRecord, RetrievalScope

index = HybridRetriever([
    KnowledgeRecord(
        record_id="eng-001",
        title="工程工作台",
        content="施工进度计划和造价数据库工作流",
        source="projects/engineering/context-pack.md",
        scope="project",
        project_id="engineering",
    )
])

hits = index.search(
    "工程 造价",
    RetrievalScope(actor="manager", project_ids=("engineering",), max_results=8),
)
for hit in hits:
    print(hit.record.content, hit.citation())
```

## 权限规则

1. 权限过滤先于相关性评分；员工不能通过换关键词读取其他项目。
2. `company` 记录可按角色开放；`project` 和 `task` 记录必须匹配项目范围。
3. `draft`、`superseded`、`archived` 默认不进入生产回答；审计时显式开启对应选项。
4. 每个主管或员工对话应绑定自己的 `RetrievalScope`，而不是共享全局索引权限。
5. 结果带来源和证据等级；没有来源的内容不进入“已验证事实”。

## 记忆写回

任务完成后只把稳定结论提升为项目记忆：决策、交付物、验证证据、失败原因和下一步。完整聊天保留在宿主平台，按需追溯，不自动全文入库。

## 宿主接入

向量数据库、嵌入模型、文件监听和持久化由宿主适配器提供。适配器应保持本项目的 `KnowledgeRecord`、`RetrievalScope` 和 `RetrievalHit` 契约，并报告索引版本、更新时间、来源和失败原因。接入新后端前，先用同一组作用域和引用测试回放，确认结果不越权且相关性不低于基线。

## 后续切片

## 本地 CLI

以下命令只作用于你明确指定的路径：

```bash
agentflow rag-init --index .makecrew/rag/index.json
agentflow rag-sync --index .makecrew/rag/index.json --source ./knowledge --scope project --project demo
agentflow rag-query "工程 造价" --index .makecrew/rag/index.json --actor manager --project demo
agentflow rag-audit --index .makecrew/rag/index.json
```

同步会记录文件 SHA-256；未变化文件跳过，修改文件只替换自己的分块，删除文件会移除对应分块。默认支持 Markdown、纯文本、JSON、YAML 和 CSV。不会读取视频、二进制文件或目录外内容。

## 后续切片

1. BM25/向量双路召回与重排序；
2. 过期、冲突和废止记录审计；
3. 与项目主管、专业员工身份配置绑定的宿主适配器。
