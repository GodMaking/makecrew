"""Deterministic batch scheduling for explicit multi-task work.

The scheduler owns queue state and dispatch decisions. A host adapter owns the
actual Codex/Agent conversation lifecycle, so this module remains portable.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .router import CORE_EMPLOYEE_PROFILES, EMPLOYEE_PROFILES, route_task


ThreadAdapter = Callable[[str, str, str], dict[str, Any]]
AgentDispatcher = Callable[[str, dict[str, Any]], dict[str, Any]]
TERMINAL = {"done", "failed", "cancelled", "blocked_dependency"}
BATCH_STATUSES = {
    "pending", "running", "waiting_host", "blocked_dependency", "waiting_dependency",
    "waiting_thread", "waiting_file_conflict", "waiting_budget", "review", "qa_review", "blocked_qa", "paused",
    "done", "failed", "cancelled",
}
DEFAULT_SUPERVISOR_ID = "PM-001"


class BatchScheduler:
    """Schedule independent tasks with dependency, budget, and thread reuse."""

    STATE_VERSION = 1

    def __init__(
        self,
        *,
        max_concurrency: int = 3,
        total_tool_calls: int | None = None,
        max_qa_reworks: int = 2,
        supervisor_id: str = DEFAULT_SUPERVISOR_ID,
        thread_adapter: ThreadAdapter | None = None,
        agent_dispatcher: AgentDispatcher | None = None,
        run_id: str | None = None,
        trace_path: str | Path | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("并发上限必须大于 0")
        if total_tool_calls is not None and total_tool_calls < 0:
            raise ValueError("批次工具预算不能为负数")
        if isinstance(max_qa_reworks, bool) or not isinstance(max_qa_reworks, int) or max_qa_reworks < 0:
            raise ValueError("QA 返工上限必须是非负整数")
        self.max_concurrency = max_concurrency
        self.total_tool_calls = total_tool_calls
        self.max_qa_reworks = max_qa_reworks
        self.supervisor_id = supervisor_id.strip() or DEFAULT_SUPERVISOR_ID
        self.thread_adapter = thread_adapter
        self.agent_dispatcher = agent_dispatcher
        self.run_id = str(run_id or "").strip() or uuid4().hex
        self.trace_path = Path(trace_path).expanduser().resolve() if trace_path else None
        self.state_path = Path(state_path).expanduser().resolve() if state_path else None
        if self.state_path is not None and self.trace_path == self.state_path:
            raise ValueError("批次状态文件和 trace 文件必须使用不同路径")
        if self.state_path is not None and self.state_path.exists():
            raise FileExistsError(f"批次状态文件已存在；请使用 BatchScheduler.restore：{self.state_path}")
        self._trace_events: list[dict[str, Any]] = []
        self._tasks: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._usage = {"tool_calls": 0}
        self._threads: dict[tuple[str, str, str], str] = {}

    @classmethod
    def restore(
        cls,
        state_path: str | Path,
        *,
        thread_adapter: ThreadAdapter | None = None,
        agent_dispatcher: AgentDispatcher | None = None,
        trace_path: str | Path | None = None,
    ) -> "BatchScheduler":
        """Rehydrate one batch and mark any interrupted running task retryable."""
        path = Path(state_path).expanduser().resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"批次状态文件无效：{path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"批次状态文件结构无效：{path}")
        version = payload.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version != cls.STATE_VERSION:
            raise ValueError(f"不支持的批次状态版本：{payload.get('version')}")

        task_records = payload.get("tasks")
        if not isinstance(task_records, list) or any(not isinstance(item, dict) for item in task_records):
            raise ValueError(f"批次状态任务列表无效：{path}")
        max_concurrency = payload.get("max_concurrency")
        total_tool_calls = payload.get("total_tool_calls")
        max_qa_reworks = payload.get("max_qa_reworks", 2)
        raw_run_id = payload.get("run_id")
        raw_supervisor_id = payload.get("supervisor_id", "")
        run_id = raw_run_id.strip() if isinstance(raw_run_id, str) else ""
        supervisor_id = raw_supervisor_id.strip() if isinstance(raw_supervisor_id, str) else ""
        usage = payload.get("usage")
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise ValueError(f"批次状态并发配置无效：{path}")
        if total_tool_calls is not None and (
            isinstance(total_tool_calls, bool) or not isinstance(total_tool_calls, int) or total_tool_calls < 0
        ):
            raise ValueError(f"批次状态预算配置无效：{path}")
        if isinstance(max_qa_reworks, bool) or not isinstance(max_qa_reworks, int) or max_qa_reworks < 0:
            raise ValueError(f"批次状态 QA 返工上限无效：{path}")
        if not run_id or not isinstance(usage, dict):
            raise ValueError(f"批次状态缺少 run_id 或用量：{path}")
        usage_calls = usage.get("tool_calls")
        if isinstance(usage_calls, bool) or not isinstance(usage_calls, int) or usage_calls < 0:
            raise ValueError(f"批次状态用量无效：{path}")

        restored_trace_path = trace_path
        if restored_trace_path is None:
            restored_trace_path = payload.get("trace_path") or None
        if restored_trace_path is not None and Path(restored_trace_path).expanduser().resolve() == path:
            raise ValueError("批次状态文件和 trace 文件必须使用不同路径")
        scheduler = cls(
            max_concurrency=max_concurrency,
            total_tool_calls=total_tool_calls,
            max_qa_reworks=max_qa_reworks,
            supervisor_id=supervisor_id or DEFAULT_SUPERVISOR_ID,
            thread_adapter=thread_adapter,
            agent_dispatcher=agent_dispatcher,
            run_id=run_id,
            trace_path=restored_trace_path,
        )
        scheduler.state_path = path
        scheduler._usage = {"tool_calls": usage_calls}
        restored_tasks: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for raw_record in task_records:
            record = deepcopy(raw_record)
            raw_task_id = record.get("task_id")
            task_id = raw_task_id.strip() if isinstance(raw_task_id, str) else ""
            if not task_id or task_id in restored_tasks:
                raise ValueError(f"批次状态包含空或重复 task_id：{path}")
            if (
                not isinstance(record.get("task"), str)
                or not isinstance(record.get("status"), str)
                or record["status"] not in BATCH_STATUSES
                or not isinstance(record.get("task_packet"), dict)
                or not isinstance(record.get("depends_on"), list)
                or any(not isinstance(item, str) for item in record["depends_on"])
                or not isinstance(record.get("usage"), dict)
                or not isinstance(record.get("budget"), dict)
                or not isinstance(record.get("thread_id", ""), str)
                or not isinstance(record.get("file_scope", []), list)
                or not isinstance(record.get("artifact_refs", []), list)
                or not isinstance(record.get("qa", {}), dict)
                or not isinstance(record.get("qa_review_id", ""), str)
                or not isinstance(record.get("qa_dispatch_error", ""), str)
                or not isinstance(record.get("paused_from_status", ""), str)
            ):
                raise ValueError(f"批次状态任务结构无效：{task_id}")
            attempt = record.get("attempt")
            record_usage = record["usage"].get("tool_calls")
            record_budget = record["budget"].get("tool_calls")
            latest_qa = record.get("qa", {})
            legacy_qa_status = latest_qa.get("status", "not_run")
            qa_rework_count = record.get(
                "qa_rework_count", 1 if legacy_qa_status == "rework_required" else 0,
            )
            qa_history = record.get("qa_history")
            if qa_history is None and "qa_history" not in record:
                qa_history = [deepcopy(latest_qa)] if legacy_qa_status != "not_run" else []
            packet = record["task_packet"]
            if (
                isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0
                or isinstance(record_usage, bool) or not isinstance(record_usage, int) or record_usage < 0
                or isinstance(record_budget, bool) or not isinstance(record_budget, int) or record_budget < 0
                or isinstance(qa_rework_count, bool) or not isinstance(qa_rework_count, int) or qa_rework_count < 0
                or not isinstance(qa_history, list) or any(not isinstance(item, dict) for item in qa_history)
            ):
                raise ValueError(f"批次状态任务计数无效：{task_id}")
            record.setdefault("qa_rework_count", qa_rework_count)
            record.setdefault("qa_history", qa_history)
            if record["status"] == "done" and legacy_qa_status == "rework_required":
                record["status"] = "review"
                record["failure_reason"] = str(latest_qa.get("reason", ""))
            elif record["status"] == "done" and legacy_qa_status == "blocked":
                record["status"] = "blocked_qa"
                record["failure_reason"] = str(latest_qa.get("reason", ""))
            if (
                record.get("run_id") != run_id
                or packet.get("run_id") != run_id
                or packet.get("task_id") != task_id
            ):
                raise ValueError(f"任务 {task_id} 的 run_id 与批次不一致：{path}")
            if packet.get("idempotency_key") != f"{run_id}:{task_id}":
                raise ValueError(f"任务 {task_id} 的幂等键无效：{path}")
            if packet.get("depends_on") != record["depends_on"]:
                raise ValueError(f"任务 {task_id} 的依赖记录不一致：{path}")
            restored_tasks[task_id] = record
        for task_id, record in restored_tasks.items():
            parent_task_id = str(record.get("parent_task_id", ""))
            if parent_task_id and parent_task_id not in restored_tasks:
                raise ValueError(f"任务 {task_id} 的父任务不存在：{path}")
            missing_dependencies = [item for item in record["depends_on"] if item not in restored_tasks]
            if missing_dependencies:
                raise ValueError(f"任务 {task_id} 的依赖不存在：{path}")
        scheduler._tasks = restored_tasks
        for record in scheduler._tasks.values():
            if record.get("thread_id") and not record.get("isolated_thread"):
                thread_key = (
                    str(record.get("employee_id", "")),
                    str(record.get("project", "")),
                    f"{record.get('supervisor_id', scheduler.supervisor_id)}:shared",
                )
                scheduler._threads[thread_key] = str(record["thread_id"])
            if record.get("status") == "running":
                record["status"] = "waiting_host"
                scheduler._emit_trace(
                    "task_interrupted_on_restore",
                    record,
                    actor="recovery",
                    status="waiting_host",
                    reason="running_task_found_during_restore",
                )
        scheduler._persist_state()
        return scheduler

    def _persist_state(self) -> None:
        """Atomically save compact scheduler state when durable persistence is enabled."""
        if self.state_path is None:
            return
        payload = {
            "version": self.STATE_VERSION,
            "run_id": self.run_id,
            "supervisor_id": self.supervisor_id,
            "max_concurrency": self.max_concurrency,
            "total_tool_calls": self.total_tool_calls,
            "max_qa_reworks": self.max_qa_reworks,
            "usage": dict(self._usage),
            "trace_path": str(self.trace_path) if self.trace_path is not None else "",
            "tasks": list(self._tasks.values()),
        }
        try:
            serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        except (TypeError, ValueError) as exc:
            raise ValueError("批次状态包含不可序列化内容") from exc
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(self.state_path)

    def add(
        self,
        task: str,
        *,
        task_id: str,
        project: str = "",
        supervisor_id: str = "",
        isolated_thread: bool = False,
        parent_task_id: str = "",
        model: str = "",
        file_scope: list[str] | tuple[str, ...] | None = None,
        depends_on: list[str] | tuple[str, ...] | None = None,
        budget: int | dict[str, int] = 1,
    ) -> dict[str, Any]:
        clean = task.strip()
        if not clean:
            raise ValueError("任务不能为空")
        if task_id in self._tasks:
            raise ValueError(f"任务 ID 已存在：{task_id}")
        parent_task_id = str(parent_task_id or "").strip()
        if parent_task_id and parent_task_id not in self._tasks:
            raise ValueError(f"父任务不存在：{parent_task_id}")
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
            run_id=self.run_id,
            idempotency_key=f"{self.run_id}:{task_id}",
            parent_task_id=parent_task_id,
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
            "run_id": self.run_id,
            "parent_task_id": parent_task_id,
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
            "model": str(model or "").strip(),
            "attempt": 0,
            "artifact_refs": [],
            "qa": {"status": "not_run", "reason": "", "agent_id": "", "model": "", "evidence_refs": []},
            "qa_history": [],
            "qa_rework_count": 0,
            "qa_review_id": "",
            "qa_dispatch_error": "",
            "paused_from_status": "",
            "agent_id": employee_id,
            "agent_kind": "employee",
            "task_packet": task_packet,
        }
        record["task_packet"]["supervisor"]["agent_id"] = record["supervisor_id"]
        self._emit_trace("task_created", record, actor="supervisor")
        self._tasks[task_id] = record
        self._persist_state()
        return self.snapshot(task_id)

    @staticmethod
    def _task_packet(
        *,
        task_id: str,
        run_id: str,
        idempotency_key: str,
        parent_task_id: str,
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
            "run_id": run_id,
            "idempotency_key": idempotency_key,
            "parent_task_id": parent_task_id,
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
            "result_schema": ["summary", "evidence", "risks", "next_steps", "artifact_refs"],
        }

    def _emit_trace(
        self,
        event_type: str,
        record: dict[str, Any],
        *,
        actor: str,
        status: str | None = None,
        reason: str = "",
        model: str | None = None,
        thread_id: str | None = None,
        attempt: int | None = None,
        qa_rework_count: int | None = None,
        artifact_refs: list[str] | tuple[str, ...] | None = None,
        host_run_id: str = "",
        dispatch_status: str = "",
        qa_status: str = "",
        qa_reason: str = "",
        qa_agent_id: str = "",
        qa_model: str = "",
        qa_evidence_refs: list[str] | tuple[str, ...] = (),
        qa_review_id: str = "",
    ) -> dict[str, Any]:
        """Record compact lifecycle evidence without copying task prompts or chat history."""
        event = {
            "event_id": uuid4().hex,
            "run_id": self.run_id,
            "event_type": event_type,
            "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "task_id": record["task_id"],
            "parent_task_id": record.get("parent_task_id", ""),
            "idempotency_key": record.get("task_packet", {}).get("idempotency_key", ""),
            "depends_on": list(record.get("depends_on", [])),
            "actor": actor,
            "supervisor_id": record.get("supervisor_id", self.supervisor_id),
            "employee_id": record.get("employee_id", ""),
            "agent_id": record.get("agent_id", ""),
            "thread_id": record.get("thread_id", "") if thread_id is None else thread_id,
            "model": record.get("model", "") if model is None else model,
            "attempt": record.get("attempt", 0) if attempt is None else attempt,
            "qa_rework_count": record.get("qa_rework_count", 0) if qa_rework_count is None else qa_rework_count,
            "status": record.get("status", "") if status is None else status,
            "artifact_refs": list(record.get("artifact_refs", [])) if artifact_refs is None else list(artifact_refs),
        }
        if reason:
            event["reason"] = str(reason)[:2000]
        if host_run_id:
            event["host_run_id"] = str(host_run_id)
        if dispatch_status:
            event["dispatch_status"] = str(dispatch_status)
        if qa_status:
            event["qa_status"] = str(qa_status)
            event["qa_reason"] = str(qa_reason)[:2000]
            event["qa_agent_id"] = str(qa_agent_id)
            event["qa_model"] = str(qa_model)
            event["qa_evidence_refs"] = list(qa_evidence_refs)
        if qa_review_id:
            event["qa_review_id"] = str(qa_review_id)
        if self.trace_path is not None:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self.trace_path.open("a", encoding="utf-8", newline="\n") as trace_file:
                trace_file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._trace_events.append(event)
        return event

    def trace_events(self) -> list[dict[str, Any]]:
        """Return compact events for this run; no prompt or conversation history is included."""
        return [dict(event) for event in self._trace_events]

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
            if len(selected) >= free_slots or record["status"] in TERMINAL or record["status"] in {"running", "paused", "qa_review", "blocked_qa"}:
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
        self._persist_state()
        return selected

    def mark_running(self, task_id: str) -> dict[str, Any]:
        record = self._get(task_id)
        if record["status"] in TERMINAL:
            raise ValueError(f"任务已结束：{task_id}")
        if not self._dependency_ready(record):
            raise ValueError(f"任务仍在等待依赖：{task_id}")
        if not self._budget_available(record):
            record["status"] = "waiting_budget"
            self._persist_state()
            raise ValueError(f"任务超出批次预算：{task_id}")
        active = [item for item in self._tasks.values() if item["status"] == "running" and item["task_id"] != task_id]
        conflict = self._conflict_reason(record, active)
        if conflict:
            record["status"] = conflict
            self._persist_state()
            raise ValueError(f"任务存在执行冲突：{task_id}")
        if sum(item["status"] == "running" for item in self._tasks.values()) >= self.max_concurrency:
            raise ValueError("已达到批次并发上限")
        next_attempt = int(record.get("attempt", 0)) + 1
        self._emit_trace("task_started", record, actor="employee", status="running", attempt=next_attempt)
        record["status"] = "running"
        record["attempt"] = next_attempt
        self._persist_state()
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
                    try:
                        response = self.thread_adapter(record["employee_id"], record["project"], record["role"])
                    except Exception as exc:
                        record["status"] = "waiting_host"
                        self._emit_trace(
                            "host_thread_error",
                            record,
                            actor="host_adapter",
                            status="waiting_host",
                            reason=f"{type(exc).__name__}: {exc}",
                        )
                        self._persist_state()
                        raise
                    thread_id = str(response.get("thread_id", ""))
                    reused = bool(response.get("reused", False))
                    if thread_id:
                        self._threads[thread_key] = thread_id
            record["thread_id"] = thread_id
            record["thread_reused"] = reused
            host_dispatch = None
            self._emit_trace("dispatch_requested", record, actor="supervisor", thread_id=thread_id)
            self._persist_state()
            if self.agent_dispatcher is not None:
                try:
                    response = self.agent_dispatcher(thread_id, record["task_packet"])
                except Exception as exc:
                    record["status"] = "waiting_host"
                    self._emit_trace(
                        "host_dispatch_error",
                        record,
                        actor="host_adapter",
                        status="waiting_host",
                        reason=f"{type(exc).__name__}: {exc}",
                        thread_id=thread_id,
                    )
                    self._persist_state()
                    raise
                host_dispatch = response if isinstance(response, dict) else {"status": "accepted", "result": response}
                if str(host_dispatch.get("status", "")).lower() in {"queued", "blocked", "waiting"}:
                    record["status"] = "waiting_host"
                host_model = str(host_dispatch.get("model", host_dispatch.get("model_name", ""))).strip()
                if host_model:
                    record["model"] = host_model
                dispatched_thread_id = str(host_dispatch.get("thread_id", "")).strip()
                if dispatched_thread_id and not record["thread_id"]:
                    record["thread_id"] = dispatched_thread_id
                    record["thread_reused"] = bool(host_dispatch.get("reused", False))
                    if thread_key is not None:
                        self._threads[thread_key] = dispatched_thread_id
                self._emit_trace(
                    "host_dispatch_result",
                    record,
                    actor="host_adapter",
                    host_run_id=str(host_dispatch.get("run_id", host_dispatch.get("host_run_id", ""))),
                    dispatch_status=str(host_dispatch.get("status", "accepted")),
                )
            else:
                self._emit_trace("dispatch_prepared", record, actor="supervisor")
            self._persist_state()
            dispatched.append({
                "task_id": task_id,
                "run_id": self.run_id,
                "idempotency_key": record["task_packet"]["idempotency_key"],
                "parent_task_id": record.get("parent_task_id", ""),
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
            raw_artifacts = result.get("artifact_refs") or []
            artifact_refs = [str(item).strip() for item in raw_artifacts if item is not None and str(item).strip()] \
                if isinstance(raw_artifacts, (list, tuple)) else ([str(raw_artifacts).strip()] if str(raw_artifacts).strip() else [])
            return {
                "summary": str(summary).strip(),
                "evidence": list(result.get("evidence", [])),
                "risks": list(result.get("risks", [])),
                "next_steps": list(result.get("next_steps", result.get("next_step", [])))
                if isinstance(result.get("next_steps", result.get("next_step", [])), (list, tuple))
                else [str(result.get("next_steps", result.get("next_step", ""))).strip()],
                "artifact_refs": artifact_refs,
            }
        return {"summary": str(result).strip(), "evidence": [], "risks": [], "next_steps": [], "artifact_refs": []}

    def mark_done(
        self,
        task_id: str,
        *,
        result: Any = None,
        usage: dict[str, int] | None = None,
        model: str = "",
    ) -> dict[str, Any]:
        record = self._get(task_id)
        if record["status"] not in {"pending", "running", "review", "waiting_host"}:
            raise ValueError(f"当前状态不可标记完成：{task_id}")
        if record["status"] == "cancelled":
            raise ValueError(f"任务已取消：{task_id}")
        calls = int((usage or {}).get("tool_calls", 0))
        if calls < 0:
            raise ValueError("用量不能为负数")
        normalized_result = self._normalize_result(result)
        artifact_refs = list((normalized_result or {}).get("artifact_refs", []))
        resolved_model = str(model or "").strip() or str(record.get("model", ""))
        self._emit_trace(
            "task_completed",
            record,
            actor="employee",
            status="done",
            model=resolved_model,
            artifact_refs=artifact_refs,
        )
        record["usage"]["tool_calls"] += calls
        self._usage["tool_calls"] += calls
        record["status"] = "done"
        record["model"] = resolved_model
        record["result"] = normalized_result
        record["artifact_refs"] = artifact_refs
        record["qa"] = {"status": "not_run", "reason": "", "agent_id": "", "model": "", "evidence_refs": []}
        record["qa_dispatch_error"] = ""
        self._persist_state()
        return self.snapshot(task_id)

    def begin_qa_review(self, task_id: str, *, reviewer_id: str = "QA-001") -> dict[str, Any]:
        """Reserve an independent QA review and return its stable delivery key."""
        record = self._get(task_id)
        if record["status"] == "qa_review":
            return self.snapshot(task_id)
        if record["status"] != "done" or record.get("qa", {}).get("status") != "not_run":
            raise ValueError(f"仅已完成且待 QA 的任务可启动独立复核：{task_id}")
        reviewer_id = str(reviewer_id).strip() or "QA-001"
        review_id = f"{self.run_id}:{task_id}:qa:{len(record.get('qa_history', [])) + 1}"
        review = {
            "status": "in_progress",
            "reason": "",
            "agent_id": reviewer_id,
            "model": "",
            "evidence_refs": [],
            "review_id": review_id,
            "thread_id": "",
            "host_run_id": "",
            "dispatch_status": "pending",
        }
        self._emit_trace(
            "qa_review_started",
            record,
            actor=self.supervisor_id,
            status="qa_review",
            qa_status="in_progress",
            qa_agent_id=reviewer_id,
            qa_review_id=review_id,
        )
        record["status"] = "qa_review"
        record["qa"] = review
        record["qa_review_id"] = review_id
        record["qa_dispatch_error"] = ""
        self._persist_state()
        return self.snapshot(task_id)

    def record_qa_dispatch(
        self,
        task_id: str,
        review_id: str,
        *,
        thread_id: str = "",
        host_run_id: str = "",
        model: str = "",
        dispatch_status: str = "accepted",
    ) -> dict[str, Any]:
        """Persist the host receipt for an in-flight QA child Agent."""
        record = self._get(task_id)
        if record["status"] != "qa_review" or record.get("qa_review_id") != review_id:
            raise ValueError(f"QA 派发回执与当前复核不匹配：{task_id}")
        review = dict(record.get("qa", {}))
        review.update({
            "thread_id": str(thread_id).strip(),
            "host_run_id": str(host_run_id).strip(),
            "model": str(model).strip() or review.get("model", ""),
            "dispatch_status": str(dispatch_status).strip() or "accepted",
        })
        self._emit_trace(
            "qa_dispatch_result",
            record,
            actor="host_adapter",
            status="qa_review",
            thread_id=review["thread_id"],
            model=review["model"],
            host_run_id=review["host_run_id"],
            dispatch_status=review["dispatch_status"],
            qa_status="in_progress",
            qa_agent_id=review.get("agent_id", "QA-001"),
            qa_model=review["model"],
            qa_review_id=review_id,
        )
        record["qa"] = review
        self._persist_state()
        return self.snapshot(task_id)

    def qa_review_failed(self, task_id: str, review_id: str, *, reason: str) -> dict[str, Any]:
        """Release a task after host-side QA dispatch failure without faking a verdict."""
        record = self._get(task_id)
        if record["status"] != "qa_review" or record.get("qa_review_id") != review_id:
            raise ValueError(f"QA 失败回执与当前复核不匹配：{task_id}")
        message = str(reason).strip() or "QA 宿主调用失败"
        self._emit_trace(
            "qa_dispatch_failed",
            record,
            actor="host_adapter",
            status="done",
            reason=message,
            qa_status="dispatch_failed",
            qa_reason=message,
            qa_agent_id=record.get("qa", {}).get("agent_id", "QA-001"),
            qa_review_id=review_id,
        )
        record["status"] = "done"
        record["qa_dispatch_error"] = message
        record["qa"] = {
            "status": "not_run",
            "reason": "",
            "agent_id": str(record.get("qa", {}).get("agent_id", "QA-001")),
            "model": "",
            "evidence_refs": [],
            "review_id": review_id,
            "dispatch_status": "failed",
        }
        self._persist_state()
        return self.snapshot(task_id)

    def record_qa(
        self,
        task_id: str,
        *,
        status: str,
        reason: str = "",
        agent_id: str = "",
        model: str = "",
        evidence_refs: list[str] | tuple[str, ...] = (),
        host_run_id: str = "",
        thread_id: str = "",
    ) -> dict[str, Any]:
        """Record QA evidence and move the task into pass, rework, or blocked state."""
        normalized_status = str(status).strip().lower()
        if normalized_status not in {"passed", "rework_required", "blocked"}:
            raise ValueError("QA 状态必须是 passed、rework_required 或 blocked")
        if normalized_status != "passed" and not str(reason).strip():
            raise ValueError("QA 驳回或阻塞时必须记录原因")
        record = self._get(task_id)
        if record["status"] not in {"done", "qa_review"}:
            raise ValueError(f"任务结果完成后才能进行 QA：{task_id}")
        if record["status"] == "qa_review" and record.get("qa", {}).get("status") != "in_progress":
            raise ValueError(f"当前任务没有进行中的 QA 复核：{task_id}")
        previous_qa = record.get("qa", {})
        refs = [str(item).strip() for item in evidence_refs if str(item).strip()]
        qa_record = {
            "status": normalized_status,
            "reason": str(reason).strip(),
            "agent_id": str(agent_id).strip(),
            "model": str(model).strip(),
            "evidence_refs": refs,
            "review_id": str(record.get("qa_review_id", "")).strip(),
            "thread_id": str(thread_id or previous_qa.get("thread_id", "")).strip(),
            "host_run_id": str(host_run_id or previous_qa.get("host_run_id", "")).strip(),
        }
        next_rework_count = int(record.get("qa_rework_count", 0))
        if normalized_status == "passed":
            next_status = "done"
            next_failure_reason = ""
        elif normalized_status == "blocked":
            next_status = "blocked_qa"
            next_failure_reason = qa_record["reason"]
        else:
            next_rework_count += 1
            if next_rework_count <= self.max_qa_reworks:
                next_status = "review"
                next_failure_reason = qa_record["reason"]
            else:
                next_status = "blocked_qa"
                next_failure_reason = (
                    f"QA 返工上限 {self.max_qa_reworks} 已用尽；需主管重新评估任务范围或负责人"
                )
        self._emit_trace(
            "qa_reviewed",
            record,
            actor=qa_record["agent_id"] or "qa_agent",
            status=next_status,
            qa_rework_count=next_rework_count,
            qa_status=qa_record["status"],
            qa_reason=qa_record["reason"],
            qa_agent_id=qa_record["agent_id"],
            qa_model=qa_record["model"],
            qa_evidence_refs=refs,
            host_run_id=qa_record["host_run_id"],
            qa_review_id=qa_record["review_id"],
        )
        record["status"] = next_status
        record["failure_reason"] = next_failure_reason
        record["qa_rework_count"] = next_rework_count
        record.setdefault("qa_history", []).append(deepcopy(qa_record))
        record["qa"] = qa_record
        record["qa_dispatch_error"] = ""
        self._persist_state()
        return self.snapshot(task_id)

    def mark_failed(
        self,
        task_id: str,
        *,
        reason: str = "",
        usage: dict[str, int] | None = None,
        model: str = "",
    ) -> dict[str, Any]:
        """Finish a task as failed while keeping a compact, actionable reason."""
        record = self._get(task_id)
        if record["status"] not in {"pending", "running", "review", "paused", "waiting_host"}:
            raise ValueError(f"当前状态不可标记失败：{task_id}")
        if record["status"] in TERMINAL:
            return self.snapshot(task_id)
        calls = int((usage or {}).get("tool_calls", 0))
        if calls < 0:
            raise ValueError("用量不能为负数")
        resolved_model = str(model or "").strip() or str(record.get("model", ""))
        self._emit_trace(
            "task_failed",
            record,
            actor="employee",
            status="failed",
            reason=reason.strip(),
            model=resolved_model,
        )
        record["usage"]["tool_calls"] += calls
        self._usage["tool_calls"] += calls
        record["status"] = "failed"
        record["model"] = resolved_model
        record["failure_reason"] = reason.strip()
        self._persist_state()
        return self.snapshot(task_id)

    def set_max_concurrency(self, value: int) -> int:
        """Adjust the batch ceiling without interrupting already running work."""
        if value < 1:
            raise ValueError("并发上限必须大于 0")
        self.max_concurrency = value
        self._persist_state()
        return self.max_concurrency

    def pause(self, task_id: str, *, reason: str = "") -> dict[str, Any]:
        """Pause queued or running work; its task and thread identity are retained."""
        record = self._get(task_id)
        if record["status"] in TERMINAL:
            return self.snapshot(task_id)
        if record["status"] != "paused":
            record["paused_from_status"] = record["status"]
        record["status"] = "paused"
        record["cancel_reason"] = reason.strip()
        self._persist_state()
        return self.snapshot(task_id)

    def resume(self, task_id: str) -> dict[str, Any]:
        """Resume paused work and recompute dependency/budget waiting state."""
        record = self._get(task_id)
        if record["status"] in TERMINAL:
            return self.snapshot(task_id)
        if record["status"] not in {"paused", "blocked_qa"}:
            return self.snapshot(task_id)
        if record["status"] == "paused" and record.get("paused_from_status") == "qa_review":
            # The host review may still be running. Restore the same stable
            # review ID so a redelivery is idempotent and dependents stay held.
            record["status"] = "qa_review"
        elif not self._dependency_ready(record):
            record["status"] = "waiting_dependency"
        elif (
            self.total_tool_calls is not None
            and self._usage["tool_calls"] + record["budget"]["tool_calls"] > self.total_tool_calls
        ):
            record["status"] = "waiting_budget"
        else:
            record["status"] = "pending"
        record["cancel_reason"] = ""
        record["failure_reason"] = ""
        record["paused_from_status"] = ""
        self._persist_state()
        return self.snapshot(task_id)

    def cancel(self, task_id: str, *, reason: str = "") -> dict[str, Any]:
        record = self._get(task_id)
        if record["status"] in TERMINAL:
            return self.snapshot(task_id)
        record["status"] = "cancelled"
        record["cancel_reason"] = reason.strip()
        record["paused_from_status"] = ""
        self._persist_state()
        return self.snapshot(task_id)

    def _get(self, task_id: str) -> dict[str, Any]:
        if task_id not in self._tasks:
            raise KeyError(f"未知任务：{task_id}")
        return self._tasks[task_id]

    def snapshot(self, task_id: str) -> dict[str, Any]:
        record = self._get(task_id)
        qa = record.get("qa", {})
        return dict(
            record,
            usage=dict(record["usage"]),
            budget=dict(record["budget"]),
            depends_on=list(record["depends_on"]),
            artifact_refs=list(record.get("artifact_refs", [])),
            qa={**qa, "evidence_refs": list(qa.get("evidence_refs", []))},
            qa_history=[
                {**item, "evidence_refs": list(item.get("evidence_refs", []))}
                for item in record.get("qa_history", [])
            ],
        )

    def overview(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_count": len(self._tasks),
            "running": [item["task_id"] for item in self._tasks.values() if item["status"] == "running"],
            "completed": [item["task_id"] for item in self._tasks.values() if item["status"] == "done"],
            "awaiting_qa": [
                item["task_id"] for item in self._tasks.values()
                if item["status"] == "done" and item.get("qa", {}).get("status") == "not_run"
            ],
            "qa_in_progress": [
                item["task_id"] for item in self._tasks.values() if item["status"] == "qa_review"
            ],
            "waiting": [item["task_id"] for item in self._tasks.values() if item["status"].startswith("waiting")],
            "paused": [item["task_id"] for item in self._tasks.values() if item["status"] == "paused"],
            "rework": [item["task_id"] for item in self._tasks.values() if item["status"] == "review"],
            "qa_blocked": [item["task_id"] for item in self._tasks.values() if item["status"] == "blocked_qa"],
            "usage": dict(self._usage),
            "max_concurrency": self.max_concurrency,
            "total_tool_calls": self.total_tool_calls,
            "max_qa_reworks": self.max_qa_reworks,
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
                "run_id": self.run_id,
                "parent_task_id": record.get("parent_task_id", ""),
                "employee_id": record["employee_id"],
                "agent_id": record["agent_id"],
                "model": record.get("model", ""),
                "artifact_refs": list(record.get("artifact_refs", [])),
                "qa": dict(record.get("qa", {})),
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
            "run_id": self.run_id,
        }

    def plan(self) -> dict[str, Any]:
        """Return a compact batch view suitable for a CEO status update."""
        return {
            "mode": "batch",
            "run_id": self.run_id,
            "trace_path": str(self.trace_path) if self.trace_path is not None else "",
            "state_path": str(self.state_path) if self.state_path is not None else "",
            "max_qa_reworks": self.max_qa_reworks,
            "tasks": [self.snapshot(task_id) for task_id in self._tasks],
            "overview": self.overview(),
            "dispatch_policy": "reuse_existing_then_create_missing_conversations",
        }
