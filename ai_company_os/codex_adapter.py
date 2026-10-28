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

from .capabilities import resolve_employee_tools, skill_ids_for_employee, tool_policy_for_employee
from .ceo_continuity import CeoContinuityManager, build_ceo_handoff_prompt
from .router import CORE_EMPLOYEE_PROFILES


SpawnSubagent = Callable[[str, dict[str, Any]], dict[str, Any]]
SendToThread = Callable[[str, str], dict[str, Any]]
OpenEmployeeThread = Callable[[str, str, str, dict[str, Any]], dict[str, Any]]
OpenSupervisorThread = Callable[[str, dict[str, Any]], dict[str, Any]]
SetThreadPinned = Callable[[str, bool], Any]
SetThreadArchived = Callable[[str, bool], Any]
RuntimeProbe = Callable[[], dict[str, Any]]


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
        "完成后必须返回 JSON：summary、evidence、risks、next_steps；如有文件或可复核产物，另列 artifact_refs 路径。\n"
        f"任务包：{_json(task_packet)}"
    )


def build_supervisor_prompt(aggregate: dict[str, Any]) -> str:
    """Render only compact employee deltas for a supervisor synthesis turn."""
    return (
        "你是 MakeCrew 的项目主管 Agent。请根据员工差量汇总当前批次，\n"
        "指出已完成、未完成、证据、风险和下一步，不要补写员工未提供的事实。\n"
        f"批次差量：{_json(aggregate)}"
    )


