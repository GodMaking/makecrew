import json
import tempfile
import unittest
from pathlib import Path

from ai_company_os.batch import BatchScheduler


class BatchPersistenceTests(unittest.TestCase):
    def test_restore_recovers_running_task_as_waiting_host_and_keeps_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "batch-state.json"
            trace_path = Path(directory) / "batch-trace.jsonl"
            scheduler = BatchScheduler(run_id="batch-restore", state_path=state_path)
            scheduler.add("先完成设计", task_id="T1", project="demo")
            scheduler.add(
                "依赖设计的实现",
                task_id="T2",
                project="demo",
                parent_task_id="T1",
                depends_on=["T1"],
            )
            scheduler.ready()
            scheduler.mark_running("T1")

            restored = BatchScheduler.restore(state_path, trace_path=trace_path)

            self.assertEqual(restored.run_id, "batch-restore")
            self.assertEqual(restored.snapshot("T1")["status"], "waiting_host")
            self.assertEqual(restored.snapshot("T1")["attempt"], 1)
            self.assertEqual(restored.snapshot("T2")["status"], "waiting_dependency")
            self.assertEqual(restored.snapshot("T2")["parent_task_id"], "T1")
            self.assertEqual(restored.snapshot("T1")["task_packet"]["idempotency_key"], "batch-restore:T1")
            events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(event["event_type"] == "task_interrupted_on_restore" for event in events))

    def test_restart_retry_reuses_idempotency_key_and_persists_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "batch-state.json"
            trace_path = Path(directory) / "batch-trace.jsonl"
            host_calls = []
            accepted_dispatch_keys = set()
            executed_side_effects = []

            def open_thread(_employee_id, _project, _role):
                return {"thread_id": "worker-thread", "reused": True}

            def dispatch(thread_id, task_packet):
                key = task_packet["idempotency_key"]
                host_calls.append((thread_id, key))
                if key not in accepted_dispatch_keys:
                    accepted_dispatch_keys.add(key)
                    executed_side_effects.append(key)
                return {
                    "status": "accepted",
                    "thread_id": thread_id,
                    "run_id": "host-run-1",
                    "model": "model-fixture",
                }

            first = BatchScheduler(
                run_id="batch-retry",
                state_path=state_path,
                trace_path=trace_path,
                thread_adapter=open_thread,
                agent_dispatcher=dispatch,
            )
            first.add("执行一次有外部副作用的任务", task_id="T1", project="demo")
            first_dispatch = first.dispatch_ready()[0]
            persisted_during_dispatch = json.loads(state_path.read_text(encoding="utf-8"))
            persisted_task = next(item for item in persisted_during_dispatch["tasks"] if item["task_id"] == "T1")
            self.assertEqual(persisted_task["status"], "running")
            self.assertEqual(persisted_task["task_packet"]["idempotency_key"], "batch-retry:T1")

            # Simulate process loss after host acceptance, before the employee result returns.
            restored = BatchScheduler.restore(
                state_path,
                thread_adapter=open_thread,
                agent_dispatcher=dispatch,
            )
            self.assertEqual(restored.snapshot("T1")["status"], "waiting_host")
            self.assertEqual(restored.snapshot("T1")["thread_id"], "worker-thread")

            retry_dispatch = restored.dispatch_ready()[0]
            restored.mark_done(
                "T1",
                result={"summary": "恢复后完成", "artifact_refs": ["reports/result.json"]},
                usage={"tool_calls": 2},
            )
            restored.record_qa("T1", status="passed", agent_id="QA-001", evidence_refs=["reports/qa.json"])
            verified = BatchScheduler.restore(state_path)

            self.assertEqual(first_dispatch["idempotency_key"], retry_dispatch["idempotency_key"])
            self.assertEqual(len(host_calls), 2)
            self.assertEqual(host_calls[0], host_calls[1])
            self.assertEqual(len(executed_side_effects), 1)
            self.assertEqual(retry_dispatch["status"], "running")
            self.assertEqual(verified.snapshot("T1")["status"], "done")
            self.assertEqual(verified.snapshot("T1")["attempt"], 2)
            self.assertEqual(verified.snapshot("T1")["result"]["summary"], "恢复后完成")
            self.assertEqual(verified.snapshot("T1")["usage"]["tool_calls"], 2)
            self.assertEqual(verified.snapshot("T1")["qa"]["status"], "passed")
            self.assertEqual(verified.snapshot("T1")["qa"]["evidence_refs"], ["reports/qa.json"])
            self.assertEqual(verified.dispatch_ready(), [])

    def test_existing_state_path_requires_explicit_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "batch-state.json"
            BatchScheduler(state_path=state_path).add("已保存任务", task_id="T1")

            with self.assertRaisesRegex(FileExistsError, "restore"):
                BatchScheduler(state_path=state_path)

    def test_qa_rework_state_and_review_history_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "batch-state.json"
            scheduler = BatchScheduler(state_path=state_path, max_qa_reworks=1)
            scheduler.add("实现后等待质量复核", task_id="T1")
            scheduler.dispatch_ready()
            scheduler.mark_done("T1", result={"summary": "初稿"})
            scheduler.record_qa(
                "T1", status="rework_required", reason="缺少边界用例", agent_id="QA-001",
            )

            restored = BatchScheduler.restore(state_path)

            self.assertEqual(restored.max_qa_reworks, 1)
            self.assertEqual(restored.snapshot("T1")["status"], "review")
            self.assertEqual(restored.snapshot("T1")["qa_rework_count"], 1)
            self.assertEqual(restored.snapshot("T1")["qa_history"][0]["reason"], "缺少边界用例")
            self.assertEqual(restored.dispatch_ready()[0]["status"], "running")

    def test_legacy_state_defaults_new_qa_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "legacy-state.json"
            BatchScheduler(state_path=state_path).add("旧批次任务", task_id="T1")
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            payload.pop("max_qa_reworks")
            payload["tasks"][0].pop("qa_history")
            payload["tasks"][0].pop("qa_rework_count")
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            restored = BatchScheduler.restore(state_path)

            self.assertEqual(restored.max_qa_reworks, 2)
            self.assertEqual(restored.snapshot("T1")["qa_history"], [])
            self.assertEqual(restored.snapshot("T1")["qa_rework_count"], 0)

    def test_legacy_rework_verdict_is_migrated_into_resumable_review(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "legacy-review.json"
            scheduler = BatchScheduler(state_path=state_path)
            scheduler.add("待返工任务", task_id="T1")
            scheduler.dispatch_ready()
            scheduler.mark_done("T1", result={"summary": "初稿"})
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            payload.pop("max_qa_reworks")
            record = payload["tasks"][0]
            record["qa"] = {
                "status": "rework_required", "reason": "旧版 QA 驳回", "agent_id": "QA-001",
                "model": "", "evidence_refs": ["qa.json"],
            }
            record["status"] = "done"
            record.pop("qa_history")
            record.pop("qa_rework_count")
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            restored = BatchScheduler.restore(state_path)

            self.assertEqual(restored.snapshot("T1")["status"], "review")
            self.assertEqual(restored.snapshot("T1")["qa_rework_count"], 1)
            self.assertEqual(restored.snapshot("T1")["qa_history"][0]["reason"], "旧版 QA 驳回")

    def test_restore_rejects_corrupt_or_unsupported_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "batch-state.json"
            state_path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "状态文件"):
                BatchScheduler.restore(state_path)

            state_path.write_text(json.dumps({"version": 99, "tasks": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "版本"):
                BatchScheduler.restore(state_path)

            state_path.write_text(json.dumps({"version": True, "tasks": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "版本"):
                BatchScheduler.restore(state_path)

            valid_path = Path(directory) / "valid-state.json"
            BatchScheduler(state_path=valid_path).add("任务", task_id="T1")
            valid_payload = json.loads(valid_path.read_text(encoding="utf-8"))
            valid_payload["tasks"][0]["status"] = "unknown-state"
            valid_path.write_text(json.dumps(valid_payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "任务结构无效"):
                BatchScheduler.restore(valid_path)

            valid_payload["tasks"][0]["status"] = "pending"
            valid_payload["tasks"][0]["budget"]["tool_calls"] = True
            valid_path.write_text(json.dumps(valid_payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "任务计数无效"):
                BatchScheduler.restore(valid_path)


if __name__ == "__main__":
    unittest.main()
