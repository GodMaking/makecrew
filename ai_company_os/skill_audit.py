"""Dependency-free validation for portable ``SKILL.md`` directories."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
PROGRESSIVE_DIRS = ("references", "scripts", "assets")


def _issue(code: str, message: str, *, path: Path) -> dict[str, str]:
    return {"code": code, "message": message, "path": str(path)}


def _frontmatter(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Read the small YAML subset used by the Agent Skills frontmatter."""
    issues: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {}, [_issue("unreadable_skill", f"无法读取 SKILL.md：{exc}", path=path)]
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, [_issue("missing_frontmatter", "SKILL.md 必须以 YAML frontmatter 开始", path=path)]
    end = next((index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if end is None:
        return {}, [_issue("unclosed_frontmatter", "YAML frontmatter 缺少结束标记", path=path)]
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            issues.append(_issue("invalid_frontmatter", "frontmatter 只支持顶层 key: value 字段", path=path))
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if not key:
            issues.append(_issue("invalid_frontmatter", "frontmatter 字段名不能为空", path=path))
            continue
        if value.startswith(("|", ">")):
            issues.append(_issue("unsupported_frontmatter", f"字段 {key} 使用了未支持的多行 YAML 值", path=path))
            continue
        values[key] = value.strip("'\"")
    return values, issues


def audit_skill_file(skill_file: str | Path) -> dict[str, Any]:
    """Validate one skill and report metadata without loading referenced files."""
    path = Path(skill_file).expanduser().resolve()
    issues: list[dict[str, str]] = []
    metadata, frontmatter_issues = _frontmatter(path)
    issues.extend(frontmatter_issues)
    skill_dir = path.parent
    declared_name = metadata.get("name", "").strip()
    description = metadata.get("description", "").strip()
    if not declared_name:
        issues.append(_issue("missing_name", "frontmatter 缺少 name", path=path))
    elif len(declared_name) > MAX_NAME_LENGTH or not NAME_RE.fullmatch(declared_name):
        issues.append(_issue("invalid_name", "name 必须使用小写字母、数字和单个连字符", path=path))
    if not description:
        issues.append(_issue("missing_description", "frontmatter 缺少 description", path=path))
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        issues.append(_issue("description_too_long", "description 不能超过 1024 个字符", path=path))
    if path.name != "SKILL.md":
        issues.append(_issue("invalid_filename", "Skill 文件名必须是 SKILL.md", path=path))
    if declared_name and skill_dir.name != declared_name:
        issues.append(_issue("directory_name_mismatch", "目录名应与 frontmatter 的 name 一致", path=path))
    progressive = {
        name: "available" if (skill_dir / name).is_dir() else "absent"
        for name in PROGRESSIVE_DIRS
    }
    return {
        "path": str(path),
        "skill_id": declared_name or skill_dir.name,
        "status": "review" if issues else "pass",
        "metadata": {"name": declared_name, "description": description},
        "progressive_disclosure": progressive,
        "issues": issues,
    }


def audit_skill_directory(root: str | Path) -> dict[str, Any]:
    """Audit each immediate skill directory and continue after individual errors."""
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise NotADirectoryError(str(base))
    files = sorted(
        (path / "SKILL.md" for path in base.iterdir() if path.is_dir()),
        key=lambda item: str(item.parent).casefold(),
    )
    reports = [audit_skill_file(path) if path.is_file() else {
        "path": str(path),
        "skill_id": path.parent.name,
        "status": "review",
        "metadata": {"name": "", "description": ""},
        "progressive_disclosure": {name: "absent" for name in PROGRESSIVE_DIRS},
        "issues": [_issue("missing_skill_file", "Skill 目录缺少 SKILL.md", path=path)],
    } for path in files]
    pass_count = sum(report["status"] == "pass" for report in reports)
    return {
        "root": str(base),
        "skill_count": len(reports),
        "pass_count": pass_count,
        "review_count": len(reports) - pass_count,
        "status": "pass" if pass_count == len(reports) else "review",
        "skills": reports,
    }


def inventory_skill_directory(root: str | Path) -> dict[str, Any]:
    """Return a metadata-only local Skill inventory for host adapters.

    The inventory deliberately reuses the structural audit and never loads the
    instruction body, references, scripts, or assets. Only passing entries are
    advertised as ready for matching; entries needing review remain visible so
    a host can report the exact path and issue instead of silently ignoring it.
    """
    audit = audit_skill_directory(root)
    skills = [
        {
            "skill_id": report["skill_id"],
            "name": report["metadata"]["name"],
            "description": report["metadata"]["description"],
            "path": report["path"],
            "status": report["status"],
            "progressive_disclosure": dict(report["progressive_disclosure"]),
            "issues": list(report["issues"]),
        }
        for report in audit["skills"]
    ]
    return {
        "root": audit["root"],
        "status": "ready" if audit["status"] == "pass" else "review_required",
        "skill_count": audit["skill_count"],
        "ready_count": audit["pass_count"],
        "review_count": audit["review_count"],
        "ready_skill_ids": [item["skill_id"] for item in skills if item["status"] == "pass"],
        "review_skill_ids": [item["skill_id"] for item in skills if item["status"] != "pass"],
        "skills": skills,
        "load_policy": {
            "metadata": "loaded",
            "instructions": "load_after_match",
            "references_and_scripts": "load_on_demand",
        },
    }
