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
from .capabilities import skill_ids_for_employee


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

    @staticmethod
    def _proposal_id(task: str, domain: str, employee_id: str = "") -> str:
        if employee_id:
            return employee_id
        signature = hashlib.sha1(f"{domain}:{task.strip()}".encode("utf-8")).hexdigest()[:8].upper()
        return f"TEMP-{signature}"

    def _employee_proposal(
        self, task: str, domain: str, source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Describe a missing employee without creating a registry entry."""
        source = source or {}
        profile = EMPLOYEE_PROFILES.get(domain) or CORE_EMPLOYEE_PROFILES.get(source.get("employee_id", ""))
        employee_id = self._proposal_id(task, domain, str(source.get("employee_id", "")).strip())
        if profile:
            name = profile.name
            department = profile.department
            skills = list(profile.skills)
            tools = list(profile.tools)
            memory_scope = profile.memory_scope
            skill_ids = skill_ids_for_employee(profile.employee_id)
            kind = "core" if profile.employee_id in CORE_EMPLOYEE_PROFILES else "custom"
        else:
            name = f"{domain or '临时任务'}员工"
            department = domain or "临时任务"
            skills = list(source.get("required_skills", [])) or ["根据任务补齐专长"]
            tools = list(source.get("tools", [])) or ["filesystem"]
            memory_scope = str(source.get("memory_scope", "project"))
            skill_ids = list(source.get("skill_ids", []))
            kind = "temporary"
        objective = str(source.get("objective", f"完成任务中的{domain or '未分类'}部分"))
        output = str(source.get("output", "结果、证据和下一步"))
        return {
            "employee_id": employee_id,
            "name": name,
            "department": department,
            "reason": f"当前工作区没有可复用的{department}员工，而本任务需要该岗位完成：{objective}。",
            "responsibilities": [objective, f"提交{output}"],
            "required_skills": skills,
            "skill_ids": skill_ids,
            "tools": tools,
            "memory_scope": memory_scope,
            "estimated_cost": "仅在批准后创建并执行；新增一次岗位配置和对应任务调用，具体 Token 取决于任务轮次与工具调用。",
            "impact": "只新增一个注册表条目和项目线程；保留已有普通对话、员工、项目记忆和配置，不覆盖或删除任何内容。",
            "kind": kind,
            "status": "awaiting_user_approval",
            "created_for": task.strip(),
        }

    def _activate_proposal(self, proposal: dict[str, Any], registry: dict[str, dict[str, Any]]) -> None:
        """Materialize exactly one user-approved proposal."""
        employee_id = proposal["employee_id"]
        if employee_id in registry and self._active(registry[employee_id]):
            return
        registry[employee_id] = {
            "name": proposal["name"],
            "department": proposal["department"],
            "skills": list(proposal["required_skills"]),
            "tools": list(proposal["tools"]),
            "memory_scope": proposal["memory_scope"],
            "status": "active",
            "kind": proposal["kind"],
            "skill_ids": list(proposal["skill_ids"]),
            "created_for": proposal["created_for"],
        }

    def _execute(self, employee_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.dispatcher is None:
            return {"status": "queued", "employee_id": employee_id}
        result = self.dispatcher(employee_id, payload)
        if isinstance(result, dict):
            return {"employee_id": employee_id, **result}
        return {"employee_id": employee_id, "status": "completed", "result": result}

    def dispatch(
        self,
        task: str,
        *,
        project: str = "",
        approved_employee_ids: list[str] | tuple[str, ...] | None = None,
        employee_approval: bool = False,
    ) -> dict[str, Any]:
        """Delegate work, waiting for explicit approval when a role is missing."""
        plan = route_task(task, project)
        registry = self._read_registry()
        assignments: list[dict[str, Any]] = []
        proposals: list[dict[str, Any]] = []

        # A CEO decision remains a management action. The project manager is
        # the execution coordinator; specialists handle any later work items.
        if plan["route"] == "ceo":
            employee_id = "PM-001"
            assignment = {
                "role": "项目主管",
                "objective": "把 CEO 决策拆成可执行任务",
                "output": "任务拆解、负责人和依赖",
                "employee_id": employee_id,
                "skill_ids": skill_ids_for_employee(employee_id),
            }
            if employee_id in registry and self._active(registry[employee_id]):
                assignments.append({**assignment, "dispatch_mode": "existing"})
            else:
                proposal = self._employee_proposal(task, "管理", assignment)
                proposals.append(proposal)
                assignments.append({**assignment, "dispatch_mode": "proposed"})
        else:
            domains = plan["domains"]
            if domains == ["待澄清"]:
                domains = ["待澄清"]
            for index, domain in enumerate(domains):
                employee_id = self._find_employee(domain, registry) if domain in EMPLOYEE_PROFILES else None
                dispatch_mode = "existing"
                source = plan["assignments"][index] if index < len(plan["assignments"]) else {
                    "role": "临时任务员工",
                    "objective": "完成任务并提交可复核结果",
                    "output": "结果、证据和下一步",
                    "required_skills": [],
                    "tools": ["filesystem"],
                }
                if employee_id is None:
                    proposal = self._employee_proposal(task, domain, source)
                    proposals.append(proposal)
                    employee_id = proposal["employee_id"]
                    dispatch_mode = "proposed"
                assignments.append({
                    **source,
                    "employee_id": employee_id,
                    "dispatch_mode": dispatch_mode,
                })

        approved = set(approved_employee_ids or [])
        if employee_approval:
            approved.update(proposal["employee_id"] for proposal in proposals)
        pending_ids = {proposal["employee_id"] for proposal in proposals} - approved
        if pending_ids:
            return {
                "task": task.strip(),
                "project": project,
                "route": plan["route"],
                "lead": plan["lead"],
                "status": "awaiting_employee_approval",
                "ceo_action": "propose_and_wait",
                "dispatch_mode": "proposed",
                "executor_id": "",
                "executor_ids": [],
                "assignments": assignments,
                "employee_proposals": proposals,
                "execution": {"status": "awaiting_user_approval", "pending_employee_ids": sorted(pending_ids)},
                "verification": plan["verification_contract"],
                "acceptance_gates": plan["acceptance_gates"],
                "next_action": "请逐项查看员工提案；批准后再次派发，或一次批准全部提案。",
            }

        for proposal in proposals:
            self._activate_proposal(proposal, registry)
            proposal["status"] = "created_after_user_approval"
        if proposals:
            self._write_registry(registry)
            proposal_ids = {proposal["employee_id"] for proposal in proposals}
            assignments = [
                {**assignment, "dispatch_mode": "created_after_approval" if assignment["employee_id"] in proposal_ids else assignment["dispatch_mode"]}
                for assignment in assignments
            ]

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
            "status": "dispatched",
            "ceo_action": "delegate",
            "dispatch_mode": mode,
            "executor_id": assignments[0]["employee_id"] if assignments else "",
            "executor_ids": [assignment["employee_id"] for assignment in assignments],
            "assignments": assignments,
            "employee_proposals": proposals,
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
