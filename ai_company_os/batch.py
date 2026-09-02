"""Deterministic batch scheduling for explicit multi-task work.

The scheduler owns queue state and dispatch decisions. A host adapter owns the
actual Codex/Agent conversation lifecycle, so this module remains portable.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Any, Callable

from .router import CORE_EMPLOYEE_PROFILES, EMPLOYEE_PROFILES, route_task


ThreadAdapter = Callable[[str, str, str], dict[str, Any]]
AgentDispatcher = Callable[[str, dict[str, Any]], dict[str, Any]]
TERMINAL = {"done", "failed", "cancelled", "blocked_dependency"}
DEFAULT_SUPERVISOR_ID = "PM-001"


class BatchScheduler:
    """Schedule independent tasks with dependency, budget, and thread reuse."""

    def __init__(
        self,
        *,
        max_concurrency: int = 3,
        total_tool_calls: int | None = None,
        supervisor_id: str = DEFAULT_SUPERVISOR_ID,
        thread_adapter: ThreadAdapter | None = None,
        agent_dispatcher: AgentDispatcher | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("并发上限必须大于 0")
        if total_tool_calls is not None and total_tool_calls < 0:
            raise ValueError("批次工具预算不能为负数")
        self.max_concurrency = max_concurrency
        self.total_tool_calls = total_tool_calls
        self.supervisor_id = supervisor_id.strip() or DEFAULT_SUPERVISOR_ID
        self.thread_adapter = thread_adapter
        self.agent_dispatcher = agent_dispatcher
        self._tasks: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._usage = {"tool_calls": 0}
        self._threads: dict[tuple[str, str, str], str] = {}

    def add(
        self,
        task: str,
        *,
        task_id: str,
        project: str = "",
        supervisor_id: str = "",
        isolated_thread: bool = False,
        file_scope: list[str] | tuple[str, ...] | None = None,
        depends_on: list[str] | tuple[str, ...] | None = None,
        budget: int | dict[str, int] = 1,
    ) -> dict[str, Any]:
        clean = task.strip()
        if not clean:
            raise ValueError("任务不能为空")
        if task_id in self._tasks:
            raise ValueError(f"任务 ID 已存在：{task_id}")
        dependencies = list(depends_on or [])
        missing = [item for item in dependencies if item not in self._tasks]
        if missing:
            raise ValueError(f"依赖任务不存在：{', '.join(missing)}")
        effective_supervisor_id = supervisor_id.strip() or self.supervisor_id
        limits = {"tool_calls": int(budget) if isinstance(budget, int) else int(budget.get("tool_calls", 1))}
        if limits["tool_calls"] < 0:
            raise ValueError("任务工具预算不能为负数")
        plan = route_task(clean, project)
        assignment = plan["assignments"][0] if plan["assignments"] else {}
        employee_id = assignment.get("employee_id") or self._temporary_id(clean)
        employee = EMPLOYEE_PROFILES.get(assignment.get("department", ""))
        supervisor_profile = CORE_EMPLOYEE_PROFILES.get(effective_supervisor_id)
        supervisor_role = supervisor_profile.name if supervisor_profile else "项目主管"
        task_packet = self._task_packet(
            task_id=task_id,
            task=clean,
            project=project,
            depends_on=dependencies,
            supervisor_id=effective_supervisor_id,
            supervisor_role=supervisor_role,
            assignment=assignment,
            employee_id=employee_id,
            employee_profile=employee,
            acceptance_gates=plan["acceptance_gates"],
            file_scope=file_scope or (),
            isolated_thread=isolated_thread,
        )
        record = {
            "task_id": task_id,
            "task": clean,
            "project": project,
            "supervisor_id": effective_supervisor_id,
            "supervisor_kind": "supervisor",
            "supervisor_role": supervisor_role,
            "isolated_thread": isolated_thread,
            "file_scope": list(file_scope or ()),
            "depends_on": dependencies,
            "budget": limits,
            "usage": {"tool_calls": 0},
            "status": "pending",
            "employee_id": employee_id,
            "role": assignment.get("role", "临时任务员工"),
            "route": plan["route"],
            "acceptance_gates": plan["acceptance_gates"],
            "thread_id": "",
            "thread_reused": False,
            "cancel_reason": "",
            "failure_reason": "",
            "result": None,
            "agent_id": employee_id,
            "agent_kind": "employee",
            "task_packet": task_packet,
        }
        record["task_packet"]["supervisor"]["agent_id"] = record["supervisor_id"]
        self._tasks[task_id] = record
        return self.snapshot(task_id)

    @staticmethod
    def _task_packet(
        *,
        task_id: str,
        task: str,
        project: str,
        depends_on: list[str],
        supervisor_id: str,
        supervisor_role: str,
        assignment: dict[str, Any],
        employee_id: str,
        employee_profile: Any = None,
        acceptance_gates: list[str] | tuple[str, ...] = (),
        file_scope: list[str] | tuple[str, ...] = (),
        isolated_thread: bool = False,
    ) -> dict[str, Any]:
        """Build the small contract sent from a supervisor to one employee Agent."""
        skills = list(assignment.get("skill_ids", ()))
        tools = list(assignment.get("tools", ()))
        if employee_profile is not None:
            skills = list(getattr(employee_profile, "skills", ()))
            tools = list(getattr(employee_profile, "tools", ()))
        return {
            "task_id": task_id,
            "task": task,
            "project": project,
            "depends_on": list(depends_on),
            "acceptance_gates": list(acceptance_gates),
            "file_scope": list(file_scope),
            "isolation": "isolated_worktree" if isolated_thread else "worktree_recommended" if file_scope else "shared_thread",
            "supervisor": {
                "agent_id": supervisor_id,
                "agent_kind": "supervisor",
                "role": supervisor_role,
                "responsibility": "拆分、派发、等待依赖并汇总员工结果",
            },
            "employee": {
                "agent_id": employee_id,
                "agent_kind": "employee",
                "role": assignment.get("role", "临时任务员工"),
                "skills": skills,
                "tools": tools,
                "output": assignment.get("output", "结论、证据、风险和下一步"),
            },
            "context_policy": "project_summary_plus_task_delta",
            "execution_contract": "return_delta_result",
            "result_schema": ["summary", "evidence", "risks", "next_steps"],
        }

    @staticmethod
    def _temporary_id(task: str) -> str:
        return "TEMP-" + hashlib.sha1(task.encode("utf-8")).hexdigest()[:8].upper()

    def _dependency_ready(self, record: dict[str, Any]) -> bool:
        return all(self._tasks[item]["status"] == "done" for item in record["depends_on"])

    def _dependency_blocked(self, record: dict[str, Any]) -> str:
        for dependency in record["depends_on"]:
            if self._tasks[dependency]["status"] in {"failed", "cancelled", "blocked_dependency"}:
                return dependency
        return ""

    def _budget_available(self, record: dict[str, Any]) -> bool:
        return self.total_tool_calls is None or (
            self._reserved_calls() + record["budget"]["tool_calls"] <= self.total_tool_calls
        )

    def _reserved_calls(self) -> int:
        return self._usage["tool_calls"] + sum(
            record["budget"]["tool_calls"]
            for record in self._tasks.values()
            if record["status"] == "running"
        )

    @staticmethod
    def _thread_key(record: dict[str, Any]) -> tuple[str, str, str] | None:
        if record.get("isolated_thread"):
            return None
        return (
            str(record.get("employee_id", "")),
            str(record.get("project", "")),
            str(record.get("supervisor_id", "")),
        )

    @staticmethod
    def _file_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_paths = {str(path).strip() for path in left.get("file_scope", []) if str(path).strip()}
        right_paths = {str(path).strip() for path in right.get("file_scope", []) if str(path).strip()}
        return bool(left_paths and right_paths and left_paths.intersection(right_paths))

    def _conflict_reason(
        self,
        record: dict[str, Any],
        active: list[dict[str, Any]],
    ) -> str:
        key = self._thread_key(record)
        for other in active:
            if key is not None and self._thread_key(other) == key:
                return "waiting_thread"
            if self._file_overlap(record, other):
                return "waiting_file_conflict"
        return ""

    def ready(self) -> list[dict[str, Any]]:
        """Return the next tasks that may start, respecting order and limits."""
        free_slots = self.max_concurrency - sum(record["status"] == "running" for record in self._tasks.values())
        if free_slots <= 0:
            return []
        selected: list[dict[str, Any]] = []
        active = [record for record in self._tasks.values() if record["status"] == "running"]
        reserved = self._reserved_calls()
        for record in self._tasks.values():
            if len(selected) >= free_slots or record["status"] in TERMINAL or record["status"] in {"running", "paused"}:
                continue
            blocked_by = self._dependency_blocked(record)
            if blocked_by:
                record["status"] = "blocked_dependency"
                record["failure_reason"] = f"依赖任务未完成：{blocked_by}"
                continue
            if not self._dependency_ready(record):
                record["status"] = "waiting_dependency"
                continue
            conflict = self._conflict_reason(record, [*active, *selected])
            if conflict:
                record["status"] = conflict
                continue
            required = record["budget"]["tool_calls"]
            if self.total_tool_calls is not None and reserved + required > self.total_tool_calls:
                record["status"] = "waiting_budget"
                continue
            record["status"] = "pending"
            selected.append(self.snapshot(record["task_id"]))
            reserved += required
        return selected

    def mark_running(self, task_id: str) -> dict[str, Any]:
        record = self._get(task_id)
        if record["status"] in TERMINAL:
            raise ValueError(f"任务已结束：{task_id}")
        if not self._dependency_ready(record):
            raise ValueError(f"任务仍在等待依赖：{task_id}")
        if not self._budget_available(record):
            record["status"] = "waiting_budget"
            raise ValueError(f"任务超出批次预算：{task_id}")
        active = [item for item in self._tasks.values() if item["status"] == "running" and item["task_id"] != task_id]
        conflict = self._conflict_reason(record, active)
        if conflict:
            record["status"] = conflict
            raise ValueError(f"任务存在执行冲突：{task_id}")
        if sum(item["status"] == "running" for item in self._tasks.values()) >= self.max_concurrency:
            raise ValueError("已达到批次并发上限")
        record["status"] = "running"
        return self.snapshot(task_id)

    def dispatch_ready(self) -> list[dict[str, Any]]:
        """Open/reuse host threads for ready tasks and return compact dispatches."""
        dispatched: list[dict[str, Any]] = []
        for item in self.ready():
            task_id = item["task_id"]
            self.mark_running(task_id)
            # ``mark_running`` returns a defensive snapshot; continue with the
            # live record so host-created thread IDs and dispatch receipts are
            # retained for resume and follow-up work.
            record = self._get(task_id)
            thread_id = ""
            reused = False
            thread_key = None if record.get("isolated_thread") else (
                record["employee_id"],
                record["project"],
                f"{record.get('supervisor_id', '')}:shared",
            )
            if self.thread_adapter is not None and thread_key is not None:
                if thread_key in self._threads:
                    thread_id = self._threads[thread_key]
                    reused = True
                else:
                    response = self.thread_adapter(record["employee_id"], record["project"], record["role"])
                    thread_id = str(response.get("thread_id", ""))
                    reused = bool(response.get("reused", False))
                    if thread_id:
                        self._threads[thread_key] = thread_id
            record["thread_id"] = thread_id
            record["thread_reused"] = reused
            host_dispatch = None
            if self.agent_dispatcher is not None:
                response = self.agent_dispatcher(thread_id, record["task_packet"])
                host_dispatch = response if isinstance(response, dict) else {"status": "accepted", "result": response}
                if str(host_dispatch.get("status", "")).lower() in {"queued", "blocked", "waiting"}:
                    record["status"] = "waiting_host"
                dispatched_thread_id = str(host_dispatch.get("thread_id", "")).strip()
                if dispatched_thread_id and not record["thread_id"]:
                    record["thread_id"] = dispatched_thread_id
                    record["thread_reused"] = bool(host_dispatch.get("reused", False))
                    if thread_key is not None:
                        self._threads[thread_key] = dispatched_thread_id
            dispatched.append({
                "task_id": task_id,
                "employee_id": record["employee_id"],
                "agent_id": record["agent_id"],
                "agent_kind": record["agent_kind"],
                "supervisor": {
                    "agent_id": record["supervisor_id"],
                    "agent_kind": record["supervisor_kind"],
                    "role": record["supervisor_role"],
                },
                "thread_id": record["thread_id"],
                "thread_reused": record["thread_reused"],
                "task_packet": record["task_packet"],
                "host_dispatch": host_dispatch,
                "status": record["status"],
            })
        return dispatched

    @staticmethod
    def _normalize_result(result: Any) -> dict[str, Any] | None:
        if result is None:
            return None
        if isinstance(result, dict):
            summary = result.get("summary", result.get("result", ""))
            return {
                "summary": str(summary).strip(),
                "evidence": list(result.get("evidence", [])),
                "risks": list(result.get("risks", [])),
                "next_steps": list(result.get("next_steps", result.get("next_step", [])))
                if isinstance(result.get("next_steps", result.get("next_step", [])), (list, tuple))
                else [str(result.get("next_steps", result.get("next_step", ""))).strip()],
            }
        return {"summary": str(result).strip(), "evidence": [], "risks": [], "next_steps": []}

    def mark_done(
        self,
        task_id: str,
        *,
        result: Any = None,
        usage: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        record = self._get(task_id)
        if record["status"] not in {"pending", "running", "review", "waiting_host"}:
            raise ValueError(f"当前状态不可标记完成：{task_id}")
        if record["status"] == "cancelled":
            raise ValueError(f"任务已取消：{task_id}")
        calls = int((usage or {}).get("tool_calls", 0))
        if calls < 0:
            raise ValueError("用量不能为负数")
        record["usage"]["tool_calls"] += calls
        self._usage["tool_calls"] += calls
        record["status"] = "done"
        record["result"] = self._normalize_result(result)
        return self.snapshot(task_id)

    def mark_failed(self, task_id: str, *, reason: str = "", usage: dict[str, int] | None = None) -> dict[str, Any]:
        """Finish a task as failed while keeping a compact, actionable reason."""
        record = self._get(task_id)
        if record["status"] not in {"pending", "running", "review", "paused", "waiting_host"}:
            raise ValueError(f"当前状态不可标记失败：{task_id}")
        if record["status"] in TERMINAL:
            return self.snapshot(task_id)
        calls = int((usage or {}).get("tool_calls", 0))
        if calls < 0:
            raise ValueError("用量不能为负数")
        record["usage"]["tool_calls"] += calls
        self._usage["tool_calls"] += calls
        record["status"] = "failed"
        record["failure_reason"] = reason.strip()
        return self.snapshot(task_id)

    def set_max_concurrency(self, value: int) -> int:
        """Adjust the batch ceiling without interrupting already running work."""
        if value < 1:
            raise ValueError("并发上限必须大于 0")
        self.max_concurrency = value
        return self.max_concurrency

    def pause(self, task_id: str, *, reason: str = "") -> dict[str, Any]:
        """Pause queued or running work; its task and thread identity are retained."""
        record = self._get(task_id)
        if record["status"] in TERMINAL:
            return self.snapshot(task_id)
        record["status"] = "paused"
        record["cancel_reason"] = reason.strip()
        return self.snapshot(task_id)

    def resume(self, task_id: str) -> dict[str, Any]:
        """Resume paused work and recompute dependency/budget waiting state."""
        record = self._get(task_id)
        if record["status"] in TERMINAL:
            return self.snapshot(task_id)
        if record["status"] != "paused":
            return self.snapshot(task_id)
        if not self._dependency_ready(record):
            record["status"] = "waiting_dependency"
        elif (
            self.total_tool_calls is not None
            and self._usage["tool_calls"] + record["budget"]["tool_calls"] > self.total_tool_calls
        ):
            record["status"] = "waiting_budget"
        else:
            record["status"] = "pending"
        record["cancel_reason"] = ""
        return self.snapshot(task_id)

    def cancel(self, task_id: str, *, reason: str = "") -> dict[str, Any]:
        record = self._get(task_id)
        if record["status"] in TERMINAL:
            return self.snapshot(task_id)
        record["status"] = "cancelled"
        record["cancel_reason"] = reason.strip()
        return self.snapshot(task_id)

    def _get(self, task_id: str) -> dict[str, Any]:
        if task_id not in self._tasks:
            raise KeyError(f"未知任务：{task_id}")
        return self._tasks[task_id]

    def snapshot(self, task_id: str) -> dict[str, Any]:
        record = self._get(task_id)
        return dict(record, usage=dict(record["usage"]), budget=dict(record["budget"]), depends_on=list(record["depends_on"]))

    def overview(self) -> dict[str, Any]:
        return {
            "task_count": len(self._tasks),
            "running": [item["task_id"] for item in self._tasks.values() if item["status"] == "running"],
            "completed": [item["task_id"] for item in self._tasks.values() if item["status"] == "done"],
            "waiting": [item["task_id"] for item in self._tasks.values() if item["status"].startswith("waiting")],
            "paused": [item["task_id"] for item in self._tasks.values() if item["status"] == "paused"],
            "usage": dict(self._usage),
            "max_concurrency": self.max_concurrency,
            "total_tool_calls": self.total_tool_calls,
            "supervisor": {
                "agent_id": self.supervisor_id,
                "agent_kind": "supervisor",
                "role": "项目主管",
            },
        }

    def aggregate_results(self) -> dict[str, Any]:
        """Return compact employee deltas for the supervisor to synthesize."""
        completed = []
        for record in self._tasks.values():
            if record["status"] != "done":
                continue
            result = record.get("result") or {"summary": "", "evidence": [], "risks": [], "next_steps": []}
            completed.append({
                "task_id": record["task_id"],
                "employee_id": record["employee_id"],
                "agent_id": record["agent_id"],
                **result,
            })
        return {
            "supervisor": {
                "agent_id": self.supervisor_id,
                "agent_kind": "supervisor",
                "role": "项目主管",
                "responsibility": "整合员工结果并向用户反馈",
            },
            "completed": completed,
            "pending_task_ids": [
                record["task_id"] for record in self._tasks.values() if record["status"] not in TERMINAL
            ],
            "contract": "supervisor_summary_with_evidence",
        }

    def plan(self) -> dict[str, Any]:
        """Return a compact batch view suitable for a CEO status update."""
        return {
            "mode": "batch",
            "tasks": [self.snapshot(task_id) for task_id in self._tasks],
            "overview": self.overview(),
            "dispatch_policy": "reuse_existing_then_create_missing_conversations",
        }
