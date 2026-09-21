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

from .capabilities import resolve_employee_tools, tool_policy_for_employee
from .ceo_continuity import CeoContinuityManager, build_ceo_handoff_prompt


SpawnSubagent = Callable[[str, dict[str, Any]], dict[str, Any]]
SendToThread = Callable[[str, str], dict[str, Any]]
OpenEmployeeThread = Callable[[str, str, str, dict[str, Any]], dict[str, Any]]
OpenSupervisorThread = Callable[[str, dict[str, Any]], dict[str, Any]]
SetThreadPinned = Callable[[str, bool], Any]
SetThreadArchived = Callable[[str, bool], Any]


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
        "先按任务包中的 tool_policy 枚举宿主本轮实际启用的工具；通配符只代表已启用工具，不代表虚构能力。\n"
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
        open_employee_thread: OpenEmployeeThread | None = None,
        open_supervisor_thread: OpenSupervisorThread | None = None,
        set_thread_pinned: SetThreadPinned | None = None,
        set_thread_archived: SetThreadArchived | None = None,
        available_tools: list[str] | tuple[str, ...] | set[str] = (),
    ) -> None:
        self.supervisor_id = supervisor_id.strip() or "PM-001"
        self.supervisor_thread_id = supervisor_thread_id.strip()
        self.spawn_subagent = spawn_subagent
        self.send_to_thread = send_to_thread
        self.open_employee_thread = open_employee_thread
        self.open_supervisor_thread = open_supervisor_thread
        self.set_thread_pinned = set_thread_pinned
        self.set_thread_archived = set_thread_archived
        self.available_tools = tuple(available_tools)
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
        if self.open_employee_thread is None:
            return {"thread_id": "", "agent_id": employee_id, "reused": False, "role": role,
                    "status": "pending_host_adapter", "reason": "codex_open_employee_thread_required"}
        response = self.open_employee_thread(employee_id, project, role, {
            "supervisor_id": self.supervisor_id,
            "agent_kind": "employee",
        })
        response = response if isinstance(response, dict) else {"result": response}
        thread_id = str(response.get("thread_id", "")).strip()
        if thread_id:
            self.register_employee(employee_id=employee_id, project=project, thread_id=thread_id,
                                   agent_id=str(response.get("agent_id", employee_id)))
        return {**response, "thread_id": thread_id, "agent_id": str(response.get("agent_id", employee_id)),
                "reused": False}

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
            ref = self._employees.get((employee_id, project))
            if ref:
                thread_id = ref.thread_id
                if thread_id and self.send_to_thread is not None:
                    response = self.send_to_thread(thread_id, build_employee_prompt(task_packet))
                    response = response if isinstance(response, dict) else {"result": response}
                    return {**response, "status": response.get("status", "accepted"), "thread_id": thread_id,
                            "agent_id": str(response.get("agent_id", employee_id)), "reused": True, "host": response}
            had_ref = bool(thread_id)
            opened = self.open_employee_thread(employee_id, project, str(employee.get("role", "任务员工"))) if self.open_employee_thread and not had_ref else {}
            thread_id = thread_id or str(opened.get("thread_id", "")).strip()
            if thread_id:
                self.register_employee(employee_id=employee_id, project=project, thread_id=thread_id,
                                       agent_id=str(opened.get("agent_id", employee_id)))
                if self.send_to_thread is not None:
                    response = self.send_to_thread(thread_id, build_employee_prompt(task_packet))
                    response = response if isinstance(response, dict) else {"result": response}
                    return {**response, "status": response.get("status", "accepted"), "thread_id": thread_id,
                            "agent_id": str(response.get("agent_id", employee_id)), "host": response}
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
                "tools": resolve_employee_tools(
                    {**employee, "tool_policy": task_packet.get("tool_policy", employee.get("tool_policy", {}))},
                    self.available_tools,
                ) if self.available_tools else list(employee.get("tools", [])),
                "tool_policy": dict(task_packet.get("tool_policy", employee.get("tool_policy", {})))
                or tool_policy_for_employee(employee),
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

    @staticmethod
    def _verification_from_response(response: dict[str, Any]) -> dict[str, Any] | None:
        verification = response.get("verification")
        if isinstance(verification, dict):
            return verification
        result = response.get("result")
        if isinstance(result, dict):
            verification = result.get("verification", result)
            return verification if isinstance(verification, dict) else None
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                return None
            verification = parsed.get("verification", parsed) if isinstance(parsed, dict) else None
            return verification if isinstance(verification, dict) else None
        return None

    def rollover_ceo(
        self,
        continuity: CeoContinuityManager,
        snapshot: dict[str, Any],
        *,
        current_thread_id: str = "",
    ) -> dict[str, Any]:
        """Run a verified CEO handoff through explicit Codex host callbacks.

        The durable active pointer is switched last. If a host callback raises
        or the candidate omits verification fields, the old CEO stays active.
        """
        old_thread_id = current_thread_id.strip() or self.supervisor_thread_id
        handoff = continuity.prepare_handoff(snapshot, old_thread_id)
        continuity_status = continuity.status()
        existing_candidate = str(
            (continuity_status.get("pending_handoff") or {}).get("candidate_thread_id", "")
        ).strip()
        required_callbacks = {
            "send_to_thread": self.send_to_thread,
            "set_thread_pinned": self.set_thread_pinned,
            "set_thread_archived": self.set_thread_archived,
        }
        if not existing_candidate:
            required_callbacks["open_supervisor_thread"] = self.open_supervisor_thread
        missing = [name for name, callback in required_callbacks.items() if callback is None]
        if missing:
            return {
                "status": "pending_host_adapter",
                "handoff_id": handoff["handoff_id"],
                "active_thread_id": continuity.status()["active_thread_id"],
                "missing_callbacks": missing,
            }

        if existing_candidate:
            new_thread_id = existing_candidate
            opened = {"thread_id": new_thread_id, "reused": True}
        else:
            opened = self.open_supervisor_thread("CEO-001", {
                "agent_kind": "ceo",
                "handoff_id": handoff["handoff_id"],
                "generation": int(handoff["from_generation"]) + 1,
            })
            opened = opened if isinstance(opened, dict) else {"result": opened}
            new_thread_id = str(opened.get("thread_id", "")).strip()
            if not new_thread_id:
                return {
                    "status": "pending_host_thread",
                    "handoff_id": handoff["handoff_id"],
                    "active_thread_id": continuity.status()["active_thread_id"],
                    "host": opened,
                }
            continuity.register_candidate(new_thread_id, handoff["handoff_id"])
        response = self.send_to_thread(new_thread_id, build_ceo_handoff_prompt(handoff))
        response = response if isinstance(response, dict) else {"result": response}
        verification = self._verification_from_response(response)
        if verification is None:
            return {
                "status": "awaiting_candidate_verification",
                "handoff_id": handoff["handoff_id"],
                "candidate_thread_id": new_thread_id,
                "active_thread_id": continuity.status()["active_thread_id"],
                "host": response,
            }
        continuity.verify_candidate(new_thread_id, handoff["handoff_id"], verification)

        # Complete host presentation changes before the durable pointer switch.
        # A callback failure therefore leaves the old CEO active in local state.
        try:
            self.set_thread_pinned(new_thread_id, True)
            if old_thread_id:
                self.set_thread_pinned(old_thread_id, False)
                self.set_thread_archived(old_thread_id, True)
            result = continuity.activate(new_thread_id, handoff["handoff_id"])
        except Exception:
            # Best-effort host compensation; the durable pointer is still old
            # because activate() is the final operation.
            if old_thread_id:
                try:
                    self.set_thread_archived(old_thread_id, False)
                    self.set_thread_pinned(old_thread_id, True)
                except Exception:
                    pass
            try:
                self.set_thread_pinned(new_thread_id, False)
            except Exception:
                pass
            raise
        self.supervisor_id = "CEO-001"
        self.supervisor_thread_id = new_thread_id
        return {**result, "host": response}

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
            "ceo_rollover": {
                "available": [
                    name for name, callback in (
                        ("open_supervisor_thread", self.open_supervisor_thread),
                        ("set_thread_pinned", self.set_thread_pinned),
                        ("set_thread_archived", self.set_thread_archived),
                    ) if callback is not None
                ],
                "ready": all(callback is not None for callback in (
                    self.open_supervisor_thread,
                    self.send_to_thread,
                    self.set_thread_pinned,
                    self.set_thread_archived,
                )),
            },
        }
