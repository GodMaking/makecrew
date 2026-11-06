"""Map AgentFlow employee identities to least-privilege RAG scopes."""

from __future__ import annotations

from typing import Any, Iterable

from .rag import RetrievalScope
from .router import CORE_EMPLOYEE_PROFILES, EMPLOYEE_PROFILES


CORE_ACTORS = {"CEO-001": "ceo", "PM-001": "manager", "QA-001": "employee"}
BUILTIN_EMPLOYEE_IDS = set(CORE_EMPLOYEE_PROFILES) | {
    profile.employee_id for profile in EMPLOYEE_PROFILES.values()
}


def scope_for_employee(
    employee_id: str,
    *,
    project_ids: Iterable[str] = (),
    memory_scope: str = "project",
    actor: str | None = None,
    max_results: int = 8,
    max_chars: int = 20_000,
) -> RetrievalScope:
    """Return a scope for a task packet, failing closed on unknown identities."""
    employee_id = employee_id.strip()
    if not employee_id:
        raise ValueError("employee_id 不能为空")
    resolved_actor = actor.strip() if actor else CORE_ACTORS.get(employee_id)
    if resolved_actor is None and employee_id in BUILTIN_EMPLOYEE_IDS:
        resolved_actor = "employee"
    if resolved_actor not in {"ceo", "manager", "employee", "task"}:
        raise ValueError("未知员工身份：请显式提供受支持的 actor")
    projects = tuple(item.strip() for item in project_ids if item and item.strip())
    include_company = memory_scope in {"company", "company_and_project"} or resolved_actor == "ceo"
    if memory_scope not in {"company", "project", "company_and_project"}:
        raise ValueError("memory_scope 必须是 company、project 或 company_and_project")
    return RetrievalScope(
        actor=resolved_actor,
        project_ids=projects,
        include_company=include_company,
        max_results=max_results,
        max_chars=max_chars,
    )


def scope_payload(scope: RetrievalScope) -> dict[str, Any]:
    """Serialize a scope for a host dispatcher without leaking full memory."""
    return {
        "actor": scope.actor,
        "project_ids": list(scope.project_ids),
        "include_company": scope.include_company,
        "include_archived": scope.include_archived,
        "include_inactive": scope.include_inactive,
        "max_results": scope.max_results,
        "max_chars": scope.max_chars,
    }

