"""Execution boundary between MakeCrew routing and real employee runtimes.

The local MVP cannot open arbitrary external conversations by itself.  It does,
however, make the delegation decision explicit and accepts a small dispatcher
adapter supplied by Codex, Claude, or another host platform.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .bootstrap import initialize_workspace
from .router import CORE_EMPLOYEE_PROFILES, EMPLOYEE_PROFILES, route_task


Dispatcher = Callable[[str, dict[str, Any]], dict[str, Any]]


class CrewOrchestrator:
    """Route work to registered employees and keep CEO execution separate."""

    def __init__(self, workspace: str | Path, *, dispatcher: Dispatcher | None = None) -> None:
        self.root = Path(workspace).expanduser().resolve()
        initialize_workspace(self.root)
        self.registry_path = self.root / ".makecrew" / "employee-registry.json"
        self.dispatcher = dispatcher

    def _read_registry(self) -> dict[str, dict[str, Any]]:
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _write_registry(self, registry: dict[str, dict[str, Any]]) -> None:
        self.registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _active(record: dict[str, Any]) -> bool:
        return record.get("status", "active") == "active"

    def _find_employee(self, domain: str, registry: dict[str, dict[str, Any]]) -> str | None:
        """Choose a deterministic active employee; built-in templates win ties."""
        template = EMPLOYEE_PROFILES.get(domain)
        preferred = template.employee_id if template else ""
        if preferred in registry and self._active(registry[preferred]):
            return preferred

        matches = sorted(
            employee_id
            for employee_id, record in registry.items()
            if self._active(record)
            and record.get("department") == domain
            and record.get("kind") not in {"core", "temporary"}
        )
        return matches[0] if matches else None

    def _temporary_employee(self, task: str, registry: dict[str, dict[str, Any]], domain: str = "临时任务") -> str:
        signature = hashlib.sha1(f"{domain}:{task.strip()}".encode("utf-8")).hexdigest()[:8].upper()
        employee_id = f"TEMP-{signature}"
        existing = registry.get(employee_id)
        if existing and self._active(existing):
            return employee_id

        registry[employee_id] = {
            "name": f"临时任务员工 {signature}",
            "department": "临时任务",
            "skills": ["任务专长（由本次任务生成）"],
            "tools": ["filesystem"],
            "memory_scope": "project",
            "status": "active",
            "kind": "temporary",
            "created_for": task.strip(),
        }
        self._write_registry(registry)
        return employee_id

    def _execute(self, employee_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.dispatcher is None:
            return {"status": "queued", "employee_id": employee_id}
        result = self.dispatcher(employee_id, payload)
        if isinstance(result, dict):
            return {"employee_id": employee_id, **result}
        return {"employee_id": employee_id, "status": "completed", "result": result}

    def dispatch(self, task: str, *, project: str = "") -> dict[str, Any]:
        """Delegate a task and return execution plus independent QA instructions."""
        plan = route_task(task, project)
        registry = self._read_registry()
        assignments: list[dict[str, Any]] = []

        # A CEO decision remains a management action. The project manager is
        # the execution coordinator; specialists handle any later work items.
        if plan["route"] == "ceo":
            employee_id = "PM-001"
            assignment = {
                "role": "项目主管",
                "objective": "把 CEO 决策拆成可执行任务",
                "output": "任务拆解、负责人和依赖",
                "employee_id": employee_id,
                "dispatch_mode": "existing",
            }
            assignments.append(assignment)
        else:
            domains = plan["domains"]
            if domains == ["待澄清"]:
                domains = ["待澄清"]
            for index, domain in enumerate(domains):
                employee_id = self._find_employee(domain, registry) if domain in EMPLOYEE_PROFILES else None
                dispatch_mode = "existing"
                if employee_id is None:
                    employee_id = self._temporary_employee(task, registry, domain)
                    dispatch_mode = "temporary"
                source = plan["assignments"][index] if index < len(plan["assignments"]) else {
                    "role": "临时任务员工",
                    "objective": "完成任务并提交可复核结果",
                    "output": "结果、证据和下一步",
                    "required_skills": [],
                    "tools": ["filesystem"],
                }
                assignments.append({
                    **source,
                    "employee_id": employee_id,
                    "dispatch_mode": dispatch_mode,
                })

        executions = []
        for assignment in assignments:
            payload = {
                "task": task.strip(),
                "project": project,
                "assignment": assignment,
                "acceptance_gates": plan["acceptance_gates"],
                "instruction": "只执行分配范围，完成后回传结果、证据、风险和下一步。",
            }
            executions.append(self._execute(assignment["employee_id"], payload))

        modes = {assignment["dispatch_mode"] for assignment in assignments}
        mode = next(iter(modes)) if len(modes) == 1 else "mixed"
        return {
            "task": task.strip(),
            "project": project,
            "route": plan["route"],
            "lead": plan["lead"],
            "ceo_action": "delegate",
            "dispatch_mode": mode,
            "executor_id": assignments[0]["employee_id"] if assignments else "",
            "executor_ids": [assignment["employee_id"] for assignment in assignments],
            "assignments": assignments,
            "execution": executions[0] if len(executions) == 1 else {"status": "dispatched", "items": executions},
            "verification": plan["verification_contract"],
            "acceptance_gates": plan["acceptance_gates"],
            "next_action": "由独立验收员检查交付；临时员工完成后选择升级为长期员工或归档。",
        }

    def promote(self, employee_id: str) -> dict[str, Any]:
        """Promote a temporary employee to a user-owned long-term profile."""
        registry = self._read_registry()
        record = registry.get(employee_id)
        if record is None:
            raise KeyError(f"员工不存在：{employee_id}")
        if record.get("kind") != "temporary":
            raise ValueError(f"只有临时员工可以升级：{employee_id}")
        record["kind"] = "custom"
        record["promoted_from"] = "temporary"
        self._write_registry(registry)
        return {"employee_id": employee_id, **record}

    def archive(self, employee_id: str) -> dict[str, Any]:
        """Archive a one-off employee while keeping its task trace in the registry."""
        registry = self._read_registry()
        record = registry.get(employee_id)
        if record is None:
            raise KeyError(f"员工不存在：{employee_id}")
        if record.get("kind") != "temporary":
            raise ValueError(f"只有临时员工可以归档：{employee_id}")
        record["status"] = "archived"
        self._write_registry(registry)
        return {"employee_id": employee_id, **record}
