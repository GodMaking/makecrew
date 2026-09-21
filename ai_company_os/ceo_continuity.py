"""Durable CEO thread rotation without carrying full conversation history."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any, Callable


Clock = Callable[[], float]

_HANDOFF_FIELDS = (
    "company_memory_ref",
    "portfolio",
    "open_tasks",
    "active_decisions",
    "employee_status",
    "risks",
    "budgets",
    "next_actions",
    "evidence_refs",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(payload: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "digest"}
    return sha256(_canonical(unsigned).encode("utf-8")).hexdigest()


def _ids(items: Any, *keys: str) -> set[str]:
    values: set[str] = set()
    if not isinstance(items, list):
        return values
    for item in items:
        if isinstance(item, str) and item.strip():
            values.add(item.strip())
        elif isinstance(item, dict):
            for key in keys:
                value = str(item.get(key, "")).strip()
                if value:
                    values.add(value)
                    break
    return values


class CeoContinuityManager:
    """Persist CEO generations, handoff packages, and the active thread pointer."""

    def __init__(self, workspace: str | Path, *, clock: Clock = time.time) -> None:
        self.root = Path(workspace).expanduser().resolve()
        self.crew_dir = self.root / ".makecrew"
        self.state_path = self.crew_dir / "ceo-continuity.json"
        self.handoff_dir = self.crew_dir / "handoffs"
        self.clock = clock
        self._ensure_storage()

    @staticmethod
    def initial_state() -> dict[str, Any]:
        return {
            "version": 1,
            "ceo_id": "CEO-001",
            "active_thread_id": "",
            "generation": 0,
            "threads": [],
            "pending_handoff": None,
        }

    def _ensure_storage(self) -> None:
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write_json(self.state_path, self.initial_state())

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def _load_state(self) -> dict[str, Any]:
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("version") != 1:
            raise ValueError("CEO 连续性状态格式无效")
        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        active = [item for item in state.get("threads", []) if item.get("status") == "active"]
        active_id = str(state.get("active_thread_id", ""))
        if active_id and (len(active) != 1 or active[0].get("thread_id") != active_id):
            raise ValueError("CEO 活动线程指针与线程记录不一致")
        if not active_id and active:
            raise ValueError("存在活动 CEO 线程但缺少活动指针")
        self._write_json(self.state_path, state)

    @staticmethod
    def assess_context(used_tokens: int, context_window: int) -> dict[str, Any]:
        """Classify context pressure using stable rollover thresholds."""
        if used_tokens < 0 or context_window <= 0:
            raise ValueError("used_tokens 必须非负，context_window 必须大于 0")
        ratio = used_tokens / context_window
        percent = min(ratio * 100, 100.0)
        if ratio < 0.70:
            level, action = "normal", "continue"
        elif ratio < 0.85:
            level, action = "compress", "compress_completed_context"
        elif ratio < 0.95:
            level, action = "prepare_handoff", "prepare_ceo_handoff"
        else:
            level, action = "handoff_required", "complete_handoff_before_complex_work"
        return {
            "used_tokens": used_tokens,
            "context_window": context_window,
            "usage_ratio": round(ratio, 6),
            "usage_percent": round(percent, 2),
            "level": level,
            "action": action,
        }

    def _handoff_path(self, handoff_id: str) -> Path:
        return self.handoff_dir / f"{handoff_id}.json"

    def _read_handoff(self, handoff_id: str) -> dict[str, Any]:
        path = self._handoff_path(handoff_id)
        if not path.is_file():
            raise ValueError(f"接班包不存在：{handoff_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("digest") != _digest(payload):
            raise ValueError("接班包摘要校验失败")
        return payload

    def prepare_handoff(self, snapshot: dict[str, Any], current_thread_id: str) -> dict[str, Any]:
        """Create an idempotent, compact handoff package from explicit state fields."""
        thread_id = current_thread_id.strip()
        if not thread_id:
            raise ValueError("当前 CEO 线程 ID 不能为空")
        if not isinstance(snapshot, dict):
            raise ValueError("接班快照必须是 JSON 对象")
        state = self._load_state()
        if not state["active_thread_id"]:
            state["generation"] = 1
            state["active_thread_id"] = thread_id
            state["threads"].append({
                "thread_id": thread_id,
                "generation": 1,
                "status": "active",
                "started_at": self.clock(),
                "ended_at": None,
                "handoff_id": "",
            })
        elif state["active_thread_id"] != thread_id:
            raise ValueError("current_thread_id 不是当前活动 CEO 线程")

        pending = state.get("pending_handoff")
        if pending:
            existing = self._read_handoff(str(pending["handoff_id"]))
            if existing.get("from_thread_id") != thread_id:
                raise ValueError("已有其他 CEO 线程的接班流程待完成")
            unchanged = all(existing.get(field) == snapshot.get(field, "" if field == "company_memory_ref" else [])
                            for field in _HANDOFF_FIELDS)
            if unchanged:
                self._save_state(state)
                return existing
            if pending.get("candidate_thread_id"):
                raise ValueError("候选 CEO 已建立，接班包不能再刷新")
            for field in _HANDOFF_FIELDS:
                default = "" if field == "company_memory_ref" else []
                value = snapshot.get(field, default)
                if field != "company_memory_ref" and not isinstance(value, list):
                    raise ValueError(f"接班字段 {field} 必须是列表")
                existing[field] = deepcopy(value)
            existing["created_at"] = self.clock()
            existing["digest"] = _digest(existing)
            self._write_json(self._handoff_path(str(pending["handoff_id"])), existing)
            self._save_state(state)
            return existing

        next_generation = int(state["generation"]) + 1
        handoff_id = f"CEO-HANDOFF-{next_generation:06d}"
        payload: dict[str, Any] = {
            "handoff_id": handoff_id,
            "ceo_id": state["ceo_id"],
            "from_thread_id": thread_id,
            "from_generation": int(state["generation"]),
            "created_at": self.clock(),
        }
        for field in _HANDOFF_FIELDS:
            default: Any = "" if field == "company_memory_ref" else []
            value = snapshot.get(field, default)
            if field != "company_memory_ref" and not isinstance(value, list):
                raise ValueError(f"接班字段 {field} 必须是列表")
            payload[field] = deepcopy(value)
        payload["digest"] = _digest(payload)
        self._write_json(self._handoff_path(handoff_id), payload)
        state["pending_handoff"] = {
            "handoff_id": handoff_id,
            "candidate_thread_id": "",
            "verified": False,
            "verification": None,
        }
        self._save_state(state)
        return payload

    def register_candidate(self, thread_id: str, handoff_id: str) -> dict[str, Any]:
        candidate_id = thread_id.strip()
        if not candidate_id:
            raise ValueError("候选 CEO 线程 ID 不能为空")
        state = self._load_state()
        pending = state.get("pending_handoff") or {}
        if pending.get("handoff_id") != handoff_id:
            raise ValueError("接班 ID 与待处理接班流程不一致")
        if candidate_id == state.get("active_thread_id"):
            raise ValueError("候选 CEO 必须使用不同的新线程")
        existing_candidate = str(pending.get("candidate_thread_id", ""))
        if existing_candidate and existing_candidate != candidate_id:
            raise ValueError("接班流程已绑定其他候选线程")
        self._read_handoff(handoff_id)
        record = next((item for item in state["threads"] if item.get("thread_id") == candidate_id), None)
        if record is None:
            record = {
                "thread_id": candidate_id,
                "generation": int(state["generation"]) + 1,
                "status": "candidate",
                "started_at": self.clock(),
                "ended_at": None,
                "handoff_id": handoff_id,
            }
            state["threads"].append(record)
        elif record.get("status") != "candidate":
            raise ValueError("候选线程记录状态无效")
        pending["candidate_thread_id"] = candidate_id
        state["pending_handoff"] = pending
        self._save_state(state)
        return deepcopy(record)

    @staticmethod
    def _required_ids(handoff: dict[str, Any]) -> dict[str, set[str]]:
        high_risks = []
        for item in handoff.get("risks", []):
            if isinstance(item, str):
                high_risks.append(item)
            elif isinstance(item, dict):
                level = str(item.get("impact", item.get("severity", item.get("level", "")))).lower()
                if not level or level in {"high", "critical", "严重", "高"}:
                    high_risks.append(item)
        return {
            "project_ids": _ids(handoff.get("portfolio"), "project_id", "id"),
            "task_ids": _ids(handoff.get("open_tasks"), "task_id", "id"),
            "decision_ids": _ids(handoff.get("active_decisions"), "decision_id", "id"),
            "risk_ids": _ids(high_risks, "risk_id", "id"),
        }

    def verify_candidate(self, thread_id: str, handoff_id: str, verification: dict[str, Any]) -> dict[str, Any]:
        """Require the candidate to echo every operational identifier before activation."""
        state = self._load_state()
        pending = state.get("pending_handoff") or {}
        if pending.get("handoff_id") != handoff_id or pending.get("candidate_thread_id") != thread_id:
            raise ValueError("候选线程或接班 ID 与待处理流程不一致")
        if state.get("active_thread_id") == thread_id:
            raise ValueError("候选 CEO 已经处于活动状态")
        if not isinstance(verification, dict):
            raise ValueError("接班校验结果必须是 JSON 对象")
        handoff = self._read_handoff(handoff_id)
        expected = self._required_ids(handoff)
        missing: dict[str, list[str]] = {}
        for field, required in expected.items():
            values = verification.get(field, [])
            if not isinstance(values, list):
                raise ValueError(f"接班校验字段 {field} 必须是列表")
            received = {str(item).strip() for item in values if str(item).strip()}
            absent = sorted(required - received)
            if absent:
                missing[field] = absent
        provided_digest = str(verification.get("handoff_digest", "")).strip()
        if provided_digest != handoff["digest"]:
            missing["handoff_digest"] = [handoff["digest"]]
        if missing:
            raise ValueError(f"接班校验缺少必要状态：{_canonical(missing)}")
        checked = {
            "thread_id": thread_id,
            "handoff_id": handoff_id,
            "verified_at": self.clock(),
            "project_ids": sorted(expected["project_ids"]),
            "task_ids": sorted(expected["task_ids"]),
            "decision_ids": sorted(expected["decision_ids"]),
            "risk_ids": sorted(expected["risk_ids"]),
            "handoff_digest": handoff["digest"],
        }
        pending["verified"] = True
        pending["verification"] = checked
        state["pending_handoff"] = pending
        self._save_state(state)
        return checked

    def activate(self, thread_id: str, handoff_id: str) -> dict[str, Any]:
        """Atomically switch the local active pointer after successful verification."""
        state = self._load_state()
        pending = state.get("pending_handoff") or {}
        if pending.get("handoff_id") != handoff_id or pending.get("candidate_thread_id") != thread_id:
            raise ValueError("候选线程或接班 ID 与待处理流程不一致")
        if not pending.get("verified"):
            raise ValueError("候选 CEO 尚未通过接班校验")
        old_thread_id = str(state.get("active_thread_id", ""))
        now = self.clock()
        candidate = None
        for item in state["threads"]:
            if item.get("thread_id") == old_thread_id:
                item["status"] = "archived"
                item["ended_at"] = now
                item["handoff_id"] = handoff_id
            if item.get("thread_id") == thread_id:
                candidate = item
        if candidate is None or candidate.get("status") != "candidate":
            raise ValueError("候选 CEO 线程记录不存在或状态无效")
        candidate["status"] = "active"
        candidate["ended_at"] = None
        state["active_thread_id"] = thread_id
        state["generation"] = int(candidate["generation"])
        state["pending_handoff"] = None
        self._save_state(state)
        return {
            "status": "activated",
            "ceo_id": state["ceo_id"],
            "generation": state["generation"],
            "active_thread_id": thread_id,
            "archived_thread_id": old_thread_id,
            "handoff_id": handoff_id,
        }

    def status(self) -> dict[str, Any]:
        state = self._load_state()
        result = deepcopy(state)
        pending = result.get("pending_handoff")
        if pending:
            result["handoff_path"] = str(self._handoff_path(str(pending["handoff_id"])))
        return result


def build_ceo_handoff_prompt(handoff: dict[str, Any]) -> str:
    """Render a compact prompt that asks a new CEO thread for machine-checkable coverage."""
    required = CeoContinuityManager._required_ids(handoff)
    return (
        "你是 MakeCrew 的新一代 CEO 对话，角色 ID 仍为 CEO-001。\n"
        "只接收当前有效状态和引用；需要细节时按 evidence_refs 检索，不要要求复制旧对话全文。\n"
        "请核对项目、未完成任务、活动决策和高风险项，然后返回 verification JSON，"
        "字段为 project_ids、task_ids、decision_ids、risk_ids、handoff_digest。\n"
        f"预期标识：{_canonical({key: sorted(value) for key, value in required.items()})}\n"
        f"接班包：{_canonical(handoff)}"
    )
