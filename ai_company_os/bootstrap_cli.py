"""Command-line helpers for installing MakeCrew into an AI workspace."""

from __future__ import annotations

import argparse
import json

from .bootstrap import audit_tools, initialize_workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize or audit a MakeCrew workspace")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create a minimal .makecrew workspace")
    init.add_argument("--path", default=".", help="workspace directory")
    init.add_argument("--project", default="main", help="initial project name")

    audit = subparsers.add_parser("audit", help="check host tools against employee profiles")
    audit.add_argument("--tools", default="", help="comma-separated available tool names")

    args = parser.parse_args(argv)
    if args.command == "init":
        result = initialize_workspace(args.path, project=args.project)
    else:
        result = audit_tools([item for item in args.tools.split(",") if item.strip()])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
