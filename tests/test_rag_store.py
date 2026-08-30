import json
import tempfile
import unittest
from pathlib import Path

from ai_company_os.rag import RetrievalScope
from ai_company_os.rag_store import JsonRagIndex, plan_directory, sha256_file


class RagStoreTests(unittest.TestCase):
    def test_plan_directory_reads_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            (root / "guide.md").write_text("机密正文", encoding="utf-8")
            (root / "video.mp4").write_bytes(b"binary")
            report = plan_directory(root)
            self.assertEqual(report["supported_files"], 1)
            self.assertEqual(report["ignored_files"], 1)
            self.assertFalse(report["content_read"])
            self.assertFalse(report["index_written"])

    def test_sync_is_incremental_and_removes_deleted_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            first = root / "guide.md"
            first.write_text("# 工程指南\n\n施工进度计划。", encoding="utf-8")
            index = JsonRagIndex(Path(directory) / "index.json")

            initial = index.sync_directory(root, scope="project", project_id="engineering", max_chars=100)
            self.assertEqual(initial["added"], 1)
            self.assertEqual(initial["chunks"], 1)
            second = index.sync_directory(root, scope="project", project_id="engineering", max_chars=100)
            self.assertEqual(second["skipped"], 1)
            self.assertEqual(sha256_file(first), index.files[str(first.resolve())]["sha256"])

            first.write_text("# 工程指南\n\n造价数据库。", encoding="utf-8")
            changed = index.sync_directory(root, scope="project", project_id="engineering", max_chars=100)
            self.assertEqual(changed["changed"], 1)
            first.unlink()
            removed = index.sync_directory(root, scope="project", project_id="engineering", max_chars=100)
            self.assertEqual(removed["removed"], 1)
            self.assertEqual(index.audit()["records"], 0)

    def test_persistence_keeps_scope_and_query_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            path = root / "notes.txt"
            path.write_text("工程招投标资料", encoding="utf-8")
            index_path = Path(directory) / "index.json"
            JsonRagIndex(index_path).sync_directory(root, scope="project", project_id="eng")
            restored = JsonRagIndex(index_path)
            hits = restored.search("招投标", RetrievalScope("manager", project_ids=("eng",)))
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].citation()["scope"], "project")
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 1)

    def test_quality_audit_reports_duplicates_conflicts_and_hash_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            one = root / "one.md"
            two = root / "two.md"
            one.write_text("# 发布流程\n\n先验收再发布。", encoding="utf-8")
            two.write_text("# 发布流程\n\n先测试再发布。", encoding="utf-8")
            index = JsonRagIndex(Path(directory) / "index.json")
            index.sync_directory(root, scope="project", project_id="demo")
            initial = index.audit_quality()
            self.assertEqual(initial["status"], "review")
            self.assertEqual(len(initial["conflict_groups"]), 1)
            one.write_text("# 发布流程\n\n内容已变化但还没同步。", encoding="utf-8")
            drift = index.audit_quality()
            self.assertIn(str(one.resolve()), drift["stale_sources"])

    def test_quality_audit_does_not_flag_clean_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            (root / "guide.md").write_text("# 指南\n\n唯一内容。", encoding="utf-8")
            index = JsonRagIndex(Path(directory) / "index.json")
            index.sync_directory(root)
            report = index.audit_quality()
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["issue_count"], 0)


if __name__ == "__main__":
    unittest.main()
