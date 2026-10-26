import json
import tempfile
import unittest
from pathlib import Path

from ai_company_os import BatchScheduler, CeoContinuityManager, CodexAdapter
from ai_company_os.bootstrap_cli import main
from ai_company_os.checkpoint import JsonCheckpointStore, RetryPolicy


class CodexAdapterTests(unittest.TestCase):
    @staticmethod
    def _ceo_snapshot():
        return {
            "company_memory_ref": ".makecrew/company-memory.md",
            "portfolio": [{"project_id": "P1"}],
            "open_tasks": [{"task_id": "T1"}],
            "active_decisions": [{"decision_id": "D1"}],
            "employee_status": [],
            "risks": [{"risk_id": "R1", "impact": "high"}],
            "budgets": [],
            "next_actions": [],
            "evidence_refs": [],
        }

    def test_wildcard_tool_policy_resolves_to_real_host_inventory(self):
        spawned = []

        def spawn(prompt, metadata):
            spawned.append((prompt, metadata))
            return {"status": "accepted", "thread_id": "pm-thread"}

        adapter = CodexAdapter(
            spawn_subagent=spawn,
            available_tools=["filesystem", "browser", "github", "imagegen"],
        )
        packet = {
            "task": "规划产品",
            "project": "demo",
            "employee": {"agent_id": "PM-PRODUCT-001", "role": "产品经理", "tools": ["*"]},
            "tool_policy": {"mode": "all_enabled_host_tools", "tools": ["*"], "requires_runtime_inventory": True},
        }

        result = adapter.dispatch("", packet)

        self.assertEqual(result["thread_id"], "pm-thread")
        self.assertEqual(spawned[0][1]["tools"], ["browser", "filesystem", "github", "imagegen"])
        self.assertEqual(spawned[0][1]["tool_policy"]["mode"], "all_enabled_host_tools")
        self.assertIn("枚举宿主本轮实际启用的工具", spawned[0][0])

    def test_audit_reports_unwired_native_callbacks(self):
        adapter = CodexAdapter(supervisor_id="PM-DEMO")

        report = adapter.audit(max_concurrency=4)

        self.assertFalse(report["ready"])
        self.assertEqual(report["missing"], ["spawn_subagent", "send_to_thread"])
        self.assertTrue(report["warnings"])
        self.assertFalse(report["quality_review"]["ready"])

    def test_missing_spawn_callback_leaves_task_waiting_for_host(self):
        adapter = CodexAdapter(send_to_thread=lambda thread_id, prompt: {"status": "accepted"})
        scheduler = BatchScheduler(
            thread_adapter=adapter.open_employee_thread,
            agent_dispatcher=adapter.dispatch,
        )
        scheduler.add("修复登录页面", task_id="T1", project="demo")

        dispatch = scheduler.dispatch_ready()[0]

        self.assertEqual(dispatch["status"], "waiting_host")
        self.assertEqual(scheduler.snapshot("T1")["status"], "waiting_host")

        completed = scheduler.mark_done("T1", result={"summary": "宿主稍后回传完成"})
        self.assertEqual(completed["status"], "done")

    def test_codex_audit_cli_is_machine_readable(self):
        self.assertEqual(main(["codex-audit", "--supervisor-id", "PM-DEMO"]), 0)

    def test_dispatch_spawns_employee_and_scheduler_keeps_thread_id(self):
        spawned = []

        def spawn(prompt, metadata):
            spawned.append((prompt, metadata))
            return {"status": "accepted", "thread_id": "codex-child-1", "agent_id": "ENG-CHILD-1"}

        adapter = CodexAdapter(supervisor_id="PM-DEMO", spawn_subagent=spawn)
        scheduler = BatchScheduler(
            supervisor_id="PM-DEMO",
            thread_adapter=adapter.open_employee_thread,
            agent_dispatcher=adapter.dispatch,
        )
        scheduler.add("修复登录页面", task_id="T1", project="demo", file_scope=["src/login.tsx"])

        dispatch = scheduler.dispatch_ready()[0]

        self.assertEqual(dispatch["thread_id"], "codex-child-1")
        self.assertEqual(dispatch["host_dispatch"]["agent_id"], "ENG-CHILD-1")
        self.assertEqual(spawned[0][1]["agent_kind"], "employee")
        self.assertEqual(spawned[0][1]["supervisor_id"], "PM-DEMO")
        self.assertIn("summary、evidence、risks、next_steps", spawned[0][0])

    def test_existing_employee_thread_receives_delta_without_spawning(self):
        sent = []

        def send(thread_id, prompt):
            sent.append((thread_id, prompt))
            return {"status": "accepted", "run_id": "run-2"}

        adapter = CodexAdapter(supervisor_id="PM-DEMO", send_to_thread=send)
        adapter.register_employee(employee_id="ENG-001", project="demo", thread_id="codex-existing")
        scheduler = BatchScheduler(
            supervisor_id="PM-DEMO",
            thread_adapter=adapter.open_employee_thread,
            agent_dispatcher=adapter.dispatch,
        )
        scheduler.add("补登录测试", task_id="T1", project="demo")

        dispatch = scheduler.dispatch_ready()[0]

        self.assertEqual(dispatch["thread_id"], "codex-existing")
        self.assertEqual(sent[0][0], "codex-existing")
        self.assertEqual(dispatch["host_dispatch"]["run_id"], "run-2")

        scheduler.mark_done("T1", result={"summary": "完成测试"})
        scheduler.add("继续登录测试", task_id="T2", project="demo")
        follow_up = scheduler.dispatch_ready()[0]
        self.assertEqual(follow_up["thread_id"], "codex-existing")
        self.assertTrue(follow_up["thread_reused"])

    def test_codex_host_envelope_preserves_model_run_and_artifact_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "run.jsonl"

            def spawn(_prompt, metadata):
                return {
                    "status": "accepted",
                    "thread_id": "codex-worker-1",
                    "agent_id": metadata["agent_id"],
                    "run_id": "host-run-1",
                    "model": "codex-model-fixture",
                }

            adapter = CodexAdapter(spawn_subagent=spawn)
            scheduler = BatchScheduler(
                supervisor_id="PM-TEST",
                run_id="batch-1",
                trace_path=trace_path,
                thread_adapter=adapter.open_employee_thread,
                agent_dispatcher=adapter.dispatch,
            )
            scheduler.add("实现并验收", task_id="T1", project="demo")

            dispatch = scheduler.dispatch_ready()[0]
            completed = adapter.complete(
                scheduler,
                "T1",
                {
                    "status": "completed",
                    "run_id": "host-run-complete",
                    "model": "codex-model-fixture",
                    "result": {
                        "summary": "验收通过",
                        "evidence": ["reports/test.json"],
                        "artifact_refs": ["dist/app.zip"],
                    },
                },
                usage={"tool_calls": 3},
            )

            events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            host_dispatch = next(event for event in events if event["event_type"] == "host_dispatch_result")
            task_complete = next(event for event in events if event["event_type"] == "task_completed")
            self.assertEqual(dispatch["host_dispatch"]["run_id"], "host-run-1")
            self.assertEqual(host_dispatch["host_run_id"], "host-run-1")
            self.assertEqual(host_dispatch["model"], "codex-model-fixture")
            self.assertEqual(task_complete["model"], "codex-model-fixture")
            self.assertEqual(task_complete["artifact_refs"], ["dist/app.zip"])
            self.assertEqual(completed["usage"]["tool_calls"], 3)

    def test_transient_host_interruption_retries_same_task_and_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "run.jsonl"
            checkpoint_path = Path(directory) / "checkpoints.json"
            sent = []
            accepted_dispatch_keys = set()
            executed_side_effects = []

            def send(thread_id, prompt):
                sent.append((thread_id, prompt))
                marker = '"idempotency_key":"'
                if marker not in prompt:
                    raise AssertionError("dispatch prompt lacks an idempotency key")
                dispatch_key = prompt.split(marker, 1)[1].split('"', 1)[0]
                if dispatch_key not in accepted_dispatch_keys:
                    accepted_dispatch_keys.add(dispatch_key)
                    executed_side_effects.append(dispatch_key)
                    raise TimeoutError("fixture host interruption")
                return {"status": "accepted", "run_id": "host-run-retry", "model": "codex-model-fixture"}

            adapter = CodexAdapter(send_to_thread=send)
            adapter.register_employee(employee_id="ENG-001", project="demo", thread_id="codex-worker")
            scheduler = BatchScheduler(
                supervisor_id="PM-TEST",
                run_id="batch-retry",
                trace_path=trace_path,
                thread_adapter=adapter.open_employee_thread,
                agent_dispatcher=adapter.dispatch,
            )
            scheduler.add("修复并验证", task_id="T1", project="demo")

            with self.assertRaisesRegex(TimeoutError, "fixture host interruption"):
                scheduler.dispatch_ready()

            interrupted = scheduler.snapshot("T1")
            checkpoint = JsonCheckpointStore(checkpoint_path).save(
                "T1",
                "dispatch",
                {
                    "run_id": interrupted["run_id"],
                    "attempt": interrupted["attempt"],
                    "status": interrupted["status"],
                    "thread_id": interrupted["thread_id"],
                },
                idempotency_key="T1:dispatch:1",
            )
            restored = JsonCheckpointStore(checkpoint_path).load_latest("T1")
            retry = RetryPolicy(max_attempts=2).decision(attempt=1, retryable=True)

            self.assertEqual(checkpoint["state"]["status"], "waiting_host")
            self.assertEqual(restored["state"]["attempt"], 1)
            self.assertEqual(retry["action"], "retry")
            self.assertEqual(retry["resume_from"], "last_checkpoint")
            self.assertEqual(RetryPolicy(max_attempts=2).decision(attempt=2, retryable=True)["action"], "stop")

            dispatched = scheduler.dispatch_ready()[0]
            completed = adapter.complete(
                scheduler,
                "T1",
                {
                    "status": "completed",
                    "run_id": "host-run-result",
                    "model": "codex-model-fixture",
                    "result": {"summary": "恢复后完成", "artifact_refs": ["reports/fix.txt"]},
                },
            )

            events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            starts = [event for event in events if event["event_type"] == "task_started"]
            self.assertEqual(len(sent), 2)
            self.assertEqual(len(executed_side_effects), 1)
            self.assertEqual(sent[0][0], sent[1][0])
            self.assertEqual(sent[0][1], sent[1][1])
            self.assertIn('"idempotency_key":"batch-retry:T1"', sent[0][1])
            self.assertEqual([event["attempt"] for event in starts], [1, 2])
            self.assertEqual(dispatched["thread_id"], "codex-worker")
            self.assertEqual(completed["status"], "done")
            self.assertEqual(completed["artifact_refs"], ["reports/fix.txt"])

    def test_isolated_task_always_spawns_a_new_employee_thread(self):
        spawned = []

        def spawn(prompt, metadata):
            spawned.append(metadata)
            return {"status": "accepted", "thread_id": f"isolated-{len(spawned)}"}

        adapter = CodexAdapter(spawn_subagent=spawn)
        scheduler = BatchScheduler(
            thread_adapter=adapter.open_employee_thread,
            agent_dispatcher=adapter.dispatch,
        )
        scheduler.add("修复登录页面", task_id="T1", project="demo", isolated_thread=True)
        scheduler.add("补登录测试", task_id="T2", project="demo", isolated_thread=True)

        dispatches = scheduler.dispatch_ready()

        self.assertEqual([item["thread_id"] for item in dispatches], ["isolated-1", "isolated-2"])
        self.assertTrue(all(item["isolation"] == "isolated_worktree" for item in [d["task_packet"] for d in dispatches]))

    def test_complete_and_summarize_only_send_compact_results(self):
        sent = []

        def send(thread_id, prompt):
            sent.append((thread_id, prompt))
            return {"status": "accepted"}

        adapter = CodexAdapter(supervisor_id="PM-DEMO", supervisor_thread_id="codex-pm", send_to_thread=send)
        scheduler = BatchScheduler(supervisor_id="PM-DEMO")
        scheduler.add("研究用户", task_id="T1", project="demo")
        scheduler.dispatch_ready()
        adapter.complete(scheduler, "T1", {"summary": "完成画像", "evidence": ["research.md"]})

        result = adapter.summarize(scheduler)

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(sent[0][0], "codex-pm")
        self.assertIn("完成画像", sent[0][1])
        self.assertNotIn("完整历史", sent[0][1])

    def test_failed_host_result_is_recorded_as_failed(self):
        adapter = CodexAdapter()
        scheduler = BatchScheduler()
        scheduler.add("研究用户", task_id="T1", project="demo")
        scheduler.dispatch_ready()

        result = adapter.complete(scheduler, "T1", {"status": "failed", "error": "线程超时"})

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "线程超时")

    def test_ceo_rollover_uses_verified_host_thread_and_archives_old(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CeoContinuityManager(directory)
            pinned = []
            archived = []

            def send(thread_id, prompt):
                handoff = manager._read_handoff(manager.status()["pending_handoff"]["handoff_id"])
                return {"verification": {
                    "project_ids": ["P1"],
                    "task_ids": ["T1"],
                    "decision_ids": ["D1"],
                    "risk_ids": ["R1"],
                    "handoff_digest": handoff["digest"],
                }}

            adapter = CodexAdapter(
                supervisor_id="CEO-001",
                supervisor_thread_id="ceo-old",
                open_supervisor_thread=lambda ceo_id, metadata: {"thread_id": "ceo-new"},
                send_to_thread=send,
                set_thread_pinned=lambda thread_id, value: pinned.append((thread_id, value)),
                set_thread_archived=lambda thread_id, value: archived.append((thread_id, value)),
            )

            result = adapter.rollover_ceo(manager, self._ceo_snapshot())

            self.assertEqual(result["status"], "activated")
            self.assertEqual(manager.status()["active_thread_id"], "ceo-new")
            self.assertEqual(pinned, [("ceo-new", True), ("ceo-old", False)])
            self.assertEqual(archived, [("ceo-old", True)])
            self.assertEqual(adapter.supervisor_thread_id, "ceo-new")

    def test_ceo_rollover_callback_failure_keeps_old_active_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CeoContinuityManager(directory)

            def send(thread_id, prompt):
                handoff = manager._read_handoff(manager.status()["pending_handoff"]["handoff_id"])
                return {"verification": {
                    "project_ids": ["P1"], "task_ids": ["T1"], "decision_ids": ["D1"],
                    "risk_ids": ["R1"], "handoff_digest": handoff["digest"],
                }}

            def archive_fails(thread_id, value):
                raise RuntimeError("host archive failed")

            adapter = CodexAdapter(
                supervisor_id="CEO-001",
                supervisor_thread_id="ceo-old",
                open_supervisor_thread=lambda ceo_id, metadata: {"thread_id": "ceo-new"},
                send_to_thread=send,
                set_thread_pinned=lambda thread_id, value: None,
                set_thread_archived=archive_fails,
            )

            with self.assertRaisesRegex(RuntimeError, "archive failed"):
                adapter.rollover_ceo(manager, self._ceo_snapshot())
            self.assertEqual(manager.status()["active_thread_id"], "ceo-old")

    def test_ceo_rollover_retry_reuses_pending_candidate_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CeoContinuityManager(directory)
            opened = []
            response_count = 0

            def open_supervisor(ceo_id, metadata):
                opened.append(metadata)
                return {"thread_id": "ceo-new"}

            def send(thread_id, prompt):
                nonlocal response_count
                response_count += 1
                if response_count == 1:
                    return {"status": "accepted"}
                handoff = manager._read_handoff(manager.status()["pending_handoff"]["handoff_id"])
                return {"verification": {
                    "project_ids": ["P1"], "task_ids": ["T1"], "decision_ids": ["D1"],
                    "risk_ids": ["R1"], "handoff_digest": handoff["digest"],
                }}

            adapter = CodexAdapter(
                supervisor_id="CEO-001",
                supervisor_thread_id="ceo-old",
                open_supervisor_thread=open_supervisor,
                send_to_thread=send,
                set_thread_pinned=lambda thread_id, value: None,
                set_thread_archived=lambda thread_id, value: None,
            )

            first = adapter.rollover_ceo(manager, self._ceo_snapshot())
            second = adapter.rollover_ceo(manager, self._ceo_snapshot())

            self.assertEqual(first["status"], "awaiting_candidate_verification")
            self.assertEqual(second["status"], "activated")
            self.assertEqual(len(opened), 1)


if __name__ == "__main__":
    unittest.main()
