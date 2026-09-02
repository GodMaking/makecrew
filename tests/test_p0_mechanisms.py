import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from ai_company_os.bootstrap_cli import main
from ai_company_os.capabilities import audit_employee_capabilities
from ai_company_os.checkpoint import JsonCheckpointStore, RetryPolicy
from ai_company_os.skill_audit import audit_skill_directory, audit_skill_file, inventory_skill_directory


class SkillAuditTests(unittest.TestCase):
    def test_valid_skill_has_required_metadata_and_progressive_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills" / "demo-skill"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: Use when validating a demo task.\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (root / "references").mkdir()
            report = audit_skill_file(root / "SKILL.md")

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["metadata"]["name"], "demo-skill")
            self.assertEqual(report["progressive_disclosure"]["references"], "available")
            self.assertEqual(report["issues"], [])

    def test_directory_audit_reports_invalid_skill_without_stopping_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            valid = root / "valid-skill"
            invalid = root / "bad_skill"
            valid.mkdir(parents=True)
            invalid.mkdir(parents=True)
            (valid / "SKILL.md").write_text(
                "---\nname: valid-skill\ndescription: A valid skill.\n---\nbody\n",
                encoding="utf-8",
            )
            (invalid / "SKILL.md").write_text(
                "---\nname: Bad Skill\ndescription:\n---\n",
                encoding="utf-8",
            )

            report = audit_skill_directory(root)

            self.assertEqual(report["skill_count"], 2)
            self.assertEqual(report["status"], "review")
            self.assertEqual(report["pass_count"], 1)
            self.assertEqual(report["review_count"], 1)
            invalid_report = next(item for item in report["skills"] if Path(item["path"]).parent.name == "bad_skill")
            issue_codes = {issue["code"] for issue in invalid_report["issues"]}
            self.assertIn("invalid_name", issue_codes)
            self.assertIn("missing_description", issue_codes)

    def test_inventory_exposes_metadata_without_loading_skill_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills" / "demo-skill"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: A metadata-only test.\n---\n"
                "SECRET_INSTRUCTION_BODY\n",
                encoding="utf-8",
            )

            inventory = inventory_skill_directory(root.parent)

            self.assertEqual(inventory["status"], "ready")
            self.assertEqual(inventory["ready_skill_ids"], ["demo-skill"])
            self.assertEqual(inventory["skills"][0]["description"], "A metadata-only test.")
            self.assertNotIn("SECRET_INSTRUCTION_BODY", json.dumps(inventory, ensure_ascii=False))
            self.assertEqual(inventory["load_policy"]["instructions"], "load_after_match")

    def test_skill_inventory_cli_returns_machine_readable_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills" / "demo-skill"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: A CLI inventory test.\n---\nbody\n",
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["skill-inventory", "--path", str(root.parent)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["ready_skill_ids"], ["demo-skill"])

    def test_method_catalog_cli_returns_machine_readable_audit(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["method-audit"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "pass")
        self.assertGreater(payload["card_count"], 0)


class CheckpointTests(unittest.TestCase):
    def test_json_checkpoint_is_idempotent_and_restores_latest_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonCheckpointStore(Path(directory) / "checkpoints.json")
            first = store.save(
                "T1", "execute", {"files": ["a.py"]}, idempotency_key="T1:execute:1"
            )
            same = store.save(
                "T1", "execute", {"files": ["changed.py"]}, idempotency_key="T1:execute:1"
            )
            store.save("T1", "verify", {"passed": True}, idempotency_key="T1:verify:1")

            restored = JsonCheckpointStore(Path(directory) / "checkpoints.json").load_latest("T1")

            self.assertEqual(first, same)
            self.assertEqual(restored["node_id"], "verify")
            self.assertEqual(restored["state"], {"passed": True})
            self.assertEqual(store.audit()["records"], 2)

    def test_checkpoint_rejects_valid_json_with_invalid_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.json"
            path.write_text("[]", encoding="utf-8")

            with self.assertRaises(ValueError):
                JsonCheckpointStore(path)

            path.write_text('{"version": 1, "records": ["bad"]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                JsonCheckpointStore(path)

    def test_retry_policy_exposes_bounded_retry_and_resume_contract(self):
        policy = RetryPolicy(max_attempts=3, backoff_seconds=2)

        self.assertEqual(policy.decision(attempt=1, retryable=True)["action"], "retry")
        self.assertEqual(policy.decision(attempt=3, retryable=True)["action"], "stop")
        self.assertEqual(policy.decision(attempt=1, retryable=False)["action"], "stop")
        self.assertEqual(policy.decision(attempt=1, retryable=True)["resume_from"], "last_checkpoint")


class CapabilityMatrixTests(unittest.TestCase):
    def test_new_p0_skills_are_audited_and_bound_to_roles(self):
        report = audit_employee_capabilities()

        self.assertEqual(report["missing_skill_ids"], [])
        self.assertEqual(report["unknown_skill_ids"], [])
        self.assertIn("review-and-critique", report["required_skill_ids"])
        self.assertIn("skill-audit", report["required_skill_ids"])
        self.assertIn("checkpoint-recovery", report["required_skill_ids"])


if __name__ == "__main__":
    unittest.main()
