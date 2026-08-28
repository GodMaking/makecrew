import unittest
import threading
import tempfile
import json
from pathlib import Path
import urllib.request
from urllib.parse import quote

from ai_company_os.router import route_task
from ai_company_os.task_state import TaskLedger, TaskStatus
from ai_company_os.learning import LearningEngine, ProposalStatus
from ai_company_os.bootstrap import initialize_workspace, audit_tools, register_employee
from ai_company_os.web import render_result
from ai_company_os.web import Handler
from http.server import ThreadingHTTPServer
from ai_company_os.orchestrator import CrewOrchestrator


class RouteTaskTests(unittest.TestCase):
    def test_assignment_includes_capability_contract(self):
        result = route_task("开发网站并准备上线")

        assignment = result["assignments"][0]
        self.assertIn("employee_id", assignment)
        self.assertIn("required_skills", assignment)
        self.assertIn("tools", assignment)
        self.assertEqual(assignment["status"], "active")
        self.assertEqual(assignment["kind"], "specialist_template")

    def test_route_exposes_project_memory_and_execution_policy(self):
        result = route_task("开发网站", project="demo-site")

        self.assertEqual(result["project_memory"], "demo-site")
        self.assertEqual(result["execution_policy"]["resume_on_restart"], True)
        self.assertIn("approval_required_for", result["execution_policy"])
        self.assertEqual(result["core_roles"], ["CEO", "项目主管", "验收员"])
        self.assertEqual(result["verification_contract"]["employee_id"], "QA-001")

    def test_single_specialist_task_routes_directly(self):
        result = route_task("修复登录页面的表单校验")

        self.assertEqual(result["route"], "direct_worker")
        self.assertEqual(result["lead"], "工程员工")
        self.assertEqual(result["parallel_tasks"], [])
        self.assertIn("构建或测试结果", result["acceptance_gates"])

    def test_skill_task_routes_to_skill_employee(self):
        result = route_task("制作一个可复用的 Skill，并验证 SKILL.md 的触发条件")

        self.assertEqual(result["route"], "direct_worker")
        self.assertEqual(result["lead"], "Skill员工")
        self.assertEqual(result["assignments"][0]["employee_id"], "SKL-001")
        self.assertIn("SKILL.md 可加载、触发条件和最小任务验证", result["acceptance_gates"])

    def test_skill_worker_contract_is_available(self):
        self.assertTrue(Path(__file__).parents[1].joinpath("roles", "skill-worker.md").exists())

    def test_multi_role_project_routes_to_project_lead(self):
        result = route_task("开发网站并准备上线，同时研究用户并写宣传文案")

        self.assertEqual(result["route"], "project_lead")
        self.assertEqual(result["lead"], "项目主管")
        self.assertGreaterEqual(len(result["parallel_tasks"]), 3)
        self.assertLess(result["budget"]["max_rounds"], 20)

    def test_cross_project_or_strategy_task_routes_to_ceo(self):
        result = route_task("比较两个项目的投入产出，决定本季度优先级和预算")

        self.assertEqual(result["route"], "ceo")
        self.assertEqual(result["lead"], "CEO")
        self.assertTrue(result["requires_user_confirmation"])

    def test_unknown_task_requests_minimum_context(self):
        result = route_task("帮我处理一下这个")

        self.assertEqual(result["route"], "direct_worker")
        self.assertEqual(result["domains"], ["待澄清"])
        self.assertTrue(result["needs_clarification"])

    def test_web_result_contains_plan_sections(self):
        page = render_result("开发网站并准备上线，同时研究用户", "demo-site")

        self.assertIn("并行任务", page)
        self.assertIn("岗位底座", page)
        self.assertIn("项目主管", page)
        self.assertIn("构建或测试结果", page)
        self.assertIn("ENG-001", page)
        self.assertIn("恢复策略", page)

    def test_local_http_demo_serves_a_plan(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:%d/?task=%s" % (server.server_address[1], quote("开发网站并准备上线"))
            with urllib.request.urlopen(url, timeout=2) as response:
                body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("工程员工", body)
            self.assertIn("验收门禁", body)
        finally:
            server.shutdown()
            server.server_close()


class TaskLedgerTests(unittest.TestCase):
    def test_task_ledger_reloads_state_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/tasks.json"
            ledger = TaskLedger(path)
            task = ledger.create("开发网站", project="demo", assignee="ENG-001", budget=4)
            ledger.transition(task.task_id, TaskStatus.IN_PROGRESS, note="已开始")
            ledger.record_usage(task.task_id, tool_calls=1)

            restored = TaskLedger(path)
            snapshot = restored.snapshot(task.task_id)
            self.assertEqual(snapshot["status"], TaskStatus.IN_PROGRESS)
            self.assertEqual(snapshot["usage"]["tool_calls"], 1)

    def test_task_can_pause_and_resume_with_compact_state(self):
        ledger = TaskLedger()
        task = ledger.create("开发网站", project="demo-site", assignee="ENG-001", budget=10)

        ledger.transition(task.task_id, TaskStatus.IN_PROGRESS, note="已完成页面骨架")
        ledger.transition(task.task_id, TaskStatus.BLOCKED, note="等待域名配置")
        resumed = ledger.resume(task.task_id)

        self.assertEqual(resumed.status, TaskStatus.IN_PROGRESS)
        snapshot = ledger.snapshot(task.task_id)
        self.assertEqual(snapshot["project"], "demo-site")
        self.assertEqual(snapshot["last_blocked_note"], "等待域名配置")
        self.assertEqual(snapshot["event_count"], 3)

    def test_task_rejects_invalid_transition_and_tracks_cost(self):
        ledger = TaskLedger()
        task = ledger.create("研究竞品", project="demo", assignee="RES-001", budget={"tool_calls": 4, "rounds": 4})

        with self.assertRaises(ValueError):
            ledger.transition(task.task_id, "unknown")
        ledger.record_usage(task.task_id, tool_calls=2, rounds=1)
        snapshot = ledger.snapshot(task.task_id)
        self.assertEqual(snapshot["usage"], {"tool_calls": 2, "rounds": 1})
        self.assertEqual(snapshot["budget_remaining"], {"tool_calls": 2, "rounds": 3})


class LearningEngineTests(unittest.TestCase):
    def test_failed_evaluations_create_reviewable_proposal(self):
        engine = LearningEngine()
        engine.record("T-1", employee_id="ENG-001", score=2, feedback="上线前缺少浏览器验证", root_cause="验收步骤遗漏")
        engine.record("T-2", employee_id="ENG-001", score=1, feedback="重复修改同一问题", root_cause="没有先做最小复现")

        proposals = engine.propose()

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].status, ProposalStatus.PROPOSED)
        self.assertEqual(proposals[0].scope, "employee")
        self.assertEqual(proposals[0].target, "ENG-001")
        self.assertEqual(len(proposals[0].evidence_task_ids), 2)

    def test_candidate_must_beat_baseline_before_approval(self):
        engine = LearningEngine()
        proposal = engine.propose_from_scores("P-1", baseline=[3, 4], candidate=[4, 4])[0]
        self.assertEqual(proposal.status, ProposalStatus.APPROVED)

        rejected = engine.propose_from_scores("P-2", baseline=[4, 4], candidate=[3, 4])[0]
        self.assertEqual(rejected.status, ProposalStatus.REJECTED)


