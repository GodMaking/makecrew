"""Auditable skill bindings for MakeCrew's built-in employee profiles.

The matrix names skills by portable IDs. A host may satisfy an ID with a
bundled MakeCrew skill, an installed platform skill, or a compatible upstream
implementation. The repository never silently downloads third-party code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


BUNDLED_SKILLS = (
    "makecrew", "task-intake", "interview-me", "planning-and-task-breakdown",
    "parallel-dispatch", "verification-before-completion", "test-driven-development",
    "source-driven-development", "frontend-ui-engineering", "api-and-interface-design",
    "git-workflow-and-versioning", "ci-cd-and-automation", "shipping-and-launch",
    "debugging-and-error-recovery", "context-engineering",
)

UPSTREAM_SOURCES: dict[str, dict[str, str]] = {
    "interview-me": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/interview-me",
        "license": "MIT",
        "reason": "逐题澄清需求，减少返工",
    },
    "planning-and-task-breakdown": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/planning-and-task-breakdown",
        "license": "MIT",
        "reason": "把目标拆成可验证任务和依赖",
    },
    "parallel-dispatch": {
        "repository": "obra/superpowers",
        "url": "https://github.com/obra/superpowers/tree/main/skills/dispatching-parallel-agents",
        "license": "MIT",
        "reason": "只并行派发互不依赖的任务",
    },
    "verification-before-completion": {
        "repository": "obra/superpowers",
        "url": "https://github.com/obra/superpowers/tree/main/skills/verification-before-completion",
        "license": "MIT",
        "reason": "用新鲜证据支撑完成声明",
    },
    "test-driven-development": {
        "repository": "obra/superpowers",
        "url": "https://github.com/obra/superpowers/tree/main/skills/test-driven-development",
        "license": "MIT",
        "reason": "先复现/写测试，再实现和回归",
    },
    "source-driven-development": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/source-driven-development",
        "license": "MIT",
        "reason": "基于官方来源并标注证据边界",
    },
    "frontend-ui-engineering": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/frontend-ui-engineering",
        "license": "MIT",
        "reason": "生产级界面、响应式和可访问性检查",
    },
    "api-and-interface-design": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/api-and-interface-design",
        "license": "MIT",
        "reason": "先定契约，再实现边界和错误语义",
    },
    "git-workflow-and-versioning": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/git-workflow-and-versioning",
        "license": "MIT",
        "reason": "小步提交、可回滚和不强推",
    },
    "ci-cd-and-automation": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/ci-cd-and-automation",
        "license": "MIT",
        "reason": "质量门禁通过后再部署",
    },
    "shipping-and-launch": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/shipping-and-launch",
        "license": "MIT",
        "reason": "上线前检查、灰度、监控和回滚",
    },
    "debugging-and-error-recovery": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/debugging-and-error-recovery",
        "license": "MIT",
        "reason": "复现、定位、修复、回归的故障流程",
    },
    "context-engineering": {
        "repository": "addyosmani/agent-skills",
        "url": "https://github.com/addyosmani/agent-skills/tree/main/skills/context-engineering",
        "license": "MIT",
        "reason": "按需加载上下文，控制 Token",
    },
}


EMPLOYEE_SKILL_MATRIX: dict[str, tuple[str, ...]] = {
    "CEO-001": (
        "makecrew", "task-intake", "interview-me", "planning-and-task-breakdown",
        "context-engineering", "verification-before-completion",
    ),
    "PM-001": (
        "makecrew", "task-intake", "planning-and-task-breakdown", "parallel-dispatch",
        "context-engineering", "verification-before-completion",
    ),
    "QA-001": (
        "makecrew", "task-intake", "verification-before-completion", "test-driven-development",
        "debugging-and-error-recovery", "context-engineering",
    ),
    "ENG-001": (
        "task-intake", "test-driven-development", "debugging-and-error-recovery",
        "frontend-ui-engineering", "api-and-interface-design", "git-workflow-and-versioning",
        "ci-cd-and-automation", "shipping-and-launch", "context-engineering",
    ),
    "RES-001": (
        "task-intake", "source-driven-development", "context-engineering",
        "verification-before-completion",
    ),
    "CON-001": (
        "task-intake", "interview-me", "source-driven-development",
        "verification-before-completion", "context-engineering",
    ),
    "DES-001": (
        "task-intake", "frontend-ui-engineering", "verification-before-completion",
        "context-engineering",
    ),
    "KNO-001": (
        "task-intake", "source-driven-development", "context-engineering",
        "verification-before-completion",
    ),
    "SKL-001": (
        "makecrew", "task-intake", "interview-me", "context-engineering",
        "verification-before-completion",
    ),
}


def skill_ids_for_employee(employee_id: str) -> list[str]:
    """Return a copy so callers cannot mutate the canonical matrix."""
    return list(EMPLOYEE_SKILL_MATRIX.get(employee_id, ()))


def audit_employee_capabilities() -> dict[str, Any]:
    """Check that every built-in profile has a non-empty, known skill binding."""
    from .router import CORE_EMPLOYEE_PROFILES, EMPLOYEE_PROFILES

    profiles = [*CORE_EMPLOYEE_PROFILES, *(profile.employee_id for profile in EMPLOYEE_PROFILES.values())]
    missing_profiles = [employee_id for employee_id in profiles if employee_id not in EMPLOYEE_SKILL_MATRIX]
    skill_root = Path(__file__).resolve().parents[1] / "skills"
    required_skill_ids = sorted({skill for employee_id in profiles for skill in EMPLOYEE_SKILL_MATRIX.get(employee_id, ())})
    missing_skill_ids = [
        skill for skill in required_skill_ids
        if not (skill_root / skill / "SKILL.md").is_file()
    ]
    unknown_skill_ids = sorted({skill for employee_id in profiles for skill in EMPLOYEE_SKILL_MATRIX.get(employee_id, ()) if skill not in BUNDLED_SKILLS and skill not in UPSTREAM_SOURCES})
    return {
        "employees": profiles,
        "missing_profiles": missing_profiles,
        "missing_skill_ids": missing_skill_ids,
        "unknown_skill_ids": unknown_skill_ids,
        "required_skill_ids": required_skill_ids,
        "skill_root": str(skill_root),
        "shared_skills": sorted(set.intersection(*(set(EMPLOYEE_SKILL_MATRIX[item]) for item in profiles))),
        "bundled_skills": list(BUNDLED_SKILLS),
        "upstream_sources": UPSTREAM_SOURCES,
    }
