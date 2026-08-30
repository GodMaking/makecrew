"""Workspace bootstrap and host capability checks for MakeCrew."""

from __future__ import annotations

import json
from pathlib import Path

from .router import CORE_EMPLOYEE_PROFILES, EMPLOYEE_PROFILES, EmployeeProfile
from .capabilities import skill_ids_for_employee


KNOWN_TOOLS = (
    "filesystem",
    "shell",
    "browser",
    "web_search",
    "search",
    "imagegen",
)


def _default_profiles() -> dict[str, dict]:
    """Return immutable-by-convention role templates for user review.

    Templates describe available roles; they are not employee instances and
    therefore must not create host conversations or active registry entries.
    """
    return {
        profile.employee_id: {
            "name": profile.name,
            "department": profile.department,
            "skills": list(profile.skills),
            "tools": list(profile.tools),
            "memory_scope": profile.memory_scope,
            "status": profile.status,
            "kind": profile.kind,
            "skill_ids": skill_ids_for_employee(profile.employee_id),
        }
        for profile in [*CORE_EMPLOYEE_PROFILES.values(), *EMPLOYEE_PROFILES.values()]
    }


def audit_tools(available: list[str] | tuple[str, ...] | set[str]) -> dict[str, list[str]]:
    """Compare host tools with the capabilities used by the default profiles."""
    available_set = {item.strip() for item in available if item and item.strip()}
    required = sorted({
        tool
        for profile in [*CORE_EMPLOYEE_PROFILES.values(), *EMPLOYEE_PROFILES.values()]
        for tool in profile.tools
    })
    return {
        "available": sorted(available_set),
        "required": required,
        "missing": [tool for tool in required if tool not in available_set],
        "unknown": sorted(available_set - set(KNOWN_TOOLS)),
    }


def initialize_workspace(base_dir: str | Path, *, project: str = "main") -> dict[str, str]:
    """Create a minimal local MakeCrew workspace without touching existing files."""
    root = Path(base_dir).expanduser().resolve()
    project_name = project.strip() or "main"
    crew_dir = root / ".makecrew"
    project_dir = crew_dir / "projects" / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    files = {
        crew_dir / "company-memory.md": "# Company Memory\n\n记录稳定偏好、质量规则、成本规则和公司级决策。\n",
        project_dir / "context-pack.md": f"# Project Context: {project_name}\n\n记录目标、路径、技术栈、约束和完成定义。\n",
        crew_dir / "tasks.json": "[]\n",
        crew_dir / "learning.json": '{"records": [], "proposals": []}\n',
    }
    created = []
    for path, content in files.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(str(path.relative_to(root)))

    default_templates = _default_profiles()
    templates_path = crew_dir / "employee-templates.json"
    if not templates_path.exists():
        templates_path.write_text(json.dumps(default_templates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created.append(str(templates_path.relative_to(root)))
    registry_path = crew_dir / "employee-registry.json"
    if not registry_path.exists():
        # A fresh install has no employees yet. Templates are opt-in and only
        # become employees after the user reviews and approves a proposal.
        registry_path.write_text("{}\n", encoding="utf-8")
        created.append(str(registry_path.relative_to(root)))
    else:
        # Upgrade an existing workspace additively. Existing employees,
        # ordinary conversations, project memory, and user settings win.
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        changed = False
        # Only enrich entries that already exist; never create a role silently.
        for employee_id, record in registry.items():
            template = default_templates.get(employee_id, {})
            if "kind" not in record and template.get("kind"):
                record["kind"] = template["kind"]
                changed = True
            if "skill_ids" not in record and template.get("skill_ids"):
                record["skill_ids"] = template["skill_ids"]
                changed = True
        if changed:
            registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"root": str(root), "project": project_name, "created_count": str(len(created)), "employee_count": str(len(json.loads(registry_path.read_text(encoding="utf-8"))))}


def register_employee(
    base_dir: str | Path,
    profile: EmployeeProfile | dict,
    *,
    approved: bool = False,
) -> dict[str, str]:
    """Add one user-selected employee without replacing core roles or templates.

    The registry is intentionally additive. Existing project memory and role
    definitions remain untouched, while a custom employee gets the same
    capability contract as the built-in profiles.
    """
    if not approved:
        raise ValueError("创建员工前必须先展示提案并取得用户同意；请传入 approved=True")
    root = Path(base_dir).expanduser().resolve()
    registry_path = root / ".makecrew" / "employee-registry.json"
    if not registry_path.exists():
        initialize_workspace(root)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if isinstance(profile, EmployeeProfile):
        record = {
            "name": profile.name,
            "department": profile.department,
            "skills": list(profile.skills),
            "tools": list(profile.tools),
            "memory_scope": profile.memory_scope,
            "status": profile.status,
            "kind": "custom",
        }
        employee_id = profile.employee_id
    else:
        employee_id = str(profile.get("employee_id", "")).strip()
        record = {
            "name": str(profile.get("name", "")).strip(),
            "department": str(profile.get("department", "")).strip(),
            "skills": list(profile.get("skills", [])),
            "tools": list(profile.get("tools", [])),
            "memory_scope": str(profile.get("memory_scope", "project")),
            "status": str(profile.get("status", "active")),
            "kind": "custom",
        }
    if not employee_id or not record["name"] or not record["department"]:
        raise ValueError("自定义员工至少需要 employee_id、name 和 department")
    if employee_id in CORE_EMPLOYEE_PROFILES or employee_id in registry:
        raise ValueError(f"员工 ID 已存在或属于核心岗位：{employee_id}")
    registry[employee_id] = record
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"employee_id": employee_id, "kind": "custom", "registry": str(registry_path)}
