import unittest

from ai_company_os import BatchScheduler, CodexAdapter
from ai_company_os.bootstrap_cli import main


class CodexAdapterTests(unittest.TestCase):
    def test_audit_reports_unwired_native_callbacks(self):
        adapter = CodexAdapter(supervisor_id="PM-DEMO")

        report = adapter.audit(max_concurrency=4)

        self.assertFalse(report["ready"])
        self.assertEqual(report["missing"], ["spawn_subagent", "send_to_thread"])
        self.assertTrue(report["warnings"])

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


if __name__ == "__main__":
    unittest.main()
