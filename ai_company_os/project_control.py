"""Project-level control tower for MakeCrew.

Keeps phases, milestones, dependencies, critical-path slack, resources,
budgets and risks in a small JSON-friendly model. Execution remains delegated
to the host scheduler; this module decides what needs attention.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import json


@dataclass
class ProjectNode:
    node_id: str
    title: str
    duration: int = 1
    depends_on: list[str] = field(default_factory=list)
    budget: float = 0.0
    resources: list[str] = field(default_factory=list)
    status: str = "pending"
    milestone: bool = False


class ProjectControlTower:
    """Manage a project's dependency graph and health signals."""

    def __init__(self, project_id: str, *, path: str | Path | None = None) -> None:
        self.project_id = project_id.strip()
        if not self.project_id:
            raise ValueError("项目 ID 不能为空")
        self.path = Path(path) if path else None
        self.nodes: dict[str, ProjectNode] = {}
        self.risks: list[dict] = []
        self.resource_limits: dict[str, int] = {}
        self.budget_limit: float | None = None
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.nodes = {item["node_id"]: ProjectNode(**item) for item in raw.get("nodes", [])}
        self.risks = list(raw.get("risks", []))
        self.resource_limits = {str(k): int(v) for k, v in raw.get("resource_limits", {}).items()}
        self.budget_limit = raw.get("budget_limit")

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def add_node(self, node: ProjectNode) -> dict:
        if node.node_id in self.nodes:
            raise ValueError(f"项目节点已存在：{node.node_id}")
        if node.duration < 1 or node.budget < 0:
            raise ValueError("节点工期必须大于 0，预算不能为负数")
        missing = [item for item in node.depends_on if item not in self.nodes]
        if missing:
            raise ValueError(f"前置节点不存在：{', '.join(missing)}")
        self.nodes[node.node_id] = node
        self._assert_acyclic()
        self._save()
        return asdict(node)

    def set_budget(self, limit: float | None) -> None:
        if limit is not None and limit < 0:
            raise ValueError("项目预算不能为负数")
        self.budget_limit = limit
        self._save()

    def set_resource_limit(self, resource: str, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("资源容量必须大于 0")
        self.resource_limits[resource.strip()] = capacity
        self._save()

    def add_risk(self, risk_id: str, title: str, *, probability: str = "medium", impact: str = "medium", trigger: str = "", owner: str = "") -> None:
        self.risks.append({"risk_id": risk_id, "title": title, "probability": probability, "impact": impact, "trigger": trigger, "owner": owner, "status": "open"})
        self._save()

    def critical_path(self) -> dict[str, dict[str, int | bool]]:
        order = self._topological_order()
        earliest: dict[str, int] = {}
        for node_id in order:
            node = self.nodes[node_id]
            earliest[node_id] = max((earliest[parent] + self.nodes[parent].duration for parent in node.depends_on), default=0)
        project_duration = max((earliest[n] + self.nodes[n].duration for n in order), default=0)
        latest: dict[str, int] = {n: project_duration - self.nodes[n].duration for n in order}
        for node_id in reversed(order):
            children = [n for n in order if node_id in self.nodes[n].depends_on]
            if children:
                latest[node_id] = min(latest[child] - self.nodes[node_id].duration for child in children)
        return {n: {"early_start": earliest[n], "late_start": latest[n], "slack": max(0, latest[n] - earliest[n]), "critical": latest[n] == earliest[n]} for n in order}

    def health(self) -> dict:
        path = self.critical_path()
        total_budget = sum(node.budget for node in self.nodes.values())
        active_resources: dict[str, int] = {}
        for node in self.nodes.values():
            if node.status in {"pending", "in_progress", "blocked", "review"}:
                for resource in node.resources:
                    active_resources[resource] = active_resources.get(resource, 0) + 1
        conflicts = [r for r, count in active_resources.items() if count > self.resource_limits.get(r, 1)]
        return {"project_id": self.project_id, "node_count": len(self.nodes), "completed": sum(n.status == "done" for n in self.nodes.values()), "budget": {"planned": total_budget, "limit": self.budget_limit, "over": self.budget_limit is not None and total_budget > self.budget_limit}, "critical_nodes": [n for n, value in path.items() if value["critical"] and self.nodes[n].status != "done"], "resource_conflicts": conflicts, "open_risks": [r for r in self.risks if r.get("status") == "open"], "status": "warning" if conflicts or any(r.get("impact") == "high" for r in self.risks if r.get("status") == "open") else "healthy"}

    def snapshot(self) -> dict:
        return {"project_id": self.project_id, "nodes": [asdict(n) for n in self.nodes.values()], "risks": self.risks, "resource_limits": self.resource_limits, "budget_limit": self.budget_limit}

    def _topological_order(self) -> list[str]:
        order: list[str] = []
        pending = set(self.nodes)
        while pending:
            ready = sorted(n for n in pending if all(parent in order for parent in self.nodes[n].depends_on))
            if not ready:
                raise ValueError("项目节点依赖存在循环")
            order.extend(ready)
            pending.difference_update(ready)
        return order

    def _assert_acyclic(self) -> None:
        self._topological_order()
