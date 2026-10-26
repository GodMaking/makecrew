"""Native streaming event adapters for common model tool-call protocols.

These adapters normalize provider events into ``ToolCallDeltaAssembler`` input;
they do not make API requests, validate tool schemas, or execute tools.
"""

from __future__ import annotations

import json
from typing import Any

from .tool_stream import IncompleteToolCallError, ToolCallDeltaAssembler


class ProviderStreamError(ValueError):
    """Raised when a provider stream is malformed, inconsistent, or fails."""


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderStreamError(f"provider stream 缺少 {field}")
    return value.strip()


def _sequence_event_id(event: dict[str, Any], *, provider: str, response_id: str) -> str:
    sequence = event.get("sequence_number")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ProviderStreamError(f"{provider} 事件缺少有效 sequence_number")
    return f"{provider}:{response_id}:{sequence}"


class OpenAIResponsesToolStreamAdapter:
    """Normalize OpenAI Responses API function-call streaming events.

    Event identity is the documented response ID plus ``sequence_number``.
    The final ``response.function_call_arguments.done`` value is checked against
    the accumulated deltas before the assembler marks the call complete.
    """

    def __init__(self) -> None:
        self._assembler = ToolCallDeltaAssembler()
        self._response_id = ""
        self._items: dict[str, dict[str, str]] = {}
        self._arguments: dict[str, str] = {}
        self._seen: dict[str, str] = {}
        self._finished = False
        self._terminal_received = False

    def _event_id(self, event: dict[str, Any]) -> str:
        event_response_id = str(event.get("response_id", "")).strip()
        if event_response_id and self._response_id and event_response_id != self._response_id:
            raise ProviderStreamError("OpenAI event 属于不同的 response")
        response_id = event_response_id or self._response_id or "unidentified"
        return _sequence_event_id(event, provider="openai-responses", response_id=response_id)

    def _feed_normalized(
        self,
        event_id: str,
        call_id: str,
        *,
        name_delta: str = "",
        arguments_delta: str = "",
        complete: bool = False,
    ) -> dict[str, Any] | None:
        normalized = {
            "event_id": event_id,
            "call_id": call_id,
            "name_delta": name_delta,
            "arguments_delta": arguments_delta,
            "complete": complete,
        }
        signature = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        previous = self._seen.get(event_id)
        if previous is not None:
            if previous != signature:
                raise ProviderStreamError(f"OpenAI sequence_number 冲突：{event_id}")
            return None
        completed = self._assembler.feed(normalized)
        self._seen[event_id] = signature
        return completed

    def feed(self, event: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Consume one event; expose calls only after a successful response.completed."""
        if self._finished:
            raise ProviderStreamError("OpenAI Responses stream 已结束")
        if not isinstance(event, dict):
            raise ProviderStreamError("OpenAI Responses event 必须是 JSON 对象")
        event_type = event.get("type")

        if event_type == "response.created":
            response = event.get("response")
            if not isinstance(response, dict):
                raise ProviderStreamError("response.created 缺少 response 对象")
            response_id = _required_text(response.get("id"), "response.id")
            if self._response_id and response_id != self._response_id:
                raise ProviderStreamError("同一 adapter 收到了不同的 OpenAI response")
            self._response_id = response_id
            return None

        if event_type in {"response.failed", "response.incomplete", "response.cancelled", "error"}:
            details = event.get("error") or event.get("response") or event
            self._finished = True
            raise ProviderStreamError(f"OpenAI Responses stream 失败：{str(details)[:1000]}")

        if event_type == "response.output_item.added":
            item = event.get("item")
            if not isinstance(item, dict) or item.get("type") != "function_call":
                return None
            item_id = _required_text(event.get("item_id") or item.get("id"), "item_id")
            call_id = _required_text(item.get("call_id"), "item.call_id")
            name = _required_text(item.get("name"), "item.name")
            prior_item = self._items.get(item_id)
            current = {"call_id": call_id, "name": name}
            if prior_item is not None and prior_item != current:
                raise ProviderStreamError(f"OpenAI item_id 内容冲突：{item_id}")
            prior_call = next((key for key, value in self._items.items() if value["call_id"] == call_id and key != item_id), "")
            if prior_call:
                raise ProviderStreamError(f"OpenAI call_id 重复映射到多个 item：{call_id}")
            self._feed_normalized(self._event_id(event), call_id, name_delta=name)
            self._items[item_id] = current
            self._arguments.setdefault(call_id, "")
            return None

        if event_type == "response.function_call_arguments.delta":
            item_id = _required_text(event.get("item_id"), "item_id")
            item = self._items.get(item_id)
            if item is None:
                raise ProviderStreamError(f"OpenAI arguments delta 的 item 尚未登记：{item_id}")
            delta = event.get("delta")
            if not isinstance(delta, str):
                raise ProviderStreamError("OpenAI arguments delta 必须是字符串")
            event_id = self._event_id(event)
            normalized_signature = json.dumps(
                {
                    "event_id": event_id,
                    "call_id": item["call_id"],
                    "name_delta": "",
                    "arguments_delta": delta,
                    "complete": False,
                }, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
            previous = self._seen.get(event_id)
            if previous is not None:
                if previous != normalized_signature:
                    raise ProviderStreamError(f"OpenAI sequence_number 冲突：{event_id}")
                return None
            self._feed_normalized(event_id, item["call_id"], arguments_delta=delta)
            self._arguments[item["call_id"]] += delta
            return None

        if event_type == "response.function_call_arguments.done":
            item_id = str(event.get("item_id", "")).strip()
            call_id = str(event.get("call_id", "")).strip()
            name = str(event.get("name", "")).strip()
            item = self._items.get(item_id) if item_id else None
            if item is not None:
                if call_id and call_id != item["call_id"]:
                    raise ProviderStreamError(f"OpenAI final call_id 与 item 不一致：{item_id}")
                if name and name != item["name"]:
                    raise ProviderStreamError(f"OpenAI final function name 与 item 不一致：{item_id}")
                call_id, name = item["call_id"], item["name"]
            call_id = _required_text(call_id, "call_id")
            name = _required_text(name, "name")
            arguments = event.get("arguments")
            if not isinstance(arguments, str):
                raise ProviderStreamError("OpenAI final arguments 必须是 JSON 字符串")
            accumulated = self._arguments.get(call_id, "")
            if accumulated and accumulated != arguments:
                raise ProviderStreamError("OpenAI delta 与最终 arguments 不一致")
            if item is None:
                self._items[item_id or f"call:{call_id}"] = {"call_id": call_id, "name": name}
            final_delta = arguments if not accumulated else ""
            self._feed_normalized(
                self._event_id(event), call_id, name_delta=name if item is None else "",
                arguments_delta=final_delta, complete=True,
            )
            self._arguments[call_id] = arguments
            return None

        if event_type == "response.completed":
            response = event.get("response")
            if not isinstance(response, dict):
                raise ProviderStreamError("response.completed 缺少 response 对象")
            terminal_id = _required_text(response.get("id"), "response.id")
            if self._response_id and terminal_id != self._response_id:
                raise ProviderStreamError("OpenAI 终止事件属于不同的 response")
            terminal_status = str(response.get("status", "")).strip()
            if terminal_status and terminal_status != "completed":
                self._finished = True
                raise ProviderStreamError(f"OpenAI response.completed 状态异常：{terminal_status}")
            calls = self._assembler.finish()
            self._terminal_received = True
            self._finished = True
            return calls
        return None

    def finish(self) -> None:
        """Verify successful terminal completion without emitting calls twice."""
        if self._terminal_received:
            return None
        self._finished = True
        self._assembler.finish()
        raise IncompleteToolCallError("OpenAI stream ended before response.completed")


class AnthropicMessagesToolStreamAdapter:
    """Normalize Anthropic Messages API ``tool_use`` SSE event payloads.

    Anthropic's documented event payloads identify content blocks by message ID
    plus index, but do not expose a per-delta sequence number. This adapter
    assigns local event IDs and expects each SSE event to be delivered once;
    hosts must restart a partial message as a new task attempt after interruption.
    """

    def __init__(self) -> None:
        self._assembler = ToolCallDeltaAssembler()
        self._message_id = ""
        self._blocks: dict[int, dict[str, Any]] = {}
        self._ignored_blocks: set[int] = set()
        self._event_index = 0
        self._finished = False
        self._terminal_received = False
        self._stop_reason = ""

    def _event_id(self, block_index: int, phase: str) -> str:
        self._event_index += 1
        message_id = self._message_id or "unidentified"
        return f"anthropic-messages:{message_id}:{block_index}:{phase}:{self._event_index}"

    def _feed_normalized(
        self,
        event_id: str,
        call_id: str,
        *,
        name_delta: str = "",
        arguments_delta: str = "",
        complete: bool = False,
    ) -> dict[str, Any] | None:
        return self._assembler.feed({
            "event_id": event_id,
            "call_id": call_id,
            "name_delta": name_delta,
            "arguments_delta": arguments_delta,
            "complete": complete,
        })

    @staticmethod
    def _block_index(event: dict[str, Any]) -> int:
        value = event.get("index")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProviderStreamError("Anthropic content block 缺少有效 index")
        return value

    def feed(self, event: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Consume one event; expose tools only after successful message_stop."""
        if self._finished:
            raise ProviderStreamError("Anthropic Messages stream 已结束")
        if not isinstance(event, dict):
            raise ProviderStreamError("Anthropic Messages event 必须是 JSON 对象")
        event_type = event.get("type")

        if event_type == "error":
            details = event.get("error", event)
            self._finished = True
            raise ProviderStreamError(f"Anthropic Messages stream 失败：{str(details)[:1000]}")
        if event_type == "message_start":
            message = event.get("message")
            if not isinstance(message, dict):
                raise ProviderStreamError("message_start 缺少 message 对象")
            message_id = _required_text(message.get("id"), "message.id")
            if self._message_id and self._message_id != message_id:
                raise ProviderStreamError("同一 adapter 收到了不同的 Anthropic message")
            self._message_id = message_id
            return None

        if event_type == "content_block_start":
            block = event.get("content_block")
            if not isinstance(block, dict):
                return None
            index = self._block_index(event)
            if block.get("type") != "tool_use":
                self._ignored_blocks.add(index)
                return None
            if not self._message_id:
                raise ProviderStreamError("tool_use block 出现在 message_start 之前")
            if index in self._blocks or index in self._ignored_blocks:
                raise ProviderStreamError(f"Anthropic 重复 content_block_start：{index}")
            call_id = _required_text(block.get("id"), "tool_use.id")
            name = _required_text(block.get("name"), "tool_use.name")
            initial_input = block.get("input")
            self._blocks[index] = {
                "call_id": call_id,
                "name": name,
                "arguments": "",
                "initial_empty_input": initial_input == {},
                "complete": False,
            }
            return self._feed_normalized(self._event_id(index, "start"), call_id, name_delta=name)

        if event_type == "content_block_delta":
            delta = event.get("delta")
            if not isinstance(delta, dict) or delta.get("type") != "input_json_delta":
                return None
            index = self._block_index(event)
            block = self._blocks.get(index)
            if block is None:
                if index in self._ignored_blocks:
                    return None
                raise ProviderStreamError(f"Anthropic input_json_delta 缺少 tool_use block：{index}")
            if block["complete"]:
                raise ProviderStreamError(f"Anthropic 已关闭的 tool_use block 又收到 delta：{index}")
            partial_json = delta.get("partial_json")
            if not isinstance(partial_json, str):
                raise ProviderStreamError("Anthropic partial_json 必须是字符串")
            block["arguments"] += partial_json
            return self._feed_normalized(
                self._event_id(index, "delta"), block["call_id"], arguments_delta=partial_json,
            )

        if event_type == "content_block_stop":
            index = self._block_index(event)
            block = self._blocks.get(index)
            if block is None:
                self._ignored_blocks.discard(index)
                return None
            if block["complete"]:
                raise ProviderStreamError(f"Anthropic tool_use block 重复关闭：{index}")
            completion_delta = "{}" if not block["arguments"] and block["initial_empty_input"] else ""
            block["complete"] = True
            self._feed_normalized(
                self._event_id(index, "stop"), block["call_id"],
                arguments_delta=completion_delta, complete=True,
            )
            block["arguments"] += completion_delta
            return None

        if event_type == "message_delta":
            delta = event.get("delta")
            if isinstance(delta, dict) and delta.get("stop_reason") is not None:
                stop_reason = str(delta.get("stop_reason")).strip()
                if stop_reason:
                    self._stop_reason = stop_reason
            return None

        if event_type == "message_stop":
            self._finished = True
            calls = self._assembler.finish()
            if calls and self._stop_reason != "tool_use":
                raise ProviderStreamError(
                    f"Anthropic tool_use blocks ended with stop_reason={self._stop_reason or 'missing'}"
                )
            self._terminal_received = True
            return calls
        return None

    def finish(self) -> None:
        """Verify successful terminal completion without emitting calls twice."""
        if self._terminal_received:
            return None
        self._finished = True
        self._assembler.finish()
        raise IncompleteToolCallError("Anthropic stream ended before message_stop")


__all__ = [
    "AnthropicMessagesToolStreamAdapter",
    "OpenAIResponsesToolStreamAdapter",
    "ProviderStreamError",
    "IncompleteToolCallError",
]
