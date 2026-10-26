import unittest
import tempfile
from pathlib import Path

from ai_company_os import BatchScheduler, CodexAdapter


class CodexIndependentQaReviewTests(unittest.TestCase):
    @staticmethod
    def _completed_scheduler(*, dependent=False):
        scheduler = BatchScheduler(run_id="qa-run")
        scheduler.add("实现客户导入", task_id="T1", project="crm")
        if dependent:
            scheduler.add("编写客户导入说明", task_id="T2", project="crm", depends_on=["T1"])
        scheduler.mark_running("T1")
        scheduler.mark_done(
            "T1",
            result={
                "summary": "导入流程已实现",
                "evidence": ["测试覆盖 CSV 导入"],
                "artifact_refs": ["src/import.py", "reports/import-tests.xml"],
            },
            model="worker-model",
        )
        return scheduler

    def test_request_spawns_independent_reviewer_and_holds_downstream_tasks(self):
        spawned = []

        def spawn(prompt, metadata):
            spawned.append((prompt, metadata))
            return {"status": "accepted", "thread_id": "qa-thread", "run_id": "qa-host-run"}

        scheduler = self._completed_scheduler(dependent=True)
        adapter = CodexAdapter(supervisor_id="PM-1", spawn_subagent=spawn, available_tools=["filesystem", "browser", "search"])

        request = adapter.request_qa_review(scheduler, "T1")

        prompt, metadata = spawned[0]
        self.assertEqual(request["status"], "accepted")
        self.assertEqual(request["task"]["status"], "qa_review")
        self.assertEqual(request["review_id"], "qa-run:T1:qa:1")
        self.assertEqual(metadata["agent_kind"], "qa")
        self.assertTrue(metadata["independent_review"])
        self.assertNotEqual(metadata["agent_id"], "ENG-001")
        self.assertNotEqual(metadata["independent_of_agent_id"], metadata["agent_id"])
        self.assertEqual(metadata["isolation"], "isolated_thread")
        self.assertIn("review-and-critique", metadata["skills"])
        self.assertIn("reports/import-tests.xml", prompt)
        self.assertIn("acceptance_gates", prompt)
        self.assertEqual(scheduler.dispatch_ready(), [])

    def test_passed_review_records_evidence_and_unlocks_dependent_task(self):
        scheduler = self._completed_scheduler(dependent=True)
        adapter = CodexAdapter(spawn_subagent=lambda *_: {"status": "accepted", "thread_id": "qa-thread"})
        request = adapter.request_qa_review(scheduler, "T1")

        reviewed = adapter.complete_qa_review(
            scheduler,
            "T1",
            {
                "status": "completed",
                "run_id": "review-run-1",
                "model": "qa-model",
                "result": {
                    "status": "passed",
                    "reason": "验收标准均有对应测试证据",
                    "evidence_refs": ["reports/import-tests.xml"],
                },
            },
            review_id=request["review_id"],
        )

        self.assertEqual(reviewed["status"], "done")
        self.assertEqual(reviewed["qa"]["status"], "passed")
        self.assertEqual(reviewed["qa"]["model"], "qa-model")
        self.assertEqual(reviewed["qa_history"][0]["host_run_id"], "review-run-1")
        self.assertEqual(scheduler.dispatch_ready()[0]["task_id"], "T2")

    def test_rework_review_requeues_original_task_not_its_dependents(self):
        scheduler = self._completed_scheduler(dependent=True)
        adapter = CodexAdapter(spawn_subagent=lambda *_: {"status": "accepted", "thread_id": "qa-thread"})
        request = adapter.request_qa_review(scheduler, "T1")

        reviewed = adapter.complete_qa_review(
            scheduler,
            "T1",
            {"result": {"status": "rework_required", "reason": "缺少重复行处理测试", "evidence_refs": ["reports/gap.md"]}},
            review_id=request["review_id"],
        )

        self.assertEqual(reviewed["status"], "review")
        self.assertEqual([item["task_id"] for item in scheduler.dispatch_ready()], ["T1"])
        self.assertEqual(scheduler.snapshot("T2")["status"], "waiting_dependency")

    def test_missing_reviewer_callback_keeps_task_done_and_marks_qa_waiting(self):
        scheduler = self._completed_scheduler()

        result = CodexAdapter().request_qa_review(scheduler, "T1")

        self.assertEqual(result["status"], "queued")
        self.assertEqual(scheduler.snapshot("T1")["status"], "done")
        self.assertEqual(scheduler.overview()["awaiting_qa"], ["T1"])

    def test_dispatch_exception_releases_task_and_retry_reuses_review_id(self):
        calls = []

        def spawn(_prompt, metadata):
            calls.append(metadata["idempotency_key"])
            if len(calls) == 1:
                raise TimeoutError("host acknowledgement lost")
            return {"status": "accepted", "thread_id": "qa-thread"}

        scheduler = self._completed_scheduler()
        adapter = CodexAdapter(spawn_subagent=spawn)

        failed = adapter.request_qa_review(scheduler, "T1")
        retried = adapter.request_qa_review(scheduler, "T1")

        self.assertEqual(failed["status"], "host_error")
        self.assertEqual(failed["task"]["status"], "done")
        self.assertEqual(retried["status"], "accepted")
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(retried["review_id"], calls[0])

    def test_stale_qa_result_is_rejected(self):
        scheduler = self._completed_scheduler()
        adapter = CodexAdapter(spawn_subagent=lambda *_: {"status": "accepted"})
        adapter.request_qa_review(scheduler, "T1")

        with self.assertRaises(ValueError):
            adapter.complete_qa_review(
                scheduler, "T1", {"result": {"status": "passed"}}, review_id="old-review-id",
            )

        self.assertEqual(scheduler.snapshot("T1")["status"], "qa_review")

    def test_pass_without_evidence_is_not_released_as_a_pass(self):
        scheduler = self._completed_scheduler()
        adapter = CodexAdapter(spawn_subagent=lambda *_: {"status": "accepted", "thread_id": "qa-thread"})
        request = adapter.request_qa_review(scheduler, "T1")

        result = adapter.complete_qa_review(
            scheduler,
            "T1",
            {"result": {"status": "passed", "reason": "看起来没问题", "evidence_refs": []}},
            review_id=request["review_id"],
        )

        self.assertEqual(result["status"], "invalid_result")
        self.assertEqual(result["task"]["status"], "done")
        self.assertEqual(result["task"]["qa"]["status"], "not_run")
        self.assertIn("evidence_refs", result["task"]["qa_dispatch_error"])
        self.assertEqual(scheduler.overview()["awaiting_qa"], ["T1"])

    def test_pause_resume_preserves_inflight_review_and_id(self):
        scheduler = self._completed_scheduler()
        adapter = CodexAdapter(spawn_subagent=lambda *_: {"status": "accepted", "thread_id": "qa-thread"})
        request = adapter.request_qa_review(scheduler, "T1")
        scheduler.pause("T1", reason="用户暂停")

        paused = scheduler.resume("T1")

        self.assertEqual(paused["status"], "qa_review")
        self.assertEqual(paused["qa_review_id"], request["review_id"])
        self.assertEqual(scheduler.overview()["qa_in_progress"], ["T1"])

    def test_inflight_review_survives_restart_and_redelivery_reuses_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "batch.json"
            scheduler = BatchScheduler(run_id="durable-qa", state_path=state_path)
            scheduler.add("实现客户导入", task_id="T1", project="crm")
            scheduler.mark_running("T1")
            scheduler.mark_done("T1", result={"summary": "已实现", "artifact_refs": ["src/import.py"]})
            first = CodexAdapter(spawn_subagent=lambda *_: {"status": "accepted", "thread_id": "qa-1"})
            original = first.request_qa_review(scheduler, "T1")

            restored = BatchScheduler.restore(state_path)
            calls = []
            retrier = CodexAdapter(spawn_subagent=lambda _prompt, metadata: calls.append(metadata["idempotency_key"]) or {"status": "accepted", "thread_id": "qa-1"})
            retried = retrier.request_qa_review(restored, "T1")

            self.assertEqual(restored.overview()["qa_in_progress"], ["T1"])
            self.assertEqual(original["review_id"], retried["review_id"])
            self.assertEqual(calls, [original["review_id"]])


if __name__ == "__main__":
    unittest.main()
