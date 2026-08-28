"""Workspace bootstrap and host capability checks for MakeCrew."""

from __future__ import annotations

import json
from pathlib import Path

from .router import EMPLOYEE_PROFILES


KNOWN_TOOLS = (
    "filesystem",
    "shell",
    "browser",
    "web_search",
    "search",
    "imagegen",
)


def audit_tools(available: list[str] | tuple[str, ...] | set[str]) -> dict[str, list[str]]:
    """Compare host tools with the capabilities used by the default profiles."""
    available_set = {item.strip() for item in available if item and item.strip()}
    required = sorted({tool for profile in EMPLOYEE_PROFILES.values() for tool in profile.tools})
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

    registry = {
        profile.employee_id: {
            "name": profile.name,
            "department": profile.department,
            "skills": list(profile.skills),
            "tools": list(profile.tools),
            "memory_scope": profile.memory_scope,
            "status": profile.status,
        }
        for profile in EMPLOYEE_PROFILES.values()
    }
    registry_path = crew_dir / "employee-registry.json"
    if not registry_path.exists():
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created.append(str(registry_path.relative_to(root)))
    return {"root": str(root), "project": project_name, "created_count": str(len(created))}
