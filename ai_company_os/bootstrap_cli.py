"""Command-line helpers for installing MakeCrew into an AI workspace."""

from __future__ import annotations

import argparse
import json

from .bootstrap import audit_tools, initialize_workspace, register_employee
from .orchestrator import CrewOrchestrator
from .intake import plan_batch, plan_request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize or audit a MakeCrew workspace")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create a minimal .makecrew workspace")
    init.add_argument("--path", default=".", help="workspace directory")
    init.add_argument("--project", default="main", help="initial project name")

    audit = subparsers.add_parser("audit", help="check host tools against employee profiles")
    audit.add_argument("--tools", default="", help="comma-separated available tool names")

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

    intake = subparsers.add_parser("intake", help="clarify and plan one task")
    intake.add_argument("task", nargs="+", help="task description")
    intake.add_argument("--confirmed", action="store_true", help="confirm the displayed plan")

    batch = subparsers.add_parser("batch-plan", help="plan multiple tasks for CEO fan-out")
    batch.add_argument("tasks", nargs="+", help="independent task descriptions")

    args = parser.parse_args(argv)
    if args.command == "init":
        result = initialize_workspace(args.path, project=args.project)
    elif args.command == "audit":
        result = audit_tools([item for item in args.tools.split(",") if item.strip()])
    elif args.command == "add-employee":
        result = register_employee(args.path, {
            "employee_id": args.employee_id,
            "name": args.name,
            "department": args.department,
            "skills": [item.strip() for item in args.skills.split(",") if item.strip()],
            "tools": [item.strip() for item in args.tools.split(",") if item.strip()],
            "memory_scope": args.memory_scope,
        })
    elif args.command == "intake":
        result = plan_request(" ".join(args.task), confirmed=args.confirmed)
    elif args.command == "batch-plan":
        result = plan_batch(args.tasks)
    else:
        result = CrewOrchestrator(args.path).dispatch(" ".join(args.task), project=args.project)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
