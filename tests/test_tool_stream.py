import unittest

from ai_company_os import IncompleteToolCallError, ToolCallDeltaAssembler


class ToolCallDeltaAssemblerTests(unittest.TestCase):
    def test_incremental_arguments_are_concatenated_and_emitted_once(self):
        assembler = ToolCallDeltaAssembler()

        self.assertIsNone(assembler.feed({
            "event_id": "e1", "call_id": "call-1", "name_delta": "write_file",
            "arguments_delta": '{"path":"README.md",',
        }))
        completed = assembler.feed({
            "event_id": "e2", "call_id": "call-1", "arguments_delta": '"content":"hello"}',
            "complete": True,
        })

        self.assertEqual(completed, {
            "call_id": "call-1", "name": "write_file",
            "arguments": {"path": "README.md", "content": "hello"},
        })
        self.assertEqual(assembler.feed({
            "event_id": "e2", "call_id": "call-1", "arguments_delta": '"content":"hello"}',
            "complete": True,
        }), None)
        self.assertEqual(assembler.finish(), [completed])

    def test_duplicate_delta_event_is_ignored_instead_of_appended_twice(self):
        assembler = ToolCallDeltaAssembler()
        first = {
            "event_id": "e1", "call_id": "call-1", "name_delta": "lookup",
            "arguments_delta": '{"query":"x"',
        }
        assembler.feed(first)
        assembler.feed(first)

        completed = assembler.feed({
            "event_id": "e2", "call_id": "call-1", "arguments_delta": "}", "complete": True,
        })

        self.assertEqual(completed["arguments"], {"query": "x"})

    def test_event_id_collision_with_different_payload_is_rejected(self):
        assembler = ToolCallDeltaAssembler()
        assembler.feed({"event_id": "e1", "call_id": "call-1", "name_delta": "lookup"})

        with self.assertRaisesRegex(ValueError, "event_id"):
            assembler.feed({"event_id": "e1", "call_id": "call-1", "name_delta": "delete"})

    def test_interleaved_tool_calls_keep_separate_argument_buffers(self):
        assembler = ToolCallDeltaAssembler()
        assembler.feed({"event_id": "e1", "call_id": "A", "name_delta": "lookup", "arguments_delta": '{"q":'})
        assembler.feed({"event_id": "e2", "call_id": "B", "name_delta": "write", "arguments_delta": '{"p":'})

        b = assembler.feed({"event_id": "e3", "call_id": "B", "arguments_delta": '"b"}', "complete": True})
        a = assembler.feed({"event_id": "e4", "call_id": "A", "arguments_delta": '"a"}', "complete": True})

        self.assertEqual((b["name"], b["arguments"]), ("write", {"p": "b"}))
        self.assertEqual((a["name"], a["arguments"]), ("lookup", {"q": "a"}))

    def test_incomplete_call_is_not_executable(self):
        assembler = ToolCallDeltaAssembler()
        assembler.feed({"event_id": "e1", "call_id": "call-1", "name_delta": "lookup", "arguments_delta": '{"q":'})

        with self.assertRaises(IncompleteToolCallError):
            assembler.finish()
        self.assertEqual(assembler.pending_call_ids, ("call-1",))

    def test_invalid_final_json_never_emits_a_tool_call(self):
        assembler = ToolCallDeltaAssembler()
        with self.assertRaisesRegex(ValueError, "JSON"):
            assembler.feed({
                "event_id": "e1", "call_id": "call-1", "name_delta": "lookup",
                "arguments_delta": '{"q":', "complete": True,
            })
        self.assertEqual(assembler.completed_calls, ())

    def test_event_after_completed_call_is_rejected(self):
        assembler = ToolCallDeltaAssembler()
        assembler.feed({
            "event_id": "e1", "call_id": "call-1", "name_delta": "lookup",
            "arguments_delta": "{}", "complete": True,
        })

        with self.assertRaisesRegex(ValueError, "已完成"):
            assembler.feed({"event_id": "e2", "call_id": "call-1", "arguments_delta": "{}"})


if __name__ == "__main__":
    unittest.main()