def build_qa_prompt(review_packet: dict[str, Any]) -> str:
    """Render an independent, evidence-first review prompt for a Codex QA Agent."""
    return (
        "你是 MakeCrew 的独立 QA 验收 Agent；你不参与被审任务的实现，也不继承执行员工的判断。\n"
        "只按 acceptance_gates 检查本次交付及可访问证据；不要仅凭员工自述通过。\n"
        "逐项核对验收标准，优先查看 artifact_refs 与 evidence；标出未覆盖标准、矛盾、不可复现项和风险。\n"
        "仅返回 JSON：status (passed|rework_required|blocked)、reason、evidence_refs。\n"
        "passed 必须附上可复核的 evidence_refs；rework_required/blocked 必须说明具体缺口或阻塞及对应证据。\n"
        "不要自行修改产物。\n"
        f"复核任务包：{_json(review_packet)}"
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
        runtime_probe: RuntimeProbe | None = None,
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
        self.runtime_probe = runtime_probe
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
            model = str(host_result.get("model", host_result.get("model_name", ""))).strip()
            if status in {"failed", "error"}:
                reason = str(host_result.get("reason", host_result.get("error", "Codex 员工执行失败")))
                return scheduler.mark_failed(task_id, reason=reason, usage=usage, model=model)
        else:
            result = host_result
            model = ""
        validation_error = self._validate_employee_result(result)
        if validation_error:
            return scheduler.mark_failed(
                task_id,
                reason=f"员工结果契约校验失败：{validation_error}",
                usage=usage,
                model=model,
            )
        return scheduler.mark_done(task_id, result=result, usage=usage, model=model)

    @staticmethod
    def _validate_employee_result(result: Any) -> str:
        """Validate the compact employee result before it enters the ledger.

        The scheduler accepts flexible values for portability.  The Codex host
        boundary is stricter: a completed employee turn must return a JSON
        object with a non-empty summary and list-shaped evidence fields, so a
        malformed host response is recorded as a retryable failure rather than
        being mistaken for successful work.
        """
        if not isinstance(result, dict):
            return "结果必须是 JSON 对象"
        if not str(result.get("summary", "")).strip():
            return "缺少非空 summary"
        for field in ("evidence", "risks", "next_steps", "artifact_refs"):
            if field in result and result[field] is not None and not isinstance(result[field], (list, tuple)):
                return f"{field} 必须是数组"
        return ""

    def request_qa_review(self, scheduler: Any, task_id: str) -> dict[str, Any]:
        """Dispatch a separate QA Agent and keep dependents behind the review gate.

        The stable review ID is also sent as a host idempotency key: if the host
        accepted a spawn but its acknowledgement was lost, retrying can safely
        recover the same logical review instead of creating a second verdict.
        """
        task = scheduler.snapshot(task_id)
        if self.spawn_subagent is None:
            return {
                "status": "queued",
                "reason": "codex_spawn_adapter_required_for_qa",
                "task": task,
            }

        worker_id = str(task.get("employee_id", "")).strip()
        reviewer_id = "QA-001" if worker_id != "QA-001" else "QA-REVIEW-001"
        task = scheduler.begin_qa_review(task_id, reviewer_id=reviewer_id)
        review_id = str(task.get("qa_review_id", "")).strip()
        profile = CORE_EMPLOYEE_PROFILES["QA-001"]
        reviewer = {
            "agent_id": reviewer_id,
            "role": profile.name,
            "department": profile.department,
            "skills": skill_ids_for_employee("QA-001"),
            "tools": list(profile.tools),
            "memory_scope": profile.memory_scope,
        }
        tool_subject = {"tools": list(profile.tools)}
        qa_packet = {
            "review_id": review_id,
            "run_id": task["run_id"],
            "task_id": task["task_id"],
            "project": task.get("project", ""),
            "task": task["task"],
            "acceptance_gates": task.get("acceptance_gates", []),
            "employee_id": worker_id,
            "employee_result": task.get("result"),
            "artifact_refs": task.get("artifact_refs", []),
            "file_scope": task.get("file_scope", []),
        }
        metadata = {
            "agent_id": reviewer_id,
            "agent_kind": "qa",
            "independent_review": True,
            "independent_of_agent_id": str(task.get("agent_id", worker_id)),
            "supervisor_id": task.get("supervisor_id", self.supervisor_id),
            "project": task.get("project", ""),
            "role": profile.name,
            "skills": reviewer["skills"],
            "tools": resolve_employee_tools(tool_subject, self.available_tools)
            if self.available_tools else list(profile.tools),
            "tool_policy": tool_policy_for_employee(tool_subject),
            "memory_scope": profile.memory_scope,
            "file_scope": list(task.get("file_scope", [])),
            "task_id": task_id,
            "review_id": review_id,
            "idempotency_key": review_id,
            "isolation": "isolated_thread",
        }
        try:
            response = self.spawn_subagent(build_qa_prompt(qa_packet), metadata)
        except Exception as exc:
            failed = scheduler.qa_review_failed(task_id, review_id, reason=f"{type(exc).__name__}: {exc}")
            return {"status": "host_error", "reason": str(exc), "review_id": review_id, "task": failed}
        response = response if isinstance(response, dict) else {"result": response}
        status = str(response.get("status", "")).strip().lower()
        if status in {"failed", "error", "rejected"}:
            reason = str(response.get("reason", response.get("error", "Codex QA Agent 派发失败")))
            failed = scheduler.qa_review_failed(task_id, review_id, reason=reason)
            return {"status": "host_error", "reason": reason, "review_id": review_id, "host": response, "task": failed}
        receipt = scheduler.record_qa_dispatch(
            task_id,
            review_id,
            thread_id=str(response.get("thread_id", "")),
            host_run_id=str(response.get("run_id", response.get("host_run_id", ""))),
            model=str(response.get("model", response.get("model_name", ""))),
            dispatch_status=status or ("accepted" if response.get("thread_id") or response.get("run_id") else "queued"),
        )
        return {
            "status": status or ("accepted" if response.get("thread_id") or response.get("run_id") else "queued"),
            "review_id": review_id,
            "reviewer": reviewer,
            "task": receipt,
            "host": response,
        }

    def complete_qa_review(
        self,
        scheduler: Any,
        task_id: str,
        host_result: Any,
        *,
        review_id: str,
    ) -> dict[str, Any]:
        """Validate an asynchronous QA response and record its evidence-backed verdict."""
        task = scheduler.snapshot(task_id)
        if task.get("status") != "qa_review" or task.get("qa_review_id") != review_id:
            raise ValueError(f"QA 回执已过期或与当前复核不匹配：{task_id}")
        if isinstance(host_result, dict):
            outer_status = str(host_result.get("status", "")).strip().lower()
            if outer_status in {"failed", "error", "rejected"}:
                reason = str(host_result.get("reason", host_result.get("error", "Codex QA Agent 执行失败")))
                failed = scheduler.qa_review_failed(task_id, review_id, reason=reason)
                return {"status": "host_error", "reason": reason, "task": failed}
            verdict = host_result.get("result", host_result)
            model = str(host_result.get("model", host_result.get("model_name", ""))).strip()
            host_run_id = str(host_result.get("run_id", host_result.get("host_run_id", ""))).strip()
            thread_id = str(host_result.get("thread_id", task.get("qa", {}).get("thread_id", ""))).strip()
            host_agent_id = str(host_result.get("agent_id", "")).strip()
        else:
            verdict, model, host_run_id, thread_id, host_agent_id = host_result, "", "", "", ""
        if isinstance(verdict, str):
            try:
                verdict = json.loads(verdict)
            except json.JSONDecodeError:
                verdict = None
        if not isinstance(verdict, dict):
            failed = scheduler.qa_review_failed(task_id, review_id, reason="QA 输出不是有效 JSON 对象")
            return {"status": "invalid_result", "task": failed}
        status = str(verdict.get("status", "")).strip().lower()
        reason = str(verdict.get("reason", "")).strip()
        raw_refs = verdict.get("evidence_refs", verdict.get("evidence", []))
        refs = [str(item).strip() for item in raw_refs if str(item).strip()] if isinstance(raw_refs, (list, tuple)) else []
        validation_error = ""
        if status not in {"passed", "rework_required", "blocked"}:
            validation_error = "QA 状态必须是 passed、rework_required 或 blocked"
        elif status != "passed" and not reason:
            validation_error = "QA 驳回或阻塞时必须说明具体原因"
        elif status == "passed" and not refs:
            validation_error = "QA 通过必须附可复核的 evidence_refs"
        if validation_error:
            failed = scheduler.qa_review_failed(task_id, review_id, reason=validation_error)
            return {"status": "invalid_result", "reason": validation_error, "task": failed}
        qa = task.get("qa", {})
        updated = scheduler.record_qa(
            task_id,
            status=status,
            reason=reason,
            agent_id=str(verdict.get("agent_id", host_agent_id or qa.get("agent_id", "QA-001"))).strip(),
            model=model or str(verdict.get("model", "")).strip() or str(qa.get("model", "")).strip(),
            evidence_refs=refs,
            host_run_id=host_run_id or str(qa.get("host_run_id", "")).strip(),
            thread_id=thread_id or str(qa.get("thread_id", "")).strip(),
        )
        return {**updated, "review_id": review_id, "verdict_status": status}

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
            "quality_review": {
                "available": self.spawn_subagent is not None,
                "required_callback": "spawn_subagent",
                "ready": self.spawn_subagent is not None,
                "mode": "independent_isolated_qa_agent",
            },
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
            "runtime_probe": {
                "configured": self.runtime_probe is not None,
                "status": "not_run",
                "reason": "调用 probe_runtime() 后才会执行宿主探测" if self.runtime_probe is not None else "宿主未提供非破坏性运行时探测回调",
            },
        }

    def probe_runtime(self) -> dict[str, Any]:
        """Run an injected, non-destructive host health probe."""
        if self.runtime_probe is None:
            return {
                "status": "not_configured",
                "reason": "宿主未提供 runtime_probe 回调",
            }
        try:
            response = self.runtime_probe()
        except Exception as exc:
            return {
                "status": "error",
                "reason": f"{type(exc).__name__}: {exc}",
            }
        if not isinstance(response, dict):
            return {
                "status": "invalid",
                "reason": "runtime_probe 必须返回 JSON 对象",
            }
        normalized = dict(response)
        status = str(normalized.get("status", "")).strip().lower()
        if status in {"ok", "pass", "passed", "ready", "connected"}:
            normalized["status"] = "passed"
        elif status in {"failed", "error", "blocked", "unavailable"}:
            normalized["status"] = status
        else:
            normalized["status"] = "invalid"
            normalized.setdefault("reason", "runtime_probe.status 必须是 ok、passed、failed 或 blocked")
        return normalized
