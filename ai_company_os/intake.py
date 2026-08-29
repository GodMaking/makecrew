"""Single-conversation intake and multi-task batch planning.

This module keeps the common path local to the current conversation. It plans
before execution, asks only for missing decisions, and leaves batch fan-out to
the existing CEO/orchestrator flow.
"""

from __future__ import annotations

from typing import Any

from .router import PUBLIC_ACTIONS, route_task
from .discovery import MethodSearcher, discover_methods
from .workflow import build_workflow


MAX_QUESTIONS = 3

PLAN_FIRST_HINTS = (
    "先给方案", "先出方案", "先别执行", "不要执行", "确认后执行",
    "先规划", "先策划", "先分析方案",
)
DISCOVERY_HINTS = (
    "搜索", "搜一下", "查找", "调研", "研究", "比较", "对比",
    "推荐", "最佳", "最适合", "方法", "skill", "插件", "开源实现", "借鉴",
)
LEARNING_HINTS = (
    "差评", "不合格", "返工", "失败", "重复问题", "复盘", "训练员工",
    "效果差", "没做好", "又错", "垃圾",
)


def _question_for(task: str, plan: dict[str, Any]) -> list[str]:
    questions: list[str] = []
    public_question = any(word in task for word in PUBLIC_ACTIONS)
    if public_question:
        questions.append("生产发布确认")
    if plan["domains"] == ["待澄清"]:
        questions.append("你要的具体结果是什么，交付给谁或用在哪里？")
    if any(word in task for word in ("网站", "应用", "app", "产品")) and not any(word in task for word in ("已有", "项目", "目录", "技术栈")):
        questions.append("这是从零开始，还是基于已有项目？已有项目的目录或技术栈是什么？")
    if not any(word in task for word in ("目标", "用户", "给", "用于", "演示", "上线")):
        questions.append("完成标准是什么？需要达到什么效果或通过哪些检查？")
    return questions[:MAX_QUESTIONS]


def _skills_for(domains: list[str], task: str) -> list[str]:
    mapping = {
        "工程": ["frontend-ui-engineering", "api-and-interface-design", "test-driven-development"],
        "研究": ["web_search", "来源核验"],
        "内容": ["文案结构", "平台适配"],
        "设计": ["frontend-ui-engineering", "imagegen"],
        "知识库": ["知识库检索", "引用整理"],
        "技能": ["skill-creator", "触发验证"],
    }
    skills = [item for domain in domains for item in mapping.get(domain, [])]
    if "浏览器" in task or "网页" in task:
        skills.append("browser")
    return list(dict.fromkeys(skills))


def _request_mode(
    task: str,
    plan: dict[str, Any],
    *,
    unclear: bool,
    capability_gap: bool,
) -> tuple[str, bool, bool]:
    """Return mode, confirmation requirement, and discovery requirement."""
    public_or_strategy = plan["requires_user_confirmation"]
    plan_first = any(hint in task for hint in PLAN_FIRST_HINTS)
    discovery_needed = capability_gap or any(hint in task.lower() for hint in DISCOVERY_HINTS)
    if unclear:
        return "clarify", False, False
    if public_or_strategy:
        return "guarded", True, discovery_needed
    if plan_first:
        return "plan_first", True, discovery_needed
    if len(plan["domains"]) > 1:
        return "team", False, discovery_needed
    if discovery_needed:
        return "discovery", False, True
    return "direct", False, False


def _workflow_for(mode: str, *, learning_signal: bool) -> list[str]:
    workflows = {
        "clarify": ["补充关键信息"],
        "direct": ["执行", "验收", "交付"],
        "discovery": ["方法/Skill 发现", "执行", "验收", "交付"],
        "team": ["动态组队", "并行执行", "统一验收", "交付"],
        "plan_first": ["形成方案", "用户确认", "执行", "验收", "交付"],
        "guarded": ["确认目标与影响", "用户确认", "执行", "验收", "交付"],
    }
    steps = list(workflows[mode])
    if learning_signal:
        steps.append("学习记录")
    return steps


