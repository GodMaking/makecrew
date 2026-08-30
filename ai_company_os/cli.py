"""Command-line entry point for the local MVP."""

from __future__ import annotations

import argparse
import json
import sys

from .router import route_task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route a task through AgentFlow OS (MakeCrew compatibility alias)")
    parser.add_argument("task", nargs="*", help="task description")
    parser.add_argument("--project", default="", help="project name")
    args = parser.parse_args(argv)
    task = " ".join(args.task).strip()
    if not task:
        task = sys.stdin.read().strip()
    if not task:
        parser.error("请提供任务描述，或通过标准输入传入")
    print(json.dumps(route_task(task, args.project), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