class BootstrapTests(unittest.TestCase):
    def test_initialize_workspace_creates_safe_ai_company_files(self):
        with tempfile.TemporaryDirectory() as directory:
            result = initialize_workspace(directory, project="demo")

            self.assertEqual(result["project"], "demo")
            self.assertTrue(Path(directory, ".makecrew", "company-memory.md").exists())
            self.assertTrue(Path(directory, ".makecrew", "projects", "demo", "context-pack.md").exists())
            self.assertTrue(Path(directory, ".makecrew", "tasks.json").exists())
            self.assertTrue(Path(directory, ".makecrew", "learning.json").exists())
            registry = json.loads(Path(directory, ".makecrew", "employee-registry.json").read_text(encoding="utf-8"))
            self.assertEqual(registry["CEO-001"]["kind"], "core")
            self.assertEqual(registry["QA-001"]["kind"], "core")
            self.assertEqual(registry["ENG-001"]["kind"], "specialist_template")
            self.assertEqual(registry["SKL-001"]["kind"], "specialist_template")

    def test_audit_tools_reports_missing_capabilities(self):
        report = audit_tools(["filesystem", "shell"])

        self.assertIn("browser", report["missing"])
        self.assertIn("web_search", report["missing"])
        self.assertIn("filesystem", report["available"])

    def test_custom_employee_is_additive_and_core_roles_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize_workspace(directory)
            result = register_employee(directory, {
                "employee_id": "MKT-001",
                "name": "增长员工",
                "department": "增长",
                "skills": ["渠道分析"],
                "tools": ["web_search"],
            })
            registry = json.loads(Path(directory, ".makecrew", "employee-registry.json").read_text(encoding="utf-8"))

            self.assertEqual(result["kind"], "custom")
            self.assertEqual(registry["MKT-001"]["kind"], "custom")
            with self.assertRaises(ValueError):
                register_employee(directory, {"employee_id": "CEO-001", "name": "替换", "department": "管理"})

    def test_existing_registry_upgrade_keeps_custom_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize_workspace(directory)
            path = Path(directory, ".makecrew", "employee-registry.json")
            registry = json.loads(path.read_text(encoding="utf-8"))
            registry["LEGACY-001"] = {"name": "旧项目员工", "department": "项目", "status": "active"}
            del registry["QA-001"]
            path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

            initialize_workspace(directory)
            upgraded = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("LEGACY-001", upgraded)
            self.assertEqual(upgraded["CEO-001"]["kind"], "core")
            self.assertEqual(upgraded["QA-001"]["kind"], "core")


