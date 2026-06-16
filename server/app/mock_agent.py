"""Canned agent for UI development.

Used when `MOCK_AGENT=1` is set on the FastAPI process — lets the chat UI
be exercised end-to-end without a Windows executor or an OpenRouter key.
"""
from __future__ import annotations

import time
from typing import Callable

from shared.protocol import AgentEvent, UserMessage

EmitFn = Callable[[AgentEvent], None]


def run_mock_agent_sync(message: UserMessage, emit: EmitFn) -> None:
    """Synchronous variant — matches the real agent's signature for server/app/main.py."""
    emit(AgentEvent(kind="status", payload={"msg": "Mock agent starting"}))
    time.sleep(0.3)
    emit(AgentEvent(
        kind="thought",
        payload={"text": f"Looking at the screen to understand: {message.text!r}"},
    ))
    time.sleep(0.4)
    emit(AgentEvent(
        kind="tool_call",
        payload={"name": "hotkey", "args": {"keys": ["win", "r"]}},
    ))
    time.sleep(0.3)
    emit(AgentEvent(kind="observation", payload={"ok": True}))
    time.sleep(0.3)
    emit(AgentEvent(
        kind="thought",
        payload={"text": "Typing notepad into the Run dialog."},
    ))
    emit(AgentEvent(
        kind="tool_call",
        payload={"name": "type", "args": {"text": "notepad"}},
    ))
    time.sleep(0.3)
    emit(AgentEvent(
        kind="result",
        payload={"success": True, "summary": "Mock run finished — pretend the issue is fixed."},
    ))
