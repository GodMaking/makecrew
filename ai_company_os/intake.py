"""Single-conversation intake and multi-task batch planning.

This module keeps the common path local to the current conversation. It plans
before execution, asks only for missing decisions, and leaves batch fan-out to
the existing CEO/orchestrator flow.
"""

from __future__ import annotations

from typing import Any, Iterable

from .router import PUBLIC_ACTIONS, route_task
from .capabilities import BUNDLED_SKILLS
from .discovery import MethodSearcher, SkillSearcher, discover_methods, resolve_skills
from .workflow import build_workflow


MAX_QUESTIONS_PER_ROUND = 3

# Canonical host Skill IDs. Keep aliases at the boundary so routing never
# invents a Skill name that the host cannot resolve.
SKILL_ALIASES = {
    "browser-control": "browser:control-in-app-browser",
    "computer-control": "computer-use:computer-use",
}

PRODUCT_VERBS = ("开发", "搭建", "创建", "构建", "制作", "实现", "重做", "重构")
PRODUCT_NOUNS = ("网站", "应用", "app", "产品", "软件", "平台")
SMALL_CHANGE_HINTS = ("修复", "排查", "补测试", "改一个", "小改", "微调")

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
DEFAULT_DELEGATION_HINTS = (
    "你决定", "你来定", "你看着办", "自行决定", "按默认", "按最佳实践",
)


def _gap(question_id: str, prompt: str, reason: str) -> dict[str, str]:
    return {"question_id": question_id, "prompt": prompt, "reason": reason}


def _needs_product_delivery(task: str, *, delegated_defaults: bool = False) -> bool:
    """Detect substantial product work that benefits from design-before-code."""
    normalized = task.lower()
    return (
        not delegated_defaults
        and any(word in normalized for word in PRODUCT_VERBS)
        and any(word in normalized for word in PRODUCT_NOUNS)
        and not any(word in normalized for word in SMALL_CHANGE_HINTS)
    )


def _clarification_gaps(task: str, plan: dict[str, Any]) -> list[dict[str, str]]:
    """Return material decision gaps in priority order."""
    normalized = task.lower()
    domains = plan["domains"]
    gaps: list[dict[str, str]] = []
    if domains == ["待澄清"]:
        gaps.append(_gap(
            "outcome",
            "你最终希望得到什么具体结果？它要解决什么问题？",
            "目标产物和问题尚未明确",
        ))
        gaps.append(_gap(
            "starting_context",
            "这是从零开始，还是基于已有内容、文件或项目？请给出相关位置或现状。",
            "起点会改变执行方法",
        ))

    product_work = "工程" in domains and any(word in normalized for word in ("网站", "应用", "app", "产品", "页面"))
    if product_work and not any(word in normalized for word in ("已有", "现有", "从零", "新建", "目录", "代码库", "技术栈", "基于")):
        gaps.append(_gap(
            "project_basis",
            "这是从零开始，还是基于已有项目？已有项目的目录和技术栈是什么？",
            "项目基础决定实现路径",
        ))

    if not any(word in normalized for word in ("用户", "受众", "客户", "给", "用于", "面向", "内部", "自己")):
        gaps.append(_gap(
            "audience_and_use",
            "谁会使用这个结果，主要在什么场景下使用？",
            "使用者和场景会影响内容与实现取舍",
        ))
    if not any(word in normalized for word in ("验收", "完成标准", "达到", "通过", "效果", "演示", "上线")):
        gaps.append(_gap(
            "success_criteria",
            "你怎样判断它已经做好？最重要的验收标准是什么？",
            "缺少可验证的完成定义",
        ))
    if not any(word in normalized for word in ("限制", "约束", "必须", "预算", "兼容", "隐私", "技术栈", "格式", "尺寸")):
        gaps.append(_gap(
            "constraints",
            "有哪些必须遵守的技术、预算、隐私、格式或兼容性要求？没有可写“由你决定”。",
            "关键约束可能改变方案",
        ))
    if not any(word in normalized for word in ("截止", "今天", "明天", "本周", "下周", "日期", "时间", "尽快")):
        gaps.append(_gap(
            "deadline",
            "有明确截止时间或优先级吗？",
            "时间会影响范围和执行顺序",
        ))
    if product_work and not any(word in normalized for word in ("方案", "原型", "可运行", "完整版本", "最小版本", "mvp", "上线")):
        gaps.append(_gap(
            "delivery_depth",
            "这次先交方案、原型、最小可用版本，还是完整可运行版本？",
            "交付深度决定工作量和验收范围",
        ))
    return gaps


