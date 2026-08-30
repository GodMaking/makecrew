import unittest

from ai_company_os.rag import HybridRetriever, KnowledgeRecord, RetrievalScope


class RagTests(unittest.TestCase):
    def setUp(self):
        self.retriever = HybridRetriever([
            KnowledgeRecord("company-1", "公司规则：发布前必须经过用户确认。", "company/rules.md", title="发布门禁"),
            KnowledgeRecord("eng-1", "工程项目使用施工进度计划和造价数据库。", "projects/eng/context.md", title="工程工作台", scope="project", project_id="engineering"),
            KnowledgeRecord("eng-old", "旧版工程方案，已废止。", "projects/eng/old.md", title="旧方案", scope="project", project_id="engineering", status="superseded"),
            KnowledgeRecord("other-1", "英语项目的词汇训练计划。", "projects/words/context.md", title="词阶", scope="project", project_id="words"),
            KnowledgeRecord("private-1", "仅员工可见的研发笔记。", "private/notes.md", allowed_actors=("employee",)),
        ])

    def test_company_and_project_scope_are_filtered_before_scoring(self):
        hits = self.retriever.search("工程 造价", RetrievalScope("manager", project_ids=("engineering",)))
        self.assertEqual([hit.record.record_id for hit in hits], ["eng-1"])
        self.assertTrue(hits[0].citation()["source"].endswith("context.md"))

    def test_manager_cannot_read_other_project_or_employee_private_notes(self):
        hits = self.retriever.search("项目 训练 笔记", RetrievalScope("manager", project_ids=("engineering",)))
        ids = [hit.record.record_id for hit in hits]
        self.assertIn("eng-1", ids)
        self.assertNotIn("other-1", ids)
        self.assertNotIn("private-1", ids)

    def test_employee_can_read_private_record_when_explicitly_allowed(self):
        hits = self.retriever.search("研发 笔记", RetrievalScope("employee", project_ids=("engineering",)))
        self.assertEqual([hit.record.record_id for hit in hits], ["private-1"])

    def test_superseded_record_remains_hidden_by_default(self):
        hits = self.retriever.search("工程 方案", RetrievalScope("manager", project_ids=("engineering",)))
        self.assertNotIn("eng-old", [hit.record.record_id for hit in hits])

    def test_inactive_records_require_explicit_opt_in(self):
        hits = self.retriever.search("旧版 工程 方案", RetrievalScope("manager", project_ids=("engineering",), include_inactive=True))
        self.assertIn("eng-old", [hit.record.record_id for hit in hits])

    def test_result_budget_limits_chunks_and_empty_query_is_free(self):
        scope = RetrievalScope("ceo", max_results=1, max_chars=200)
        hits = self.retriever.search("公司 工程", scope)
        self.assertEqual(len(hits), 1)
        self.assertEqual(self.retriever.search("", scope), [])

    def test_invalid_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            KnowledgeRecord("bad", "内容", "x.md", scope="project")
        with self.assertRaises(ValueError):
            RetrievalScope("unknown")

    def test_semantic_scorer_can_recall_lexically_missing_record_and_rerank(self):
        def semantic(query, records):
            return {record.record_id: (0.95 if record.record_id == "other-1" else 0.1) for record in records}

        retriever = HybridRetriever(self.retriever._records.values(), semantic_scorer=semantic)
        hits = retriever.search("完全不同的说法", RetrievalScope("manager", project_ids=("words",)))
        self.assertEqual(hits[0].record.record_id, "other-1")

    def test_semantic_weight_is_bounded(self):
        with self.assertRaises(ValueError):
            HybridRetriever(semantic_weight=1.1)


if __name__ == "__main__":
    unittest.main()
