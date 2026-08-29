"""Small, auditable method and skill discovery for single-task intake.

The default catalog is local and deterministic, so planning remains usable
offline. Hosts may inject a searcher for fresh web/repository research; its
results are recommendations only and still require user confirmation.
"""

from __future__ import annotations

from typing import Any, Callable


MethodSearcher = Callable[[str, list[str]], list[dict[str, Any]]]
SkillSearcher = Callable[[str, list[str]], list[dict[str, Any]]]

PROGRESSIVE_DISCLOSURE_POLICY = {
    "metadata": "startup_or_inventory",
    "instructions": "load_after_match",
    "references_and_scripts": "load_on_demand",
}

LOCAL_METHODS: dict[str, list[dict[str, Any]]] = {
    "工程": [{
        "name": "规格先行 + 增量实现",
        "approach": "先确认接口、页面状态和验收标准，再分小步实现并回归",
        "skill_ids": ["interview-me", "planning-and-task-breakdown", "test-driven-development", "frontend-ui-engineering"],
        "why": "适合已有项目，能减少需求误解和返工",
        "source": "MakeCrew 内置工程流程",
    }],
    "研究": [{
        "name": "来源驱动研究",
        "approach": "优先查官方文档和一手资料，记录日期、链接与证据边界",
        "skill_ids": ["source-driven-development", "verification-before-completion"],
        "why": "适合需要可核验结论的调研任务",
        "source": "MakeCrew 内置研究流程",
    }],
    "内容": [{
        "name": "受众问题先行",
        "approach": "先明确受众欲望和单一承诺，再产出平台版本并检查事实",
        "skill_ids": ["interview-me", "source-driven-development", "verification-before-completion"],
        "why": "避免同时塞入多个卖点导致表达失焦",
        "source": "MakeCrew 内置内容流程",
    }],
    "设计": [{
        "name": "信息层级 + 目标尺寸验证",
        "approach": "先定信息层级和组件约束，再做目标尺寸预览与可访问性检查",
        "skill_ids": ["frontend-ui-engineering", "verification-before-completion"],
        "why": "适合需要可读、可用和可复用视觉交付的任务",
        "source": "MakeCrew 内置设计流程",
    }],
    "知识库": [{
        "name": "范围盘点 + 抽样核验",
        "approach": "先盘点资料范围和索引，再抽样核对引用与待处理清单",
        "skill_ids": ["source-driven-development", "context-engineering", "verification-before-completion"],
        "why": "控制大规模资料整理的遗漏和上下文成本",
        "source": "MakeCrew 内置知识库流程",
    }],
    "技能": [{
        "name": "触发条件驱动开发",
        "approach": "先定义触发/不触发、输入输出和最小回归，再编写 Skill",
        "skill_ids": ["interview-me", "context-engineering", "verification-before-completion"],
        "why": "让 Skill 在正确任务上触发且方便验证",
        "source": "MakeCrew 内置 Skill 流程",
    }],
}


def _normalize(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "name": str(item.get("name") or item.get("title") or "候选方法").strip(),
        "approach": str(item.get("approach") or item.get("summary") or "待补充").strip(),
        "skill_ids": [str(skill).strip() for skill in item.get("skill_ids", []) if str(skill).strip()],
        "why": str(item.get("why") or item.get("reason") or "与当前任务相关").strip(),
        "source": str(item.get("source") or source).strip(),
    }


def _normalize_skill(item: dict[str, Any]) -> dict[str, str]:
    skill_id = str(item.get("skill_id") or item.get("id") or item.get("name") or "").strip()
    return {
        "skill_id": skill_id,
        "name": str(item.get("name") or skill_id or "候选 Skill").strip(),
        "description": str(item.get("description") or item.get("summary") or item.get("why") or "与当前任务相关").strip(),
        "source": str(item.get("source") or item.get("url") or "宿主搜索结果").strip(),
    }


