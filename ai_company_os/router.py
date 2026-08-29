"""Rule-based task routing for the MakeCrew MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass


# These roles are the smallest complete operating loop. Specialist roles are
# templates only: a workspace may add zero, one, or many of each.
CORE_ROLES = ("CEO", "项目主管", "验收员")


DOMAIN_RULES = {
    "工程": ("工程员工", ("开发", "代码", "网站", "app", "应用", "测试", "部署", "修复", "登录", "页面", "接口")),
    "研究": ("研究员工", ("研究", "搜索", "调研", "分析", "资料", "竞品", "数据", "趋势")),
    "内容": ("内容员工", ("文案", "标题", "脚本", "宣传", "内容", "公众号", "小红书", "抖音", "视频")),
    "设计": ("设计员工", ("设计", "封面", "视觉", "logo", "界面", "ui", "配图")),
    "知识库": ("知识库员工", ("知识库", "整理", "归档", "索引", "书籍", "资料库")),
    "技能": ("Skill员工", ("skill", "技能", "skill.md", "能力套件", "技能包", "插件能力")),
}

CEO_KEYWORDS = ("优先级", "预算", "战略", "季度", "跨项目", "投入产出", "资源分配", "方向")
PUBLIC_ACTIONS = ("上线", "发布", "公开", "投放", "付款", "删除")


@dataclass(frozen=True)
class EmployeeProfile:
    """The minimum capability contract used for deterministic routing."""

    employee_id: str
    name: str
    department: str
    skills: tuple[str, ...]
    tools: tuple[str, ...]
    memory_scope: str
    status: str = "active"
    kind: str = "specialist_template"


CORE_EMPLOYEE_PROFILES = {
    "CEO-001": EmployeeProfile(
        "CEO-001", "CEO", "管理", ("目标澄清", "优先级", "资源分配"),
        ("filesystem", "search"), "company_and_project", kind="core"
    ),
    "PM-001": EmployeeProfile(
        "PM-001", "项目主管", "管理", ("拆解", "动态组队", "差量交接"),
        ("filesystem", "search"), "project", kind="core"
    ),
    "QA-001": EmployeeProfile(
        "QA-001", "验收员", "质量", ("验收", "证据核验", "质量门禁"),
        ("filesystem", "browser", "search"), "project", kind="core"
    ),
}


EMPLOYEE_PROFILES = {
    "工程": EmployeeProfile("ENG-001", "工程员工", "工程", ("代码", "测试", "部署"), ("shell", "filesystem", "browser"), "project"),
    "研究": EmployeeProfile("RES-001", "研究员工", "研究", ("检索", "来源核验", "分析"), ("web_search", "browser", "filesystem"), "project"),
    "内容": EmployeeProfile("CON-001", "内容员工", "内容", ("文案", "脚本", "平台适配"), ("filesystem", "browser"), "project"),
    "设计": EmployeeProfile("DES-001", "设计员工", "设计", ("视觉", "界面", "素材"), ("imagegen", "filesystem", "browser"), "project"),
    "知识库": EmployeeProfile("KNO-001", "知识库员工", "知识库", ("整理", "索引", "引用"), ("filesystem", "search"), "company_and_project"),
    "技能": EmployeeProfile("SKL-001", "Skill员工", "技能", ("技能设计", "SKILL.md", "触发验证"), ("filesystem", "search"), "company_and_project"),
}


@dataclass(frozen=True)
class Assignment:
    role: str
    objective: str
    output: str
    employee_id: str = ""
    required_skills: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    status: str = "active"
    memory_scope: str = "project"
    kind: str = "specialist_template"
    skill_ids: tuple[str, ...] = ()


def _domains_for(text: str) -> list[str]:
    normalized = text.lower()
    matches = [domain for domain, (_, keywords) in DOMAIN_RULES.items() if any(word in normalized for word in keywords)]
    return matches or ["待澄清"]


def _acceptance_gates(domains: list[str], text: str) -> list[str]:
    gates: list[str] = []
    if "工程" in domains:
        gates.append("构建或测试结果")
        gates.append("关键流程验证")
    if "研究" in domains:
        gates.append("来源、日期和证据边界")
    if "内容" in domains:
        gates.append("目标受众、事实依据和单一行动指引")
    if "设计" in domains:
        gates.append("目标尺寸预览和信息层级检查")
    if "知识库" in domains:
        gates.append("抽样引用准确性和处理范围")
    if "技能" in domains:
        gates.append("SKILL.md 可加载、触发条件和最小任务验证")
    if any(word in text for word in PUBLIC_ACTIONS):
        gates.append("用户确认公开或不可逆操作")
    return gates or ["目标、负责人和完成证据明确"]


def _assignment(domain: str) -> Assignment:
    from .capabilities import skill_ids_for_employee

    profile = EMPLOYEE_PROFILES[domain]
    outputs = {
        "工程": "可运行实现、测试结果和变更说明",
        "研究": "结论、来源、日期和不确定性",
        "内容": "策略、标题/脚本和平台版本",
        "设计": "视觉方案、预览和可编辑素材",
        "知识库": "已处理范围、索引和待处理清单",
        "技能": "Skill方案、SKILL.md 和触发验证结果",
    }
    return Assignment(
        profile.name,
        f"完成任务中的{domain}部分",
        outputs[domain],
        profile.employee_id,
        profile.skills,
        profile.tools,
        profile.status,
        profile.memory_scope,
        profile.kind,
        tuple(skill_ids_for_employee(profile.employee_id)),
    )


def route_task(task: str, project: str = "") -> dict:
    """Create a deterministic, reviewable collaboration plan from a task description."""
    from .capabilities import skill_ids_for_employee
    from .workflow import build_workflow

    task = task.strip()
    domains = _domains_for(task)
    is_strategy = any(keyword in task for keyword in CEO_KEYWORDS)
    needs_clarification = domains == ["待澄清"]
    requires_confirmation = is_strategy or any(word in task for word in PUBLIC_ACTIONS)

    if is_strategy:
        route, lead = "ceo", "CEO"
    elif len(domains) > 1:
        route, lead = "project_lead", "项目主管"
    elif needs_clarification:
        route, lead = "direct_worker", "待分配员工"
    else:
        route, lead = "direct_worker", DOMAIN_RULES[domains[0]][0]

    assignments = [_assignment(domain) for domain in domains if domain in DOMAIN_RULES]
    parallel_tasks = [asdict(item) for item in assignments] if route in {"project_lead", "ceo"} else []
    budget = {
        "max_rounds": 6 if route == "direct_worker" else 12 if route == "project_lead" else 16,
        "max_tool_calls": 4 if route == "direct_worker" else 10 if route == "project_lead" else 14,
    }

    next_action = (
        "补充目标、交付物和截止时间后重新路由。"
        if needs_clarification
        else "先提交方案与验收标准，确认后执行。"
        if requires_confirmation
        else "按任务卡执行，并在完成后提交差量交接。"
    )

    return {
        "task": task,
        "project": project,
        "route": route,
        "lead": lead,
        "domains": domains,
        "parallel_tasks": parallel_tasks,
        "assignments": [asdict(item) for item in assignments],
        "core_roles": list(CORE_ROLES),
        "verification_contract": {
            "employee_id": "QA-001",
            "role": "验收员",
            "skill_ids": skill_ids_for_employee("QA-001"),
            "required_checks": ["交付物存在", "证据可复核", "验收门禁通过"],
            "independent": True,
        },
        "core_capabilities": {
            employee_id: skill_ids_for_employee(employee_id)
            for employee_id in ("CEO-001", "PM-001", "QA-001")
        },
        "specialist_templates": [
            {
                "employee_id": profile.employee_id,
                "name": profile.name,
                "department": profile.department,
                "skills": list(profile.skills),
                "tools": list(profile.tools),
                "memory_scope": profile.memory_scope,
                "kind": profile.kind,
                "skill_ids": skill_ids_for_employee(profile.employee_id),
            }
            for profile in EMPLOYEE_PROFILES.values()
        ],
        "project_memory": project or "未指定项目（执行前应建立项目上下文包）",
        "execution_policy": {
            "resume_on_restart": True,
            "persist_task_state": True,
            "approval_required_for": list(PUBLIC_ACTIONS),
            "handoff_format": "delta_only",
        },
        "acceptance_gates": _acceptance_gates(domains, task),
        "workflow_graph": build_workflow(
            [asdict(item) for item in assignments],
            acceptance_gates=_acceptance_gates(domains, task),
            requires_confirmation=requires_confirmation,
            include_intake=needs_clarification or requires_confirmation,
            include_discovery=False,
            include_learning=False,
        ),
        "budget": budget,
        "requires_user_confirmation": requires_confirmation,
        "needs_clarification": needs_clarification,
        "next_action": next_action,
    }
