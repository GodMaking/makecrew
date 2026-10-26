import unittest

from ai_company_os.provider_streams import (
    AnthropicMessagesToolStreamAdapter,
    OpenAIResponsesToolStreamAdapter,
    ProviderStreamError,
)
from ai_company_os.tool_stream import IncompleteToolCallError


class OpenAIResponsesToolStreamAdapterTests(unittest.TestCase):
    def test_maps_response_events_and_validates_final_arguments_once(self):
        adapter = OpenAIResponsesToolStreamAdapter()
        self.assertIsNone(adapter.feed({
            "type": "response.created", "sequence_number": 0,
            "response": {"id": "resp-1"},
        }))
        self.assertIsNone(adapter.feed({
            "type": "response.output_item.added", "sequence_number": 1,
            "item_id": "item-1",
            "item": {"type": "function_call", "id": "item-1", "call_id": "call-1", "name": "write_file"},
        }))
        first_delta = {
            "type": "response.function_call_arguments.delta", "sequence_number": 2,
            "item_id": "item-1", "delta": '{"path":"README.md",',
        }
        self.assertIsNone(adapter.feed(first_delta))
        self.assertIsNone(adapter.feed(first_delta))
        self.assertIsNone(adapter.feed({
            "type": "response.function_call_arguments.delta", "sequence_number": 3,
            "item_id": "item-1", "delta": '"content":"hello"}',
        }))
        self.assertIsNone(adapter.feed({
            "type": "response.function_call_arguments.done", "sequence_number": 4,
            "item_id": "item-1", "call_id": "call-1", "name": "write_file",
            "arguments": '{"path":"README.md","content":"hello"}',
        }))

        self.assertEqual(adapter.feed({
            "type": "response.completed", "sequence_number": 5,
            "response": {"id": "resp-1", "status": "completed"},
        }), [{
            "call_id": "call-1", "name": "write_file",
            "arguments": {"path": "README.md", "content": "hello"},
        }])
        self.assertIsNone(adapter.finish())

    def test_final_arguments_without_delta_are_supported(self):
        adapter = OpenAIResponsesToolStreamAdapter()
        adapter.feed({"type": "response.created", "sequence_number": 0, "response": {"id": "r"}})
        adapter.feed({
            "type": "response.function_call_arguments.done", "sequence_number": 1,
            "item_id": "i", "call_id": "c", "name": "lookup", "arguments": '{"q":"x"}',
        })
        self.assertEqual(adapter.feed({
            "type": "response.completed", "sequence_number": 2,
            "response": {"id": "r", "status": "completed"},
        }), [{"call_id": "c", "name": "lookup", "arguments": {"q": "x"}}])
        self.assertIsNone(adapter.finish())

    def test_done_event_must_match_accumulated_delta_text(self):
        adapter = OpenAIResponsesToolStreamAdapter()
        adapter.feed({"type": "response.created", "sequence_number": 0, "response": {"id": "r"}})
        adapter.feed({
            "type": "response.output_item.added", "sequence_number": 1, "item_id": "i",
            "item": {"type": "function_call", "id": "i", "call_id": "c", "name": "lookup"},
        })
        adapter.feed({
            "type": "response.function_call_arguments.delta", "sequence_number": 2,
            "item_id": "i", "delta": '{"q":"x"}',
        })
        with self.assertRaisesRegex(ProviderStreamError, "与最终 arguments 不一致"):
            adapter.feed({
                "type": "response.function_call_arguments.done", "sequence_number": 3,
                "item_id": "i", "call_id": "c", "name": "lookup", "arguments": '{"q":"y"}',
            })

    def test_incomplete_call_is_not_returned_as_executable(self):
        adapter = OpenAIResponsesToolStreamAdapter()
        adapter.feed({"type": "response.created", "sequence_number": 0, "response": {"id": "r"}})
        adapter.feed({
            "type": "response.output_item.added", "sequence_number": 1, "item_id": "i",
            "item": {"type": "function_call", "id": "i", "call_id": "c", "name": "lookup"},
        })
        adapter.feed({
            "type": "response.function_call_arguments.delta", "sequence_number": 2,
            "item_id": "i", "delta": '{"q":',
        })
        with self.assertRaises(IncompleteToolCallError):
            adapter.finish()
        with self.assertRaisesRegex(ProviderStreamError, "已结束"):
            adapter.feed({
                "type": "response.function_call_arguments.delta", "sequence_number": 3,
                "item_id": "i", "delta": '"q"}',
            })

    def test_events_from_a_second_response_are_rejected(self):
        adapter = OpenAIResponsesToolStreamAdapter()
        adapter.feed({"type": "response.created", "sequence_number": 0, "response": {"id": "r1"}})
        with self.assertRaisesRegex(ProviderStreamError, "different|不同"):
            adapter.feed({
                "type": "response.output_item.added", "sequence_number": 1, "response_id": "r2",
                "item_id": "i", "item": {"type": "function_call", "id": "i", "call_id": "c", "name": "lookup"},
            })

    def test_final_argument_event_does_not_release_call_from_incomplete_response(self):
        adapter = OpenAIResponsesToolStreamAdapter()
        adapter.feed({"type": "response.created", "sequence_number": 0, "response": {"id": "r"}})
        adapter.feed({
            "type": "response.output_item.added", "sequence_number": 1, "item_id": "i",
            "item": {"type": "function_call", "id": "i", "call_id": "c", "name": "lookup"},
        })
        self.assertIsNone(adapter.feed({
            "type": "response.function_call_arguments.done", "sequence_number": 2,
            "item_id": "i", "call_id": "c", "name": "lookup", "arguments": '{"q":"x"}',
        }))
        with self.assertRaisesRegex(ProviderStreamError, "失败"):
            adapter.feed({
                "type": "response.incomplete", "sequence_number": 3,
                "response": {"id": "r", "status": "incomplete"},
            })


