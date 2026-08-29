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


def plan_request(
    task: str,
    *,
    confirmed: bool = False,
    method_searcher: MethodSearcher | None = None,
) -> dict[str, Any]:
    """Plan one task in the current conversation and gate execution."""
    clean = task.strip()
    plan = route_task(clean)
    questions = _question_for(clean, plan)
    discovery = discover_methods(clean, plan["domains"], searcher=method_searcher)
    public_action = any(word in clean for word in PUBLIC_ACTIONS)
    unclear = plan["needs_clarification"] or (len(clean) < 8 and not public_action)
    requires_confirmation = True

    if unclear:
        status = "needs_clarification"
    elif public_action and confirmed:
        # Production/public changes require a fresh, explicit confirmation
        # after target and rollback details are visible to the user.
        status = "needs_confirmation"
        if "生产发布确认" not in questions:
            questions.append("生产发布确认")
        questions = questions[:MAX_QUESTIONS]
    elif confirmed:
        status = "ready_to_execute"
    else:
        status = "ready_for_confirmation"

    return {
        "task": clean,
        "status": status,
        "single_conversation": True,
        "lead": "当前对话主管",
        "experts": plan["domains"] if plan["domains"] != ["待澄清"] else [],
        "skills": _skills_for(plan["domains"], clean),
        "method_recommendations": discovery["methods"],
        "discovery": {
            "status": discovery["status"],
            "search_error": discovery["search_error"],
            "user_selects_before_execution": True,
        },
        "tools": sorted({tool for item in plan["assignments"] for tool in item["tools"]}),
        "workflow": ["需求澄清", "工具与 Skill 规划", "用户确认", "执行", "验收"],
        "questions": questions,
        "question_details": {
            "生产发布确认": "请确认目标环境、域名/账号、发布版本、发布时间和回滚方案。"
        } if public_action else {},
        "acceptance_gates": plan["acceptance_gates"],
        "workflow_graph": build_workflow(
            plan["assignments"],
            acceptance_gates=plan["acceptance_gates"],
            requires_confirmation=requires_confirmation,
        ),
        "learning_loop": {
            "stage": "after_verification",
            "steps": ["record_score_feedback_root_cause", "propose_small_change", "replay_representative_tasks", "approve_only_if_score_improves"],
            "automatic_mutation": False,
            "storage": ".makecrew/learning.json (optional)",
        },
        "requires_confirmation": requires_confirmation,
        "execute": status == "ready_to_execute",
        "execution_route": "current_conversation_panel",
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
