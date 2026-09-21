import json
import tempfile
import unittest
from pathlib import Path

from ai_company_os.ceo_continuity import CeoContinuityManager, build_ceo_handoff_prompt
from ai_company_os.bootstrap import initialize_workspace
from ai_company_os.bootstrap_cli import main


def sample_snapshot():
    return {
        "company_memory_ref": ".makecrew/company-memory.md",
        "portfolio": [{"project_id": "P1", "status": "active"}],
        "open_tasks": [{"task_id": "T1", "status": "in_progress"}],
        "active_decisions": [{"decision_id": "D1", "status": "pending"}],
        "employee_status": [{"employee_id": "ENG-1", "status": "busy"}],
        "risks": [
            {"risk_id": "R1", "impact": "high"},
            {"risk_id": "R2", "impact": "low"},
        ],
        "budgets": [{"project_id": "P1", "remaining": 50}],
        "next_actions": ["完成 T1"],
        "evidence_refs": [".makecrew/projects/P1/context-pack.md"],
        "chat_history": "this full transcript must never be copied",
    }


def verification_for(handoff):
    return {
        "project_ids": ["P1"],
        "task_ids": ["T1"],
        "decision_ids": ["D1"],
        "risk_ids": ["R1"],
        "handoff_digest": handoff["digest"],
    }


class CeoContinuityTests(unittest.TestCase):
    def test_workspace_initialization_creates_and_preserves_continuity_files(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize_workspace(directory)
            state_path = Path(directory, ".makecrew", "ceo-continuity.json")
            self.assertTrue(state_path.is_file())
            self.assertTrue(Path(directory, ".makecrew", "handoffs").is_dir())
            self.assertTrue(Path(directory, ".makecrew", "portfolio-index.json").is_file())
            self.assertTrue(Path(directory, ".makecrew", "decision-log.jsonl").is_file())

            custom = CeoContinuityManager.initial_state()
            custom["ceo_id"] = "CEO-CUSTOM"
            state_path.write_text(json.dumps(custom), encoding="utf-8")
            initialize_workspace(directory)
            self.assertEqual(json.loads(state_path.read_text(encoding="utf-8"))["ceo_id"], "CEO-CUSTOM")

    def test_context_pressure_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            cases = [
                (699, "normal"),
                (700, "compress"),
                (850, "prepare_handoff"),
                (950, "handoff_required"),
                (1000, "handoff_required"),
            ]
            for used, expected in cases:
                with self.subTest(used=used):
                    self.assertEqual(CeoContinuityManager.assess_context(used, 1000)["level"], expected)
            self.assertFalse(Path(directory, ".makecrew").exists())

    def test_handoff_is_compact_digest_verified_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CeoContinuityManager(directory, clock=lambda: 100.0)
            handoff = manager.prepare_handoff(sample_snapshot(), "ceo-old")
            repeated = manager.prepare_handoff(sample_snapshot(), "ceo-old")

            self.assertEqual(handoff, repeated)
            self.assertNotIn("chat_history", handoff)
            self.assertNotIn("this full transcript", json.dumps(handoff))
            self.assertEqual(handoff["handoff_id"], "CEO-HANDOFF-000002")
            prompt = build_ceo_handoff_prompt(handoff)
            self.assertIn(handoff["digest"], prompt)
            self.assertIn("P1", prompt)

    def test_pending_package_refreshes_before_candidate_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            ticks = iter([100.0, 101.0, 102.0])
            manager = CeoContinuityManager(directory, clock=lambda: next(ticks))
            first = manager.prepare_handoff(sample_snapshot(), "ceo-old")
            updated = sample_snapshot()
            updated["open_tasks"].append({"task_id": "T2"})

            refreshed = manager.prepare_handoff(updated, "ceo-old")

            self.assertEqual(refreshed["handoff_id"], first["handoff_id"])
            self.assertNotEqual(refreshed["digest"], first["digest"])
            self.assertEqual({item["task_id"] for item in refreshed["open_tasks"]}, {"T1", "T2"})

    def test_candidate_cannot_activate_before_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CeoContinuityManager(directory)
            handoff = manager.prepare_handoff(sample_snapshot(), "ceo-old")
            manager.register_candidate("ceo-new", handoff["handoff_id"])

            with self.assertRaisesRegex(ValueError, "尚未通过"):
                manager.activate("ceo-new", handoff["handoff_id"])
            self.assertEqual(manager.status()["active_thread_id"], "ceo-old")

    def test_verification_requires_projects_tasks_decisions_risks_and_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CeoContinuityManager(directory)
            handoff = manager.prepare_handoff(sample_snapshot(), "ceo-old")
            manager.register_candidate("ceo-new", handoff["handoff_id"])

            with self.assertRaisesRegex(ValueError, "task_ids"):
                manager.verify_candidate("ceo-new", handoff["handoff_id"], {
                    "project_ids": ["P1"],
                    "task_ids": [],
                    "decision_ids": ["D1"],
                    "risk_ids": ["R1"],
                    "handoff_digest": handoff["digest"],
                })
            self.assertFalse(manager.status()["pending_handoff"]["verified"])

    def test_same_thread_cannot_be_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CeoContinuityManager(directory)
            handoff = manager.prepare_handoff(sample_snapshot(), "ceo-old")
            with self.assertRaisesRegex(ValueError, "不同的新线程"):
                manager.register_candidate("ceo-old", handoff["handoff_id"])

    def test_successful_activation_leaves_exactly_one_active_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CeoContinuityManager(directory, clock=lambda: 100.0)
            handoff = manager.prepare_handoff(sample_snapshot(), "ceo-old")
            manager.register_candidate("ceo-new", handoff["handoff_id"])
            manager.verify_candidate("ceo-new", handoff["handoff_id"], verification_for(handoff))

            result = manager.activate("ceo-new", handoff["handoff_id"])
            status = manager.status()

            self.assertEqual(result["generation"], 2)
            self.assertEqual(status["active_thread_id"], "ceo-new")
            self.assertEqual(sum(item["status"] == "active" for item in status["threads"]), 1)
            self.assertEqual(next(item for item in status["threads"] if item["thread_id"] == "ceo-old")["status"], "archived")

    def test_pending_handoff_survives_restart_and_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            first = CeoContinuityManager(directory)
            handoff = first.prepare_handoff(sample_snapshot(), "ceo-old")
            restored = CeoContinuityManager(directory)
            self.assertEqual(restored.status()["pending_handoff"]["handoff_id"], handoff["handoff_id"])

            path = Path(directory, ".makecrew", "handoffs", f"{handoff['handoff_id']}.json")
            changed = json.loads(path.read_text(encoding="utf-8"))
            changed["next_actions"] = ["tampered"]
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "摘要校验失败"):
                restored.register_candidate("ceo-new", handoff["handoff_id"])

    def test_cli_commands_return_success(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory, "snapshot.json")
            snapshot_path.write_text(json.dumps(sample_snapshot(), ensure_ascii=False), encoding="utf-8")
            self.assertEqual(main(["ceo-assess", "--path", directory, "--used-tokens", "850", "--context-window", "1000"]), 0)
            self.assertEqual(main(["ceo-prepare-handoff", "--path", directory, "--current-thread", "ceo-old", "--snapshot", str(snapshot_path)]), 0)
            self.assertEqual(main(["ceo-status", "--path", directory]), 0)


if __name__ == "__main__":
    unittest.main()
