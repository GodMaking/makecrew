import unittest
import threading
import urllib.request
from urllib.parse import quote

from ai_company_os.router import route_task
from ai_company_os.web import render_result
from ai_company_os.web import Handler
from http.server import ThreadingHTTPServer


class RouteTaskTests(unittest.TestCase):
    def test_single_specialist_task_routes_directly(self):
        result = route_task("修复登录页面的表单校验")

        self.assertEqual(result["route"], "direct_worker")
        self.assertEqual(result["lead"], "工程员工")
        self.assertEqual(result["parallel_tasks"], [])
        self.assertIn("构建或测试结果", result["acceptance_gates"])

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
        self.assertIn("项目主管", page)
        self.assertIn("构建或测试结果", page)

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


if __name__ == "__main__":
    unittest.main()
