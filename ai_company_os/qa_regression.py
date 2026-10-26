"""Blinded, deterministic regression cases for MakeCrew QA verdicts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "QA-01",
        "expected_status": "passed",
        "expected_issue": "",
        "input": {
            "required_artifact_refs": ["deliverables/prd.md"],
            "artifact_refs": ["deliverables/prd.md"],
            "criteria": ["AC-1", "AC-2"],
            "evidence": [
                {"ref": "reports/research.md", "supports": ["AC-1"], "valid": True},
                {"ref": "reports/test.md", "supports": ["AC-2"], "valid": True},
            ],
            "dependency_status": "ready",
            "conflicting_findings": False,
            "critical_defects": [],
            "rework_attempt": 0,
            "max_rework_attempts": 2,
        },
    },
    {
        "case_id": "QA-02",
        "expected_status": "rework_required",
        "expected_issue": "missing_evidence",
        "input": {
            "required_artifact_refs": ["deliverables/prd.md"],
            "artifact_refs": ["deliverables/prd.md"],
            "criteria": ["AC-1", "AC-2"],
            "evidence": [{"ref": "reports/research.md", "supports": ["AC-1"], "valid": True}],
            "dependency_status": "ready",
            "conflicting_findings": False,
            "critical_defects": [],
            "rework_attempt": 0,
            "max_rework_attempts": 2,
        },
    },
    {
        "case_id": "QA-03",
        "expected_status": "rework_required",
        "expected_issue": "wrong_artifact",
        "input": {
            "required_artifact_refs": ["deliverables/prd.md"],
            "artifact_refs": ["deliverables/old-prd.md"],
            "criteria": ["AC-1"],
            "evidence": [{"ref": "reports/test.md", "supports": ["AC-1"], "valid": True}],
            "dependency_status": "ready",
            "conflicting_findings": False,
            "critical_defects": [],
            "rework_attempt": 0,
            "max_rework_attempts": 2,
        },
    },
    {
        "case_id": "QA-04",
        "expected_status": "rework_required",
        "expected_issue": "missing_artifact",
        "input": {
            "required_artifact_refs": ["deliverables/prd.md"],
            "artifact_refs": [],
            "criteria": ["AC-1"],
            "evidence": [{"ref": "reports/test.md", "supports": ["AC-1"], "valid": True}],
            "dependency_status": "ready",
            "conflicting_findings": False,
            "critical_defects": [],
            "rework_attempt": 0,
            "max_rework_attempts": 2,
        },
    },
    {
        "case_id": "QA-05",
        "expected_status": "rework_required",
        "expected_issue": "conflicting_agent_findings",
        "input": {
            "required_artifact_refs": ["deliverables/architecture.md"],
            "artifact_refs": ["deliverables/architecture.md"],
            "criteria": ["AC-1"],
            "evidence": [{"ref": "reports/review.md", "supports": ["AC-1"], "valid": True}],
            "dependency_status": "ready",
            "conflicting_findings": True,
            "critical_defects": [],
            "rework_attempt": 0,
            "max_rework_attempts": 2,
        },
    },
    {
        "case_id": "QA-06",
        "expected_status": "blocked",
        "expected_issue": "blocked_dependency",
        "input": {
            "required_artifact_refs": ["deliverables/release.md"],
            "artifact_refs": ["deliverables/release.md"],
            "criteria": ["AC-1"],
            "evidence": [{"ref": "reports/test.md", "supports": ["AC-1"], "valid": True}],
            "dependency_status": "blocked",
            "conflicting_findings": False,
            "critical_defects": [],
            "rework_attempt": 0,
            "max_rework_attempts": 2,
        },
    },
    {
        "case_id": "QA-07",
        "expected_status": "rework_required",
        "expected_issue": "unsupported_evidence",
        "input": {
            "required_artifact_refs": ["deliverables/prd.md"],
            "artifact_refs": ["deliverables/prd.md"],
            "criteria": ["AC-1"],
            "evidence": [{"ref": "reports/notes.md", "supports": [], "valid": True}],
            "dependency_status": "ready",
            "conflicting_findings": False,
            "critical_defects": [],
            "rework_attempt": 0,
            "max_rework_attempts": 2,
        },
    },
    {
        "case_id": "QA-08",
        "expected_status": "blocked",
        "expected_issue": "rework_limit_reached",
        "input": {
            "required_artifact_refs": ["deliverables/prd.md"],
            "artifact_refs": ["deliverables/prd.md"],
            "criteria": ["AC-1"],
            "evidence": [],
            "dependency_status": "ready",
            "conflicting_findings": False,
            "critical_defects": ["AC-1 still fails after revision"],
            "rework_attempt": 2,
            "max_rework_attempts": 2,
        },
    },
    {
        "case_id": "QA-09",
        "expected_status": "passed",
        "expected_issue": "",
        "input": {
            "required_artifact_refs": ["deliverables/prd.md"],
            "artifact_refs": ["deliverables/prd.md"],
            "criteria": ["AC-1"],
            "evidence": [{"ref": "reports/retest.md", "supports": ["AC-1"], "valid": True}],
            "dependency_status": "ready",
            "conflicting_findings": False,
            "critical_defects": [],
            "rework_attempt": 1,
            "max_rework_attempts": 2,
        },
    },
    {
        "case_id": "QA-10",
        "expected_status": "rework_required",
        "expected_issue": "critical_test_failure",
        "input": {
            "required_artifact_refs": ["deliverables/release.md"],
            "artifact_refs": ["deliverables/release.md"],
            "criteria": ["AC-1", "AC-2"],
            "evidence": [
                {"ref": "reports/smoke.md", "supports": ["AC-1", "AC-2"], "valid": True}
            ],
            "dependency_status": "ready",
            "conflicting_findings": False,
            "critical_defects": ["AC-2 failed"],
            "rework_attempt": 0,
            "max_rework_attempts": 2,
        },
    },
)

VALID_STATUSES = {"passed", "rework_required", "blocked"}


def qa_regression_cases() -> list[dict[str, Any]]:
    """Return copies of the fixed, labeled cases for tests and local evaluators."""
    return deepcopy(list(_CASES))


def export_qa_regression_cases() -> dict[str, Any]:
    """Return a blinded case pack; expected labels remain inside the evaluator."""
    return {
        "version": 1,
        "cases": [
            {"case_id": case["case_id"], "input": deepcopy(case["input"])}
            for case in _CASES
        ],
    }


def evaluate_qa_regression_results(payload: Any) -> dict[str, Any]:
    """Compare candidate QA verdicts with fixed labels and summarize cost signals.

    ``tool_calls`` is an observed value supplied by the caller/host. Missing
    usage remains explicitly incomplete rather than being treated as zero.
    """
    run_metadata: dict[str, str] = {}
    if isinstance(payload, dict):
        run_metadata = {
            key: str(payload[key]).strip()[:200]
            for key in ("run_id", "model", "prompt_version")
            if payload.get(key) is not None and str(payload[key]).strip()
        }
        payload = payload.get("results")
    if not isinstance(payload, list):
        raise ValueError("结果文件应包含 results 数组")

    known = {case["case_id"]: case for case in _CASES}
    actual_by_id: dict[str, dict[str, Any]] = {}
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("每条回归结果必须是 JSON 对象")
        case_id = str(raw.get("case_id", "")).strip()
        if case_id not in known:
            raise ValueError(f"未知 QA 回归 case_id：{case_id}")
        if case_id in actual_by_id:
            raise ValueError(f"QA 回归结果重复：{case_id}")
        status = str(raw.get("status", "")).strip().lower()
        if status not in VALID_STATUSES:
            raise ValueError(f"{case_id} 的 status 必须是 {', '.join(sorted(VALID_STATUSES))}")
        tool_calls = raw.get("tool_calls")
        if tool_calls is not None and (isinstance(tool_calls, bool) or not isinstance(tool_calls, int) or tool_calls < 0):
            raise ValueError(f"{case_id} 的 tool_calls 必须是非负整数")
        actual_by_id[case_id] = {
            "status": status,
            "tool_calls": tool_calls,
            "reason": str(raw.get("reason", "")).strip(),
        }

    case_reports: list[dict[str, Any]] = []
    correct_count = 0
    false_accept_count = 0
    false_reject_count = 0
    actual_pass_count = 0
    missing_case_ids: list[str] = []
    missing_usage_case_ids: list[str] = []
    reported_tool_calls = 0

    for case in _CASES:
        case_id = case["case_id"]
        actual = actual_by_id.get(case_id)
        expected_status = case["expected_status"]
        actual_status = actual["status"] if actual else "missing"
        calls = actual["tool_calls"] if actual else None
        if actual is None:
            missing_case_ids.append(case_id)
        elif calls is None:
            missing_usage_case_ids.append(case_id)
        else:
            reported_tool_calls += calls

        correct = actual_status == expected_status
        false_accept = expected_status != "passed" and actual_status == "passed"
        false_reject = expected_status == "passed" and actual_status != "passed"
        correct_count += int(correct)
        false_accept_count += int(false_accept)
        false_reject_count += int(false_reject)
        actual_pass_count += int(actual_status == "passed")
        case_reports.append({
            "case_id": case_id,
            "expected_status": expected_status,
            "actual_status": actual_status,
            "expected_issue": case["expected_issue"],
            "correct": correct,
            "false_accept": false_accept,
            "false_reject": false_reject,
            "tool_calls": calls,
            "reason": actual["reason"] if actual else "",
        })

    denominator = len(_CASES)
    usage_complete = not missing_case_ids and not missing_usage_case_ids
    return {
        "suite_version": 1,
        "run_metadata": run_metadata,
        "case_count": denominator,
        "submitted_count": len(actual_by_id),
        "correct_count": correct_count,
        "verdict_accuracy": round(correct_count / denominator, 4),
        "actual_pass_count": actual_pass_count,
        "actual_pass_rate": round(actual_pass_count / denominator, 4),
        "false_accept_count": false_accept_count,
        "false_reject_count": false_reject_count,
        "missing_case_ids": missing_case_ids,
        "usage_complete": usage_complete,
        "missing_usage_case_ids": missing_usage_case_ids,
        "tool_calls_total": reported_tool_calls if usage_complete else None,
        "reported_tool_calls_partial_sum": reported_tool_calls,
        "cases": case_reports,
    }