class AnthropicMessagesToolStreamAdapterTests(unittest.TestCase):
    def test_maps_tool_use_deltas_until_content_block_stop(self):
        adapter = AnthropicMessagesToolStreamAdapter()
        adapter.feed({"type": "message_start", "message": {"id": "msg-1"}})
        self.assertIsNone(adapter.feed({
            "type": "content_block_start", "index": 2,
            "content_block": {"type": "tool_use", "id": "toolu-1", "name": "write_file", "input": {}},
        }))
        self.assertIsNone(adapter.feed({
            "type": "content_block_delta", "index": 2,
            "delta": {"type": "input_json_delta", "partial_json": '{"path":"README.md",'},
        }))
        self.assertIsNone(adapter.feed({
            "type": "content_block_delta", "index": 2,
            "delta": {"type": "input_json_delta", "partial_json": '"content":"hello"}'},
        }))
        self.assertIsNone(adapter.feed({"type": "content_block_stop", "index": 2}))
        self.assertIsNone(adapter.feed({"type": "message_delta", "delta": {"stop_reason": "tool_use"}}))
        self.assertEqual(adapter.feed({"type": "message_stop"}), [{
            "call_id": "toolu-1", "name": "write_file",
            "arguments": {"path": "README.md", "content": "hello"},
        }])
        self.assertIsNone(adapter.finish())

    def test_empty_object_tool_input_completes_as_an_empty_object(self):
        adapter = AnthropicMessagesToolStreamAdapter()
        adapter.feed({"type": "message_start", "message": {"id": "msg-empty"}})
        adapter.feed({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "toolu-empty", "name": "no_args", "input": {}},
        })
        self.assertIsNone(adapter.feed({"type": "content_block_stop", "index": 0}))
        adapter.feed({"type": "message_delta", "delta": {"stop_reason": "tool_use"}})
        self.assertEqual(adapter.feed({"type": "message_stop"}), [{
            "call_id": "toolu-empty", "name": "no_args", "arguments": {},
        }])

    def test_message_end_with_open_tool_block_reports_interruption(self):
        adapter = AnthropicMessagesToolStreamAdapter()
        adapter.feed({"type": "message_start", "message": {"id": "msg-open"}})
        adapter.feed({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "toolu-open", "name": "lookup", "input": {}},
        })
        adapter.feed({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"q":'},
        })
        with self.assertRaises(IncompleteToolCallError):
            adapter.feed({"type": "message_stop"})
        with self.assertRaisesRegex(ProviderStreamError, "已结束"):
            adapter.feed({
                "type": "content_block_delta", "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '"x"}'},
            })

    def test_unknown_events_are_ignored_and_provider_error_is_reported(self):
        adapter = AnthropicMessagesToolStreamAdapter()
        self.assertIsNone(adapter.feed({"type": "ping"}))
        with self.assertRaisesRegex(ProviderStreamError, "overloaded_error"):
            adapter.feed({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})

    def test_server_tool_use_events_are_not_routed_as_client_tools(self):
        adapter = AnthropicMessagesToolStreamAdapter()
        adapter.feed({"type": "message_start", "message": {"id": "msg-server-tool"}})
        adapter.feed({
            "type": "content_block_start", "index": 1,
            "content_block": {"type": "server_tool_use", "id": "srvtoolu-1", "name": "web_search", "input": {}},
        })
        self.assertIsNone(adapter.feed({
            "type": "content_block_delta", "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"query":"x"}'},
        }))
        self.assertIsNone(adapter.feed({"type": "content_block_stop", "index": 1}))
        self.assertEqual(adapter.feed({"type": "message_stop"}), [])

    def test_completed_tool_block_is_not_released_if_message_errors_before_stop(self):
        adapter = AnthropicMessagesToolStreamAdapter()
        adapter.feed({"type": "message_start", "message": {"id": "msg-error"}})
        adapter.feed({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "toolu-error", "name": "lookup", "input": {}},
        })
        adapter.feed({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"q":"x"}'},
        })
        self.assertIsNone(adapter.feed({"type": "content_block_stop", "index": 0}))
        with self.assertRaisesRegex(ProviderStreamError, "stream 失败"):
            adapter.feed({"type": "error", "error": {"type": "overloaded_error"}})


if __name__ == "__main__":
    unittest.main()
