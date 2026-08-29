"""Small, explicit workflow graphs for MakeCrew task execution.

The graph is deliberately data-only. A host runtime may execute it with
LangGraph, CrewAI Flows, a Codex adapter, or a local queue without changing
the routing contract. Keeping the graph serializable also makes checkpoints
and human interrupts visible to users before any expensive work starts.
"""

from __future__ import annotations

from typing import Any, Iterable


def _node(
    node_id: str,
    kind: str,
    *,
    owner: str,
    depends_on: Iterable[str] = (),
    requires_confirmation: bool = False,
    output_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "kind": kind,
        "owner": owner,
        "depends_on": list(depends_on),
        "requires_confirmation": requires_confirmation,
        "output_contract": output_contract or {},
    }


def build_workflow(
    assignments: list[dict[str, Any]],
    *,
    acceptance_gates: list[str] | tuple[str, ...] = (),
    requires_confirmation: bool = True,
) -> dict[str, Any]:
    """Build a checkpointed DAG from an existing routing plan."""
    nodes = [
        _node(
            "intake",
            "intake",
            owner="当前对话主管",
            output_contract={"required": ["task", "goal", "success_criteria"]},
        ),
        _node(
            "discovery",
            "discovery",
            owner="当前对话主管",
            depends_on=("intake",),
            output_contract={"required": ["methods", "skills", "tradeoffs", "sources"]},
        ),
    ]

    interrupt_ids: list[str] = []
    confirmation_dependency = "discovery"
    if requires_confirmation:
        nodes.append(
            _node(
                "confirmation",
                "human_gate",
                owner="用户",
                depends_on=("discovery",),
                requires_confirmation=True,
                output_contract={"required": ["approved_scope", "approved_tools", "budget"]},
            )
        )
        interrupt_ids.append("confirmation")
        confirmation_dependency = "confirmation"

    execute_ids: list[str] = []
    for index, assignment in enumerate(assignments, start=1):
        employee_id = str(assignment.get("employee_id", "")).strip() or f"worker-{index}"
        node_id = f"execute:{employee_id}:{index}"
        execute_ids.append(node_id)
        nodes.append(
            _node(
                node_id,
                "execute",
                owner=employee_id,
                depends_on=(confirmation_dependency,),
                output_contract={
                    "required": ["result", "evidence", "risks", "next_action"],
                    "skills": list(assignment.get("skill_ids", ())),
                },
            )
        )

    verify_dependencies = execute_ids or [confirmation_dependency]
    nodes.extend(
        [
            _node(
                "verify",
                "verify",
                owner="QA-001",
                depends_on=verify_dependencies,
                output_contract={"required": ["gates", "evidence", "decision", "rework_reason"]},
            ),
            _node(
                "deliver",
                "deliver",
                owner="当前对话主管",
                depends_on=("verify",),
                output_contract={"required": ["artifact", "status", "known_limits"]},
            ),
            _node(
                "learn",
                "learn",
                owner="SKL-001",
                depends_on=("deliver",),
                output_contract={"required": ["score", "feedback", "root_cause", "proposal"]},
            ),
        ]
    )

    checkpoints = ["intake", "discovery", *execute_ids, "verify", "deliver"]
    return {
        "version": "1",
        "nodes": nodes,
        "entrypoint": "intake",
        "interrupts": interrupt_ids,
        "checkpoints": checkpoints,
        "parallel_groups": [execute_ids] if len(execute_ids) > 1 else [],
        "acceptance_gates": list(acceptance_gates),
        "execution_policy": {
            "durable_checkpoints": True,
            "resume_from_last_checkpoint": True,
            "human_confirmation_before_execute": requires_confirmation,
        },
    }


def ready_nodes(
    graph: dict[str, Any],
    *,
    completed: set[str] | Iterable[str],
    confirmed: bool = False,
) -> list[str]:
    """Return executable node IDs for a checkpoint state."""
    completed_set = set(completed)
    ready: list[str] = []
    for node in graph.get("nodes", []):
        node_id = node["node_id"]
        if node_id in completed_set:
            continue
        if node.get("kind") == "human_gate":
            if confirmed:
                continue
            dependencies = set(node.get("depends_on", []))
            if dependencies.issubset(completed_set):
                ready.append(node_id)
            continue
        if node.get("requires_confirmation") and not confirmed:
            continue
        dependencies = set(node.get("depends_on", []))
        if "confirmation" in dependencies and confirmed:
            dependencies.remove("confirmation")
        if dependencies.issubset(completed_set):
            ready.append(node_id)
    return ready
