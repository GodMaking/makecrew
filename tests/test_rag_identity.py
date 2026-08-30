import unittest

from ai_company_os.rag import RetrievalScope
from ai_company_os.rag_identity import scope_for_employee, scope_payload


class RagIdentityTests(unittest.TestCase):
    def test_ceo_has_company_scope_and_optional_project_scope(self):
        scope = scope_for_employee("CEO-001", project_ids=("eng",), memory_scope="company_and_project")
        self.assertEqual(scope.actor, "ceo")
        self.assertTrue(scope.include_company)
        self.assertEqual(scope.project_ids, ("eng",))

    def test_project_employee_is_limited_to_bound_project(self):
        scope = scope_for_employee("ENG-001", project_ids=("eng",), memory_scope="project")
        self.assertEqual(scope.actor, "employee")
        self.assertFalse(scope.include_company)
        self.assertEqual(scope.project_ids, ("eng",))

    def test_company_and_project_employee_can_read_both_explicit_scopes(self):
        scope = scope_for_employee("KNO-001", project_ids=("eng",), memory_scope="company_and_project")
        self.assertTrue(scope.include_company)
        self.assertEqual(scope.project_ids, ("eng",))

    def test_unbound_project_employee_fails_closed_to_no_project_records(self):
        scope = scope_for_employee("ENG-001", memory_scope="project")
        self.assertEqual(scope.project_ids, ())
        self.assertFalse(scope.include_company)

    def test_payload_is_json_friendly_and_does_not_contain_content(self):
        payload = scope_payload(scope_for_employee("ENG-001", project_ids=("eng",)))
        self.assertEqual(payload["project_ids"], ["eng"])
        self.assertNotIn("content", payload)
        self.assertIsInstance(RetrievalScope(**{**payload, "project_ids": tuple(payload["project_ids"])}), RetrievalScope)


if __name__ == "__main__":
    unittest.main()
