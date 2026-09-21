import tempfile
import unittest
from pathlib import Path

from ai_company_os import ProjectControlTower, ProjectNode


class ProjectControlTests(unittest.TestCase):
    def test_critical_path_budget_resource_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            tower = ProjectControlTower("software", path=Path(directory) / "project.json")
            tower.set_budget(100)
            tower.set_resource_limit("研发", 1)
            tower.add_node(ProjectNode("requirements", "需求确认", duration=2, budget=20, resources=["产品"]))
            tower.add_node(ProjectNode("development", "开发", duration=5, depends_on=["requirements"], budget=60, resources=["研发"]))
            tower.add_node(ProjectNode("test", "测试", duration=3, depends_on=["development"], budget=30, resources=["研发"]))
            tower.add_risk("R1", "供应商延迟", impact="high", trigger="交期未确认")
            self.assertEqual(tower.critical_path()["development"]["slack"], 0)
            self.assertTrue(tower.health()["budget"]["over"])
            self.assertEqual(tower.health()["status"], "warning")
            restored = ProjectControlTower("software", path=Path(directory) / "project.json")
            self.assertEqual(len(restored.nodes), 3)


if __name__ == "__main__":
    unittest.main()
