"""Canned LLM that emits a deterministic sequence of tool calls.

Use with `--mock-llm` (or `MOCK_LLM=1`) so the agent loop can iterate
without hitting OpenRouter. The default script: open Notepad via Win+R,
type a sentence, then finish.
"""
from __future__ import annotations

from typing import Any

from shared.protocol import ToolCall

DEFAULT_SCRIPT: list[tuple[str, ToolCall]] = [
    ("I'll open the Run dialog with Win+R.", ToolCall(name="hotkey", args={"keys": ["win", "r"]})),
    ("Now I'll type 'notepad' and press Enter.", ToolCall(name="type", args={"text": "notepad"})),
    ("Press Enter to launch.", ToolCall(name="key", args={"key": "enter"})),
    ("Wait for Notepad to appear.", ToolCall(name="wait", args={"seconds": 1.0})),
    ("Take a screenshot to confirm.", ToolCall(name="screenshot", args={})),
    (
        "Notepad is open — I'll type a greeting.",
        ToolCall(name="type", args={"text": "Hello from voodo!"}),
    ),
    (
        "Done.",
        ToolCall(
            name="finish",
            args={"success": True, "summary": "Opened Notepad and typed a greeting."},
        ),
    ),
]


class MockLLM:
    def __init__(self, script: list[tuple[str, ToolCall]] | None = None):
        self.script = list(script or DEFAULT_SCRIPT)
        self._step = 0

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str, list[ToolCall]]:
        if self._step >= len(self.script):
            return (
                "Out of script.",
                [ToolCall(name="finish", args={"success": False, "summary": "Mock exhausted."})],
            )
        thought, call = self.script[self._step]
        self._step += 1
        return thought, [call]
