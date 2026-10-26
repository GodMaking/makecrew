import unittest

from ai_company_os.batch import BatchScheduler


class BatchSchedulerQaReworkTests(unittest.TestCase):
    def test_rework_verdict_requeues_task_and_keeps_review_history(self):
        scheduler = BatchScheduler(run_id="qa-rework", max_qa_reworks=1)
        scheduler.add("实现登录接口", task_id="T1", project="crm")
        scheduler.add("编写登录接口文档", task_id="T2", project="crm", depends_on=["T1"])
        first_dispatch = scheduler.dispatch_ready()[0]
        scheduler.mark_done("T1", result={"summary": "初稿"})
        self.assertEqual(scheduler.overview()["awaiting_qa"], ["T1"])

        rejected = scheduler.record_qa(
            "T1", status="rework_required", reason="缺少权限边界测试", agent_id="QA-001",
            evidence_refs=["reports/review-1.json"],
        )

        self.assertEqual(rejected["status"], "review")
        self.assertEqual(rejected["qa_rework_count"], 1)
        self.assertIn("T1", scheduler.aggregate_results()["pending_task_ids"])
        retry_dispatches = scheduler.dispatch_ready()
        self.assertEqual([item["task_id"] for item in retry_dispatches], ["T1"])
        retry_dispatch = retry_dispatches[0]
        self.assertEqual(scheduler.snapshot("T2")["status"], "waiting_dependency")
        self.assertEqual(retry_dispatch["status"], "running")
        self.assertEqual(scheduler.snapshot("T1")["attempt"], 2)
        self.assertEqual(retry_dispatch["idempotency_key"], first_dispatch["idempotency_key"])

        scheduler.mark_done("T1", result={"summary": "补充测试后的版本"})
        self.assertEqual(scheduler.overview()["awaiting_qa"], ["T1"])
        passed = scheduler.record_qa(
            "T1", status="passed", agent_id="QA-001", evidence_refs=["reports/review-2.json"],
        )

        self.assertEqual(passed["status"], "done")
        self.assertEqual(passed["qa"]["status"], "passed")
        self.assertEqual(scheduler.overview()["awaiting_qa"], [])
        self.assertEqual([item["status"] for item in passed["qa_history"]], ["rework_required", "passed"])
        self.assertEqual(scheduler.dispatch_ready()[0]["task_id"], "T2")

    def test_blocked_verdict_waits_for_explicit_resume(self):
        scheduler = BatchScheduler()
        scheduler.add("交付需客户确认的接口", task_id="T1")
        scheduler.dispatch_ready()
        scheduler.mark_done("T1", result={"summary": "已实现"})

        blocked = scheduler.record_qa(
            "T1", status="blocked", reason="待客户确认接口契约", agent_id="QA-001",
        )

        self.assertEqual(blocked["status"], "blocked_qa")
        self.assertEqual(scheduler.dispatch_ready(), [])
        resumed = scheduler.resume("T1")
        self.assertEqual(resumed["status"], "pending")
        self.assertEqual(scheduler.dispatch_ready()[0]["status"], "running")

    def test_rework_cap_routes_exhausted_task_to_blocked_qa(self):
        scheduler = BatchScheduler(max_qa_reworks=0)
        scheduler.add("修复数据导出", task_id="T1")
        scheduler.dispatch_ready()
        scheduler.mark_done("T1", result={"summary": "初稿"})

        blocked = scheduler.record_qa(
            "T1", status="rework_required", reason="缺少字段映射证据", agent_id="QA-001",
        )

        self.assertEqual(blocked["status"], "blocked_qa")
        self.assertEqual(blocked["qa_rework_count"], 1)
        self.assertEqual(scheduler.dispatch_ready(), [])

    def test_qa_verdict_requires_a_completed_employee_result(self):
        scheduler = BatchScheduler()
        scheduler.add("生成接口契约", task_id="T1")
        scheduler.dispatch_ready()

        with self.assertRaisesRegex(ValueError, "任务结果完成后"):
            scheduler.record_qa("T1", status="passed", agent_id="QA-001")


if __name__ == "__main__":
    unittest.main()