def _merge_material_gaps(
    builtin: Iterable[dict[str, str]],
    supplied: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    """Merge host-model gaps by stable ID while preserving priority order."""
    merged: dict[str, dict[str, str]] = {}
    for item in [*builtin, *supplied]:
        question_id = str(item.get("question_id", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        if not question_id or not prompt:
            continue
        merged[question_id] = {
            "question_id": question_id,
            "prompt": prompt,
            "reason": str(item.get("reason", "影响任务决策")).strip(),
        }
    return list(merged.values())


def _skills_for(domains: list[str], task: str) -> list[str]:
    mapping = {
        "工程": [
            "test-driven-development", "debugging-and-error-recovery",
            "frontend-ui-engineering", "api-and-interface-design",
        ],
        "研究": ["source-driven-development", "verification-before-completion"],
        "内容": ["interview-me", "source-driven-development", "verification-before-completion"],
        "设计": ["frontend-ui-engineering", "verification-before-completion"],
        "知识库": ["source-driven-development", "context-engineering", "verification-before-completion"],
        "技能": ["interview-me", "context-engineering", "verification-before-completion"],
    }
    skills = [item for domain in domains for item in mapping.get(domain, [])]
    normalized = task.lower()
    if "浏览器" in normalized:
        skills.append(SKILL_ALIASES["browser-control"])
    if any(word in normalized for word in ("上线", "部署", "发布到生产")):
        skills.extend(["ci-cd-and-automation", "shipping-and-launch"])
    if any(word in normalized for word in ("github", "git ", "提交代码", "推送代码")):
        skills.append("git-workflow-and-versioning")
    if "skill" in normalized and "技能" in domains:
        skills.append("skill-creator")
    return list(dict.fromkeys(skills))


def _request_mode(
    task: str,
    plan: dict[str, Any],
    *,
    unclear: bool,
    capability_gap: bool,
    delegated_defaults: bool = False,
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
    if _needs_product_delivery(task, delegated_defaults=delegated_defaults):
        return "product_delivery", True, discovery_needed
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
        "product_delivery": [
            "需求澄清", "产品简报", "Demo/原型", "技术方案", "用户确认",
            "执行", "验收", "交付",
        ],
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
    skill_searcher: SkillSearcher | None = None,
    installed_skill_ids: Iterable[str] | None = None,
    learning_signal: bool = False,
    capability_gap: bool = False,
    clarification_round: int = 1,
    answered_question_ids: Iterable[str] = (),
    material_gaps: Iterable[dict[str, Any]] = (),
    answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Choose the shortest reliable path for one task."""
    clean = task.strip()
    answer_values = {
        str(key).strip(): str(value).strip()
        for key, value in (answers or {}).items()
        if str(key).strip() and str(value).strip()
    }
    # Answers are kept as compact planning context. The original task remains
    # the user-facing value and is never replaced by the questionnaire.
    planning_text = clean
    if answer_values:
        planning_text += "\n" + "\n".join(f"{key}: {value}" for key, value in answer_values.items())
    plan = route_task(planning_text)
    public_action = any(word in clean for word in PUBLIC_ACTIONS)
    if clarification_round < 1:
        raise ValueError("澄清轮次必须大于 0")
    answered_ids = {str(item).strip() for item in answered_question_ids if str(item).strip()}
    answered_ids.update(answer_values)
    supplied_gaps = list(material_gaps)
    delegated_defaults = any(hint in clean for hint in DEFAULT_DELEGATION_HINTS)
    product_bootstrap = _needs_product_delivery(clean, delegated_defaults=delegated_defaults)
    base_unclear = (
        plan["needs_clarification"]
        or (len(clean) < 8 and not public_action)
        or bool(supplied_gaps)
        or product_bootstrap
    )
    builtin_gaps = _clarification_gaps(clean, plan) if base_unclear or answered_ids or clarification_round > 1 else []
    all_gaps = _merge_material_gaps(builtin_gaps, supplied_gaps)
    pending_gaps = [gap for gap in all_gaps if gap["question_id"] not in answered_ids]
    unclear = base_unclear and bool(pending_gaps) and not delegated_defaults
    round_gaps = pending_gaps[:MAX_QUESTIONS_PER_ROUND] if unclear else []
    feedback_signal = any(hint in clean for hint in LEARNING_HINTS)
    learning_enabled = learning_signal or feedback_signal
    mode, requires_confirmation, discovery_needed = _request_mode(
        clean,
        plan,
        unclear=unclear,
        capability_gap=capability_gap,
        delegated_defaults=delegated_defaults,
    )
    questions = [gap["prompt"] for gap in round_gaps]
    if mode == "guarded" and not confirmed:
        questions = ["生产发布确认"] if public_action else []

    required_skills = _skills_for(plan["domains"], clean)
    if mode == "product_delivery":
        required_skills.insert(0, "product-delivery")
        required_skills = list(dict.fromkeys(required_skills))
    installed_inventory = list(BUNDLED_SKILLS if installed_skill_ids is None else installed_skill_ids)
    if unclear:
        discovery = discover_methods(clean, ["待澄清"])
    else:
        discovery = discover_methods(
            clean,
            plan["domains"],
            searcher=method_searcher,
            search_external=discovery_needed,
        )
    skill_resolution = resolve_skills(
        clean,
        required_skills,
        installed_inventory,
        searcher=skill_searcher,
        defer=unclear,
    )
    skill_choice_needed = skill_resolution["requires_user_decision"]
    skill_gap_unresolved = skill_resolution["status"] in {
        "search_adapter_required", "search_failed", "no_candidates",
    }

    if unclear:
        status = "needs_clarification"
    elif skill_choice_needed:
        status = "ready_for_skill_choice"
    elif skill_gap_unresolved:
        status = "skill_search_required"
    elif requires_confirmation and not confirmed:
        status = "ready_for_confirmation"
    else:
        status = "ready_to_execute"

    include_intake = mode in {"clarify", "plan_first", "product_delivery", "guarded"}
    external_discovery_used = discovery["external_searched"] or skill_resolution["external_searched"]
    workflow_graph = build_workflow(
        plan["assignments"],
        acceptance_gates=plan["acceptance_gates"],
        requires_confirmation=requires_confirmation,
        include_intake=include_intake,
        include_discovery=external_discovery_used or skill_gap_unresolved,
        include_learning=learning_enabled,
    )
    workflow_steps = _workflow_for(mode, learning_signal=learning_enabled)
    if skill_choice_needed or skill_gap_unresolved:
        workflow_steps.insert(0, "Skill 匹配与选择")

    return {
        "task": clean,
        "mode": mode,
        "status": status,
        "single_conversation": True,
        "lead": "当前对话主管",
        "experts": plan["domains"] if plan["domains"] != ["待澄清"] else [],
        "skills": required_skills,
        "skill_resolution": skill_resolution,
        "method_recommendations": discovery["methods"],
        "discovery": {
            "status": discovery["status"],
            "search_error": discovery["search_error"],
            "triggered": not unclear,
            "external_triggered": discovery["external_searched"],
            "local_match_count": discovery["local_match_count"],
            "reason": (
                "capability_gap" if capability_gap
                else "user_request" if discovery_needed
                else "no_local_match" if discovery["local_match_count"] == 0
                else "task_local_match"
            ),
            "user_selects_before_execution": skill_choice_needed,
        },
        "tools": sorted({tool for item in plan["assignments"] for tool in item["tools"]}),
        "workflow": workflow_steps,
        "questions": questions,
        "clarification": {
            "round": clarification_round,
            "ready": not unclear,
            "questions_per_round": MAX_QUESTIONS_PER_ROUND,
            "max_total_questions": None,
            "question_ids": [gap["question_id"] for gap in round_gaps],
            "all_question_ids": [gap["question_id"] for gap in all_gaps],
            "answered_question_ids": sorted(answered_ids),
            "answer_values": dict(answer_values),
            "answer_values_complete": not any(
                gap["question_id"] in answered_ids and gap["question_id"] not in answer_values
                for gap in all_gaps
            ),
            "remaining_question_ids": [gap["question_id"] for gap in pending_gaps],
            "has_more": len(pending_gaps) > len(round_gaps),
            "stop_reason": (
                "delegated_defaults" if delegated_defaults
                else "all_material_gaps_resolved" if base_unclear and not pending_gaps
                else "decision_ready" if not base_unclear
                else "awaiting_answers"
            ),
            "policy": "iterate_until_decision_ready",
            "gap_source": "builtin_and_host" if supplied_gaps and builtin_gaps else "host" if supplied_gaps else "builtin",
        },
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
        "requires_skill_confirmation": skill_choice_needed,
        "execute": status == "ready_to_execute",
        "execution_route": "current_conversation_expert_panel" if mode == "team" else "current_conversation",
        "token_policy": "只保留当前任务必要上下文，不复制完整员工历史",
        "product_delivery": {
            "triggered": product_bootstrap,
            "artifacts": [
                "project-brief.md", "product-demo.md", "technical-design.md",
                "verification-report.md",
            ] if mode == "product_delivery" else [],
        },
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
