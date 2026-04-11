"""Tests for output message formatting."""

from unittest import TestCase

from nockcc_agent.output import (
    format_command_result,
    format_identify,
    format_output_message,
    format_process_list,
)


class OutputFormattingTest(TestCase):
    def test_format_output_message(self) -> None:
        msg = format_output_message("sess-1", 42, "Hello world", "stdout")
        self.assertEqual(msg["type"], "output")
        self.assertEqual(msg["session_id"], "sess-1")
        self.assertEqual(msg["line"], 42)
        self.assertEqual(msg["content"], "Hello world")
        self.assertEqual(msg["stream"], "stdout")

    def test_format_command_result(self) -> None:
        msg = format_command_result(123, "completed", "Done")
        self.assertEqual(msg["type"], "command_result")
        self.assertEqual(msg["command_id"], 123)
        self.assertEqual(msg["status"], "completed")
        self.assertEqual(msg["result"], "Done")

    def test_format_process_list(self) -> None:
        processes = [{"pid": 1, "repo": "nexus"}]
        msg = format_process_list(processes)
        self.assertEqual(msg["type"], "process_list")
        self.assertEqual(len(msg["processes"]), 1)

    def test_format_identify(self) -> None:
        msg = format_identify("TestMac", ["nexus", "abl"])
        self.assertEqual(msg["type"], "identify")
        self.assertEqual(msg["machine"], "TestMac")
        self.assertEqual(msg["repos"], ["nexus", "abl"])