class OrchestrationTests(unittest.TestCase):
    def test_dispatch_prefers_existing_specialist_and_keeps_ceo_as_delegate(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize_workspace(directory, project="demo")
            calls = []

            def dispatcher(employee_id, payload):
                calls.append((employee_id, payload))
                return {"status": "completed", "summary": "已完成"}

            result = CrewOrchestrator(directory, dispatcher=dispatcher).dispatch(
                "修复登录页面的表单校验", project="demo"
            )

            self.assertEqual(result["dispatch_mode"], "existing")
            self.assertEqual(result["executor_id"], "ENG-001")
            self.assertEqual(result["ceo_action"], "delegate")
            self.assertEqual(result["verification"]["employee_id"], "QA-001")
            self.assertEqual(result["execution"]["status"], "completed")
            self.assertEqual(calls[0][0], "ENG-001")

    def test_unknown_task_creates_temporary_employee(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize_workspace(directory)
            result = CrewOrchestrator(directory).dispatch("处理一个全新领域的特殊任务")

            self.assertEqual(result["dispatch_mode"], "temporary")
            self.assertTrue(result["executor_id"].startswith("TEMP-"))
            registry = json.loads(Path(directory, ".makecrew", "employee-registry.json").read_text(encoding="utf-8"))
            self.assertEqual(registry[result["executor_id"]]["kind"], "temporary")

    def test_temporary_employee_can_be_promoted_without_touching_core(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize_workspace(directory)
            orchestrator = CrewOrchestrator(directory)
            result = orchestrator.dispatch("处理一个全新领域的特殊任务")

            promoted = orchestrator.promote(result["executor_id"])
            registry = json.loads(Path(directory, ".makecrew", "employee-registry.json").read_text(encoding="utf-8"))
            self.assertEqual(promoted["kind"], "custom")
            self.assertEqual(registry[result["executor_id"]]["kind"], "custom")
            self.assertEqual(registry["CEO-001"]["kind"], "core")


if __name__ == "__main__":
    unittest.main()
