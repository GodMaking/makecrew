"""Small, restart-friendly task ledger for the local MakeCrew MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from time import time
from uuid import uuid4


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"


_TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.BLOCKED, TaskStatus.REVIEW, TaskStatus.DONE, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.REVIEW: {TaskStatus.IN_PROGRESS, TaskStatus.DONE, TaskStatus.CANCELLED},
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}


@dataclass
class TaskEvent:
    status: str
    note: str = ""
    at: float = field(default_factory=time)


@dataclass
class TaskRecord:
    task_id: str
    title: str
    project: str
    assignee: str
    budget: dict[str, int]
    status: str = TaskStatus.PENDING
    usage: dict[str, int] = field(default_factory=lambda: {"tool_calls": 0, "rounds": 0})
    events: list[TaskEvent] = field(default_factory=list)


class TaskLedger:
    """In-memory ledger with JSON-friendly snapshots and strict state changes."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._path = Path(path) if path else None
        if self._path and self._path.exists():
            self._load()

    def _persist(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.export(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path)

    def _load(self) -> None:
        try:
            records = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"任务台账文件无效: {self._path}") from exc
        for raw in records:
            events = [TaskEvent(**event) for event in raw.pop("events", [])]
            self._tasks[raw["task_id"]] = TaskRecord(events=events, **raw)

    def create(self, title: str, *, project: str = "", assignee: str = "", budget: int | dict[str, int] = 0) -> TaskRecord:
        if not title.strip():
            raise ValueError("任务标题不能为空")
        limits = {"tool_calls": int(budget), "rounds": int(budget)} if isinstance(budget, int) else {
            "tool_calls": int(budget.get("tool_calls", 0)),
            "rounds": int(budget.get("rounds", 0)),
        }
        if any(value < 0 for value in limits.values()):
            raise ValueError("任务预算不能为负数")
        record = TaskRecord(str(uuid4()), title.strip(), project, assignee, limits)
        self._tasks[record.task_id] = record
        self._persist()
        return record

    def get(self, task_id: str) -> TaskRecord:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"未知任务: {task_id}") from exc

    def transition(self, task_id: str, status: str | TaskStatus, *, note: str = "") -> TaskRecord:
        record = self.get(task_id)
        try:
            target = TaskStatus(status)
        except ValueError as exc:
            raise ValueError(f"未知任务状态: {status}") from exc
        current = TaskStatus(record.status)
        if target not in _TRANSITIONS[current]:
            raise ValueError(f"不允许从 {current.value} 转为 {target.value}")
        record.status = target.value
        record.events.append(TaskEvent(target.value, note.strip()))
        self._persist()
        return record

    def resume(self, task_id: str) -> TaskRecord:
        return self.transition(task_id, TaskStatus.IN_PROGRESS, note="任务已恢复")

    def record_usage(self, task_id: str, *, tool_calls: int = 0, rounds: int = 0) -> TaskRecord:
        if tool_calls < 0 or rounds < 0:
            raise ValueError("用量不能为负数")
        record = self.get(task_id)
        record.usage["tool_calls"] += tool_calls
        record.usage["rounds"] += rounds
        self._persist()
        return record

    def snapshot(self, task_id: str) -> dict:
        record = self.get(task_id)
        budget_remaining = {key: max(0, record.budget[key] - record.usage[key]) for key in record.budget}
        return {
            "task_id": record.task_id,
            "title": record.title,
            "project": record.project,
            "assignee": record.assignee,
            "status": record.status,
            "usage": dict(record.usage),
            "budget": dict(record.budget),
            "budget_remaining": budget_remaining,
            "last_note": record.events[-1].note if record.events else "",
            "last_blocked_note": next((event.note for event in reversed(record.events) if event.status == TaskStatus.BLOCKED.value), ""),
            "event_count": len(record.events),
        }

    def export(self) -> list[dict]:
        """Return a portable, non-conversational state export."""
        return [asdict(record) for record in self._tasks.values()]
