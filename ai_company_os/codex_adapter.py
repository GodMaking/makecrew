"""Codex-native Agent adapter for MakeCrew's portable batch scheduler.

The scheduler owns routing, dependencies, budgets, and conflict state.  This
module translates that state into the small callback boundary a Codex host can
implement: reuse/create an employee thread, send a task packet, and return a
structured result.  It deliberately does not depend on a private Codex API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol


SpawnSubagent = Callable[[str, dict[str, Any]], dict[str, Any]]
SendToThread = Callable[[str, str], dict[str, Any]]


class CodexHost(Protocol):
    """Optional host callbacks needed for native Codex subagent execution."""

    def spawn_subagent(self, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]: ...

    def send_to_thread(self, thread_id: str, prompt: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CodexAgentRef:
    """Inspectable identity for one supervisor or employee Agent."""

    agent_id: str
    thread_id: str
    kind: str
    project: str = ""
    supervisor_id: str = ""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_employee_prompt(task_packet: dict[str, Any]) -> str:
    """Render a compact, copy-safe prompt for one Codex employee Agent."""
    return (
        "你是 MakeCrew 的员工 Agent，只执行任务包中声明的范围。\n"
        "不要读取或复述无关员工的完整历史；只使用项目摘要和本次任务差量。\n"
        "完成后必须返回 JSON：summary、evidence、risks、next_steps。\n"
        f"任务包：{_json(task_packet)}"
    )


def build_supervisor_prompt(aggregate: dict[str, Any]) -> str:
    """Render only compact employee deltas for a supervisor synthesis turn."""
    return (
        "你是 MakeCrew 的项目主管 Agent。请根据员工差量汇总当前批次，\n"
        "指出已完成、未完成、证据、风险和下一步，不要补写员工未提供的事实。\n"
        f"批次差量：{_json(aggregate)}"
    )


class CodexAdapter:
    """Bridge BatchScheduler callbacks to a Codex host.

    ``spawn_subagent`` and ``send_to_thread`` are intentionally injected.  A
    desktop host can map them to native subagent/thread operations while a test
    or another host can use deterministic fakes.
    """

    def __init__(
        self,
        *,
        supervisor_id: str = "PM-001",
        supervisor_thread_id: str = "",
        spawn_subagent: SpawnSubagent | None = None,
        send_to_thread: SendToThread | None = None,
    ) -> None:
        self.supervisor_id = supervisor_id.strip() or "PM-001"
        self.supervisor_thread_id = supervisor_thread_id.strip()
        self.spawn_subagent = spawn_subagent
        self.send_to_thread = send_to_thread
        self._employees: dict[tuple[str, str], CodexAgentRef] = {}

    @property
    def supervisor(self) -> CodexAgentRef:
        return CodexAgentRef(
            agent_id=self.supervisor_id,
            thread_id=self.supervisor_thread_id,
            kind="supervisor",
        )

    def register_employee(
        self,
        *,
        employee_id: str,
        project: str,
        thread_id: str,
        agent_id: str = "",
    ) -> CodexAgentRef:
        """Register an existing host thread so future tasks can reuse it."""
        ref = CodexAgentRef(
            agent_id=agent_id.strip() or employee_id,
            thread_id=thread_id.strip(),
            kind="employee",
            project=project,
            supervisor_id=self.supervisor_id,
        )
        if ref.thread_id:
            self._employees[(employee_id, project)] = ref
        return ref

    def open_employee_thread(self, employee_id: str, project: str, role: str) -> dict[str, Any]:
        """BatchScheduler ``thread_adapter`` callback.

        Existing Codex threads are reused.  New threads are intentionally
        created only when the task packet is available in ``dispatch``.
        """
        ref = self._employees.get((employee_id, project))
        if ref:
            return {
                "thread_id": ref.thread_id,
                "agent_id": ref.agent_id,
                "reused": True,
                "kind": ref.kind,
            }
        return {"thread_id": "", "agent_id": employee_id, "reused": False, "role": role}

    def dispatch(self, thread_id: str, task_packet: dict[str, Any]) -> dict[str, Any]:
        """BatchScheduler ``agent_dispatcher`` callback.

        If no thread exists, create exactly one child Agent using the packet's
        employee identity.  The returned thread ID is consumed by the
        scheduler and retained for follow-up tasks.
        """
        employee = task_packet.get("employee", {})
        employee_id = str(employee.get("agent_id", "")).strip() or "TEMP-UNKNOWN"
        project = str(task_packet.get("project", ""))
        if not thread_id:
            if self.spawn_subagent is None:
                return {
                    "status": "queued",
                    "reason": "codex_spawn_adapter_required",
                    "agent_id": employee_id,
                }
            metadata = {
                "agent_id": employee_id,
                "agent_kind": "employee",
                "supervisor_id": self.supervisor_id,
                "project": project,
                "role": employee.get("role", "任务员工"),
                "skills": list(employee.get("skills", [])),
                "tools": list(employee.get("tools", [])),
                "file_scope": list(task_packet.get("file_scope", [])),
                "isolation": task_packet.get("isolation", "shared_thread"),
            }
            response = self.spawn_subagent(build_employee_prompt(task_packet), metadata)
            response = response if isinstance(response, dict) else {"result": response}
            thread_id = str(response.get("thread_id", "")).strip()
            if thread_id:
                self.register_employee(
                    employee_id=employee_id,
                    project=project,
                    thread_id=thread_id,
                    agent_id=str(response.get("agent_id", employee_id)),
                )
            return {
                **response,
                "status": response.get("status", "accepted" if thread_id else "queued"),
                "thread_id": thread_id,
                "agent_id": str(response.get("agent_id", employee_id)),
                "host": response,
            }
        if self.send_to_thread is None:
            return {
                "status": "queued",
                "reason": "codex_send_adapter_required",
                "thread_id": thread_id,
                "agent_id": employee_id,
            }
        response = self.send_to_thread(thread_id, build_employee_prompt(task_packet))
        response = response if isinstance(response, dict) else {"result": response}
        return {
            **response,
            "status": response.get("status", "accepted"),
            "thread_id": thread_id,
            "agent_id": str(response.get("agent_id", employee_id)),
            "host": response,
        }

    def complete(self, scheduler: Any, task_id: str, host_result: Any, *, usage: dict[str, int] | None = None) -> dict[str, Any]:
        """Validate a host result and write it back through ``mark_done``."""
        if isinstance(host_result, dict):
            result = host_result.get("result", host_result)
            status = str(host_result.get("status", "")).lower()
            if status in {"failed", "error"}:
                reason = str(host_result.get("reason", host_result.get("error", "Codex 员工执行失败")))
                return scheduler.mark_failed(task_id, reason=reason, usage=usage)
        else:
            result = host_result
        return scheduler.mark_done(task_id, result=result, usage=usage)

    def summarize(self, scheduler: Any) -> dict[str, Any]:
        """Send the compact batch delta to the supervisor when a host callback exists."""
        aggregate = scheduler.aggregate_results()
        if not self.supervisor_thread_id or self.send_to_thread is None:
            return {"status": "queued", "reason": "codex_supervisor_adapter_required", "aggregate": aggregate}
        response = self.send_to_thread(self.supervisor_thread_id, build_supervisor_prompt(aggregate))
        response = response if isinstance(response, dict) else {"result": response}
        return {
            **response,
            "status": response.get("status", "accepted"),
            "supervisor_id": self.supervisor_id,
            "thread_id": self.supervisor_thread_id,
            "aggregate": aggregate,
            "host": response,
        }

    def audit(self, *, max_concurrency: int = 3) -> dict[str, Any]:
        """Report whether the callbacks needed for native execution are wired."""
        available = []
        if self.spawn_subagent is not None:
            available.append("spawn_subagent")
        if self.send_to_thread is not None:
            available.append("send_to_thread")
        missing = [name for name in ("spawn_subagent", "send_to_thread") if name not in available]
        warnings = []
        if max_concurrency > 3:
            warnings.append("Codex 原生并发建议不超过 3；请确认宿主限制后再提高。")
        return {
            "supervisor": {
                "agent_id": self.supervisor_id,
                "agent_kind": "supervisor",
                "thread_id": self.supervisor_thread_id,
            },
            "available": available,
            "missing": missing,
            "ready": not missing,
            "max_concurrency": max_concurrency,
            "warnings": warnings,
        }
