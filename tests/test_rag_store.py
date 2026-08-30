import json
import tempfile
import unittest
from pathlib import Path

from ai_company_os.rag import RetrievalScope
from ai_company_os.rag_store import JsonRagIndex, sha256_file


class RagStoreTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