def plan_request(
    task: str,
    *,
    confirmed: bool = False,
    method_searcher: MethodSearcher | None = None,
    learning_signal: bool = False,
    capability_gap: bool = False,
) -> dict[str, Any]:
    """Choose the shortest reliable path for one task."""
    clean = task.strip()
    plan = route_task(clean)
    public_action = any(word in clean for word in PUBLIC_ACTIONS)
    unclear = plan["needs_clarification"] or (len(clean) < 8 and not public_action)
    feedback_signal = any(hint in clean for hint in LEARNING_HINTS)
    learning_enabled = learning_signal or feedback_signal
    mode, requires_confirmation, discovery_needed = _request_mode(
        clean,
        plan,
        unclear=unclear,
        capability_gap=capability_gap,
    )
    questions = _question_for(clean, plan) if unclear else []
    if mode == "guarded" and not confirmed:
        questions = ["生产发布确认"] if public_action else []

    if unclear:
        discovery = discover_methods(clean, ["待澄清"])
    elif discovery_needed:
        discovery = discover_methods(clean, plan["domains"], searcher=method_searcher)
    else:
        discovery = {
            "status": "skipped_not_needed",
            "query": clean,
            "methods": [],
            "search_error": "",
        }

    if unclear:
        status = "needs_clarification"
    elif requires_confirmation and not confirmed:
        status = "ready_for_confirmation"
    else:
        status = "ready_to_execute"

    include_intake = mode in {"clarify", "plan_first", "guarded"}
    workflow_graph = build_workflow(
        plan["assignments"],
        acceptance_gates=plan["acceptance_gates"],
        requires_confirmation=requires_confirmation,
        include_intake=include_intake,
        include_discovery=discovery_needed,
        include_learning=learning_enabled,
    )

    return {
        "task": clean,
        "mode": mode,
        "status": status,
        "single_conversation": True,
        "lead": "当前对话主管",
        "experts": plan["domains"] if plan["domains"] != ["待澄清"] else [],
        "skills": _skills_for(plan["domains"], clean),
        "method_recommendations": discovery["methods"],
        "discovery": {
            "status": discovery["status"],
            "search_error": discovery["search_error"],
            "triggered": discovery_needed,
            "reason": "capability_gap" if capability_gap else "user_request" if discovery_needed else "not_needed",
            "user_selects_before_execution": requires_confirmation,
        },
        "tools": sorted({tool for item in plan["assignments"] for tool in item["tools"]}),
        "workflow": _workflow_for(mode, learning_signal=learning_enabled),
        "questions": questions,
        "question_details": {
            "生产发布确认": "请确认目标环境、域名/账号、发布版本、发布时间和回滚方案。"
        } if public_action else {},
        "acceptance_gates": plan["acceptance_gates"],
        "workflow_graph": workflow_graph,
        "learning_loop": {
            "stage": "on_signal",
            "enabled_for_this_task": learning_enabled,
            "trigger_reason": "explicit_signal" if learning_signal else "task_feedback" if feedback_signal else "none",
            "triggers": ["用户差评", "验收失败", "返工", "重复问题", "用户明确要求复盘"],
            "steps": ["record_score_feedback_root_cause", "propose_small_change", "replay_representative_tasks", "approve_only_if_score_improves"],
            "automatic_mutation": False,
            "storage": ".makecrew/learning.json (optional)",
        },
        "requires_confirmation": requires_confirmation,
        "execute": status == "ready_to_execute",
        "execution_route": "current_conversation_expert_panel" if mode == "team" else "current_conversation",
        "token_policy": "只保留当前任务必要上下文，不复制完整员工历史",
    }


def plan_batch(tasks: list[str]) -> dict[str, Any]:
    """Prepare a multi-task CEO fan-out plan without executing mutations."""
    clean_tasks = [task.strip() for task in tasks if task and task.strip()]
    items = [route_task(task) for task in clean_tasks]
    return {
        "mode": "batch",
        "lead": "CEO",
        "task_count": len(clean_tasks),
        "tasks": items,
        "dispatch_policy": "reuse_existing_then_create_missing_conversations",
        "execute": False,
        "requires_confirmation": True,
        "token_policy": "CEO 只传每项任务的最小任务包，不广播完整历史",
    }