def discover_methods(
    task: str,
    domains: list[str],
    *,
    searcher: MethodSearcher | None = None,
    search_external: bool | None = None,
) -> dict[str, Any]:
    """Match local methods first, then optionally expand to host search."""
    if domains == ["待澄清"]:
        return {
            "status": "deferred_until_clear",
            "query": task,
            "methods": [],
            "local_match_count": 0,
            "external_searched": False,
            "search_error": "",
        }

    local_methods: list[dict[str, Any]] = []
    for domain in domains:
        local_methods.extend(_normalize(item, source="MakeCrew 内置流程") for item in LOCAL_METHODS.get(domain, []))
    methods: list[dict[str, Any]] = []
    search_error = ""
    should_search_external = searcher is not None and (
        search_external is not False or not local_methods
    )
    external_searched = False
    status = "local_match" if local_methods else "no_local_match"
    if should_search_external:
        external_searched = True
        try:
            methods.extend(_normalize(item, source="宿主搜索结果") for item in (searcher(task, domains) or [])[:4])
            status = "searched"
        except Exception as exc:  # host search is advisory; local planning remains usable
            status = "local_fallback"
            search_error = f"{type(exc).__name__}: {exc}"
    methods.extend(local_methods)
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for method in methods:
        key = (method["name"], method["source"])
        if key not in seen:
            seen.add(key)
            deduped.append(method)
    return {
        "status": status,
        "query": task,
        "methods": deduped[:8],
        "local_match_count": len(local_methods),
        "external_searched": external_searched,
        "search_error": search_error,
    }


def resolve_skills(
    task: str,
    required_skill_ids: list[str],
    installed_skill_ids: list[str],
    *,
    searcher: SkillSearcher | None = None,
    defer: bool = False,
) -> dict[str, Any]:
    """Match installed skills and search only for unresolved capability gaps."""
    required = list(dict.fromkeys(skill_id.strip() for skill_id in required_skill_ids if skill_id.strip()))
    installed = {skill_id.strip() for skill_id in installed_skill_ids if skill_id.strip()}
    if defer:
        return {
            "status": "deferred_until_clear",
            "local_checked": False,
            "required_skill_ids": required,
            "matched_skill_ids": [],
            "missing_skill_ids": required,
            "external_searched": False,
            "candidates": [],
            "search_error": "",
            "requires_user_decision": False,
            "decision_prompt": "",
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    matched = [skill_id for skill_id in required if skill_id in installed]
    missing = [skill_id for skill_id in required if skill_id not in installed]
    if not missing:
        return {
            "status": "local_match",
            "local_checked": True,
            "required_skill_ids": required,
            "matched_skill_ids": matched,
            "missing_skill_ids": [],
            "external_searched": False,
            "candidates": [],
            "search_error": "",
            "requires_user_decision": False,
            "decision_prompt": "",
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    if searcher is None:
        return {
            "status": "search_adapter_required",
            "local_checked": True,
            "required_skill_ids": required,
            "matched_skill_ids": matched,
            "missing_skill_ids": missing,
            "external_searched": False,
            "candidates": [],
            "search_error": "",
            "requires_user_decision": False,
            "decision_prompt": "请启用宿主 Skill 搜索能力，查找缺失能力的候选实现。",
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    try:
        raw_candidates = searcher(task, missing) or []
        candidates = [_normalize_skill(item) for item in raw_candidates[:8]]
        candidates = [item for item in candidates if item["skill_id"]]
        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            key = (candidate["skill_id"], candidate["source"])
            if key not in seen:
                seen.add(key)
                deduped.append(candidate)
    except Exception as exc:
        return {
            "status": "search_failed",
            "local_checked": True,
            "required_skill_ids": required,
            "matched_skill_ids": matched,
            "missing_skill_ids": missing,
            "external_searched": True,
            "candidates": [],
            "search_error": f"{type(exc).__name__}: {exc}",
            "requires_user_decision": False,
            "decision_prompt": "保留已匹配 Skill，修复搜索适配器后继续查找缺失能力。",
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    if not deduped:
        return {
            "status": "no_candidates",
            "local_checked": True,
            "required_skill_ids": required,
            "matched_skill_ids": matched,
            "missing_skill_ids": missing,
            "external_searched": True,
            "candidates": [],
            "search_error": "",
            "requires_user_decision": False,
            "decision_prompt": "当前没有找到合适候选，可调整搜索来源或由现有能力执行。",
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    return {
        "status": "candidates_found",
        "local_checked": True,
        "required_skill_ids": required,
        "matched_skill_ids": matched,
        "missing_skill_ids": missing,
        "external_searched": True,
        "candidates": deduped,
        "search_error": "",
        "requires_user_decision": True,
        "decision_prompt": "本地缺少部分匹配 Skill。请选择是否安装并使用上述候选，或继续使用现有能力。",
        "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
    }
