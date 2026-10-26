"""Provider-neutral assembly for normalized incremental tool-call events.

Provider adapters translate their native event shapes into this small contract;
this module never executes a tool or guesses whether a value is a delta.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


class IncompleteToolCallError(ValueError):
    """Raised when a stream ends while one or more tool calls are incomplete."""


class ToolCallDeltaAssembler:
    """Accumulate explicit argument deltas and emit a validated call once.

    Normalized input events contain ``event_id``, ``call_id``, optional
    ``name_delta`` / ``arguments_delta``, and optional boolean ``complete``.
    Duplicate event IDs with identical content are ignored; collisions fail.
    A completed call is emitted only when its full argument string parses as a
    JSON object.
    """

    def __init__(self) -> None:
        self._calls: dict[str, dict[str, Any]] = {}
        self._seen_events: dict[str, str] = {}
        self._completed: list[dict[str, Any]] = []

    @property
    def pending_call_ids(self) -> tuple[str, ...]:
        return tuple(call_id for call_id, state in self._calls.items() if not state["complete"])

    @property
    def completed_calls(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(self._completed))

    def feed(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Consume one normalized event; return a completed call once, or None."""
        if not isinstance(event, dict):
            raise ValueError("工具流事件必须是对象")
        event_id = event.get("event_id")
        call_id = event.get("call_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("工具流事件缺少 event_id")
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("工具流事件缺少 call_id")
        event_id, call_id = event_id.strip(), call_id.strip()
        name_delta = event.get("name_delta", "")
        arguments_delta = event.get("arguments_delta", "")
        complete = event.get("complete", False)
        if not isinstance(name_delta, str) or not isinstance(arguments_delta, str):
            raise ValueError("工具流增量字段必须是字符串")
        if not isinstance(complete, bool):
            raise ValueError("工具流 complete 必须是布尔值")
        try:
            encoded_event = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("工具流事件必须可序列化") from exc

        previous_event = self._seen_events.get(event_id)
        if previous_event is not None:
            if previous_event != encoded_event:
                raise ValueError(f"event_id 内容冲突：{event_id}")
            return None

        current = self._calls.get(call_id, {"name": "", "arguments": "", "complete": False})
        if current["complete"]:
            raise ValueError(f"工具调用已完成：{call_id}")
        candidate_name = current["name"] + name_delta
        candidate_arguments = current["arguments"] + arguments_delta
        completed_call = None
        if complete:
            if not candidate_name.strip():
                raise ValueError(f"工具调用缺少名称：{call_id}")
            try:
                arguments = json.loads(candidate_arguments)
            except json.JSONDecodeError as exc:
                raise ValueError(f"工具参数 JSON 无效：{call_id}") from exc
            if not isinstance(arguments, dict):
                raise ValueError(f"工具参数必须是 JSON 对象：{call_id}")
            completed_call = {
                "call_id": call_id,
                "name": candidate_name.strip(),
                "arguments": arguments,
            }

        self._seen_events[event_id] = encoded_event
        self._calls[call_id] = {
            "name": candidate_name,
            "arguments": candidate_arguments,
            "complete": complete,
        }
        if completed_call is not None:
            self._completed.append(completed_call)
            return deepcopy(completed_call)
        return None

    def finish(self) -> list[dict[str, Any]]:
        """Confirm all calls are complete and return a defensive result copy."""
        if self.pending_call_ids:
            pending = ", ".join(self.pending_call_ids)
            raise IncompleteToolCallError(f"工具流结束时仍有未完成调用：{pending}")
        return list(deepcopy(self._completed))
