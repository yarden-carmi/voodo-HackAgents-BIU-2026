"""Shared wire types and config. All tracks depend on this; touch with care."""
from shared.protocol import (
    AgentEvent,
    EventKind,
    ProblemQuery,
    SolutionMatch,
    SolutionRecord,
    SolutionStep,
    ToolCall,
    ToolName,
    UserMessage,
)
from shared.config import Settings, settings

__all__ = [
    "AgentEvent",
    "EventKind",
    "ProblemQuery",
    "Settings",
    "SolutionMatch",
    "SolutionRecord",
    "SolutionStep",
    "ToolCall",
    "ToolName",
    "UserMessage",
    "settings",
]
