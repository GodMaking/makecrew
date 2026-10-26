import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from ai_company_os.bootstrap_cli import main
from ai_company_os.qa_regression import (
    evaluate_qa_regression_results,
    export_qa_regression_cases,
    qa_regression_cases,
)


class QaRegressionTests(unittest.TestCase):
    def test_fixed_blinded_suite_has_ten_cases_and_required_failure_modes(self):
        cases = qa_regression_cases()
        exported = export_qa_regression_cases()

        self.assertEqual(len(cases), 10)
        self.assertEqual(len({case["case_id"] for case in cases}), 10)
        self.assertEqual(
            {case["expected_status"] for case in cases},
            {"passed", "rework_required", "blocked"},
        )
        serialized = json.dumps(exported, ensure_ascii=False)
        self.assertNotIn("expected_status", serialized)
        self.assertNotIn("expected_issue", serialized)
        case_text = json.dumps(cases, ensure_ascii=False)
        self.assertIn("rework_attempt", case_text)
        self.assertIn("max_rework_attempts", case_text)

    def test_evaluation_reports_accuracy_false_accepts_and_tool_calls(self):
        cases = qa_regression_cases()
        results = [
            {
                "case_id": case["case_id"],
                "status": case["expected_status"],
                "tool_calls": index % 3,
            }
            for index, case in enumerate(cases, start=1)
        ]

        report = evaluate_qa_regression_results(results)

        self.assertEqual(report["case_count"], 10)
        self.assertEqual(report["correct_count"], 10)
        self.assertEqual(report["verdict_accuracy"], 1.0)
        self.assertEqual(report["false_accept_count"], 0)
        self.assertEqual(report["tool_calls_total"], 10)
        self.assertEqual(report["missing_case_ids"], [])

    def test_false_accept_is_counted_separately_from_other_mismatches(self):
        cases = qa_regression_cases()
        results = [
            {"case_id": case["case_id"], "status": case["expected_status"], "tool_calls": 1}
            for case in cases
        ]
        results[1]["status"] = "passed"
        results[2]["status"] = "blocked"

        report = evaluate_qa_regression_results(results)

        self.assertEqual(report["verdict_accuracy"], 0.8)
        self.assertEqual(report["false_accept_count"], 1)
        self.assertEqual(report["false_reject_count"], 0)

    def test_missing_case_is_counted_as_incomplete_not_silently_dropped(self):
        cases = qa_regression_cases()
        results = [
            {"case_id": case["case_id"], "status": case["expected_status"], "tool_calls": 1}
            for case in cases[:-1]
        ]

        report = evaluate_qa_regression_results(results)

        self.assertEqual(report["submitted_count"], 9)
        self.assertEqual(report["verdict_accuracy"], 0.9)
        self.assertEqual(report["missing_case_ids"], [cases[-1]["case_id"]])

    def test_missing_usage_is_not_reported_as_zero_and_run_metadata_is_retained(self):
        cases = qa_regression_cases()
        results = [
            {"case_id": case["case_id"], "status": case["expected_status"], "tool_calls": 1}
            for case in cases
        ]
        del results[0]["tool_calls"]

        report = evaluate_qa_regression_results({
            "run_id": "run-2026-10-26-a",
            "model": "fixture-model",
            "prompt_version": "qa-v2",
            "results": results,
        })

        self.assertFalse(report["usage_complete"])
        self.assertIsNone(report["tool_calls_total"])
        self.assertEqual(report["missing_usage_case_ids"], ["QA-01"])
        self.assertEqual(report["run_metadata"]["prompt_version"], "qa-v2")

    def test_duplicate_unknown_or_negative_usage_results_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "重复"):
            evaluate_qa_regression_results([
                {"case_id": "QA-01", "status": "passed"},
                {"case_id": "QA-01", "status": "passed"},
            ])
        with self.assertRaisesRegex(ValueError, "未知"):
            evaluate_qa_regression_results([{"case_id": "QA-UNKNOWN", "status": "passed"}])
        with self.assertRaisesRegex(ValueError, "tool_calls"):
            evaluate_qa_regression_results([{"case_id": "QA-01", "status": "passed", "tool_calls": -1}])

    def test_cli_exports_blinded_cases_and_scores_candidate_results(self):
        with tempfile.TemporaryDirectory() as directory:
            cases_path = Path(directory) / "cases.json"
            results_path = Path(directory) / "results.json"
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["qa-regression", "--export-cases", str(cases_path)]), 0)
            exported = json.loads(cases_path.read_text(encoding="utf-8"))
            self.assertEqual(len(exported["cases"]), 10)
            self.assertNotIn("expected_status", cases_path.read_text(encoding="utf-8"))
            before = cases_path.read_bytes()
            with self.assertRaisesRegex(SystemExit, "输出文件已存在"):
                main(["qa-regression", "--export-cases", str(cases_path)])
            self.assertEqual(cases_path.read_bytes(), before)

            results_path.write_text(
                json.dumps({"results": [
                    {"case_id": case["case_id"], "status": case["expected_status"], "tool_calls": 1}
                    for case in qa_regression_cases()
                ]}),
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["qa-regression", "--results", str(results_path)]), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["verdict_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
