"""Small, auditable method and skill discovery for single-task intake.

The default catalog is local and deterministic, so planning remains usable
offline. Hosts may inject a searcher for fresh web/repository research; its
results are recommendations only and still require user confirmation.
"""

from __future__ import annotations

from typing import Any, Callable


MethodSearcher = Callable[[str, list[str]], list[dict[str, Any]]]

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


def discover_methods(
    task: str,
    domains: list[str],
    *,
    searcher: MethodSearcher | None = None,
) -> dict[str, Any]:
    """Return local recommendations plus optional host-provided search results."""
    if domains == ["待澄清"]:
        return {"status": "deferred_until_clear", "query": task, "methods": [], "search_error": ""}

    local_methods: list[dict[str, Any]] = []
    for domain in domains:
        local_methods.extend(_normalize(item, source="MakeCrew 内置流程") for item in LOCAL_METHODS.get(domain, []))
    methods: list[dict[str, Any]] = []
    search_error = ""
    status = "ready"
    if searcher is not None:
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
    return {"status": status, "query": task, "methods": deduped[:8], "search_error": search_error}
