"""Command-line helpers for installing MakeCrew into an AI workspace."""

from __future__ import annotations

import argparse
import json

from .bootstrap import audit_tools, initialize_workspace, register_employee
from .orchestrator import CrewOrchestrator
from .intake import plan_batch, plan_request
from .batch import BatchScheduler
from .capabilities import audit_employee_capabilities


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize or audit a MakeCrew workspace")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create a minimal .makecrew workspace")
    init.add_argument("--path", default=".", help="workspace directory")
    init.add_argument("--project", default="main", help="initial project name")

    audit = subparsers.add_parser("audit", help="check host tools against employee profiles")
    audit.add_argument("--tools", default="", help="comma-separated available tool names")

    capability_audit = subparsers.add_parser("capability-audit", help="audit built-in employee skill bindings")

    add = subparsers.add_parser("add-employee", help="add a user-defined employee")
    add.add_argument("--path", default=".", help="workspace directory")
    add.add_argument("--id", required=True, dest="employee_id", help="unique employee ID")
    add.add_argument("--name", required=True, help="employee display name")
    add.add_argument("--department", required=True, help="employee department")
    add.add_argument("--skills", default="", help="comma-separated skills")
    add.add_argument("--tools", default="", help="comma-separated tools")
    add.add_argument("--memory-scope", default="project", help="project, company, or company_and_project")

    dispatch = subparsers.add_parser("dispatch", help="route and dispatch a task")
    dispatch.add_argument("task", nargs="+", help="task description")
    dispatch.add_argument("--path", default=".", help="workspace directory")
    dispatch.add_argument("--project", default="", help="project name")
    dispatch.add_argument("--approved-employee", action="append", default=[], dest="approved_employee_ids", help="approve a proposed employee ID; repeat for multiple")
    dispatch.add_argument("--approve-all-employees", action="store_true", help="approve all employee proposals returned for this dispatch")

    intake = subparsers.add_parser("intake", help="clarify and plan one task")
    intake.add_argument("task", nargs="+", help="task description")
    intake.add_argument("--confirmed", action="store_true", help="confirm the displayed plan")
    intake.add_argument(
        "--installed-skills",
        default=None,
        help="comma-separated skill IDs reported by the host; omitted uses MakeCrew bundled skills",
    )

    batch = subparsers.add_parser("batch-plan", help="plan multiple tasks for CEO fan-out")
    batch.add_argument("tasks", nargs="+", help="independent task descriptions")

    batch_dispatch = subparsers.add_parser("batch-dispatch", help="queue a batch with concurrency and budget controls")
    batch_dispatch.add_argument("tasks", nargs="+", help="TASK_ID::task description")
    batch_dispatch.add_argument("--project", default="", help="project shared by this batch")
    batch_dispatch.add_argument("--max-concurrency", type=int, default=3, help="maximum running tasks")
    batch_dispatch.add_argument("--total-tool-calls", type=int, default=None, help="batch tool-call budget")
    batch_dispatch.add_argument(
        "--depends-on", action="append", default=[], metavar="TASK_ID=DEP1,DEP2",
        help="declare dependencies; repeat once per task (dependencies must appear earlier)",
    )
    batch_dispatch.add_argument(
        "--task-budget", action="append", default=[], metavar="TASK_ID=N",
        help="set a per-task tool-call budget; repeat as needed",
    )

    args = parser.parse_args(argv)
    if args.command == "init":
        result = initialize_workspace(args.path, project=args.project)
    elif args.command == "audit":
        result = audit_tools([item for item in args.tools.split(",") if item.strip()])
    elif args.command == "capability-audit":
        result = audit_employee_capabilities()
    elif args.command == "add-employee":
        result = register_employee(args.path, {
            "employee_id": args.employee_id,
            "name": args.name,
            "department": args.department,
            "skills": [item.strip() for item in args.skills.split(",") if item.strip()],
            "tools": [item.strip() for item in args.tools.split(",") if item.strip()],
            "memory_scope": args.memory_scope,
        }, approved=True)
    elif args.command == "intake":
        installed_skills = None if args.installed_skills is None else [
            item.strip() for item in args.installed_skills.split(",") if item.strip()
        ]
        result = plan_request(
            " ".join(args.task),
            confirmed=args.confirmed,
            installed_skill_ids=installed_skills,
        )
    elif args.command == "batch-plan":
        result = plan_batch(args.tasks)
    elif args.command == "batch-dispatch":
        scheduler = BatchScheduler(max_concurrency=args.max_concurrency, total_tool_calls=args.total_tool_calls)
        dependencies = _parse_assignments(args.depends_on, "依赖")
        budgets = _parse_assignments(args.task_budget, "任务预算")
        for raw in args.tasks:
            if "::" not in raw:
                raise SystemExit("batch-dispatch 任务格式应为 TASK_ID::任务内容")
            task_id, task = raw.split("::", 1)
            budget = int(budgets[task_id]) if task_id in budgets else 1
            depends_on = [item for item in dependencies.get(task_id, "").split(",") if item]
            scheduler.add(task, task_id=task_id, project=args.project, depends_on=depends_on, budget=budget)
        result = scheduler.plan()
        result["dispatches"] = scheduler.dispatch_ready()
        result["tasks"] = scheduler.plan()["tasks"]
        result["overview"] = scheduler.overview()
        result["execution"] = "host_adapter_required"
    else:
        result = CrewOrchestrator(args.path).dispatch(
            " ".join(args.task),
            project=args.project,
            approved_employee_ids=args.approved_employee_ids,
            employee_approval=args.approve_all_employees,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _parse_assignments(items: list[str], label: str) -> dict[str, str]:
    """Parse repeated TASK_ID=value CLI flags without accepting ambiguous input."""
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"{label}格式应为 TASK_ID=值")
        task_id, value = item.split("=", 1)
        task_id, value = task_id.strip(), value.strip()
        if not task_id or not value:
            raise SystemExit(f"{label}格式应为 TASK_ID=值")
        if task_id in parsed:
            raise SystemExit(f"{label}重复指定任务：{task_id}")
        parsed[task_id] = value
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
