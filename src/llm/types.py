"""Shared LLM types for tool-calling (provider-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCall:
    """A function/tool call requested by the model."""

    id: str
    name: str
    arguments: str  # raw JSON string of arguments


@dataclass(frozen=True)
class LlmMessage:
    """A model reply: free-text content and/or tool calls."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


def parse_message(message: dict) -> LlmMessage:
    """Parse an OpenAI-compatible chat message into an LlmMessage."""
    raw_calls = message.get("tool_calls") or []
    tool_calls = [
        ToolCall(
            id=call.get("id", ""),
            name=call.get("function", {}).get("name", ""),
            arguments=call.get("function", {}).get("arguments", "") or "",
        )
        for call in raw_calls
        if call.get("type", "function") == "function"
    ]
    return LlmMessage(content=message.get("content"), tool_calls=tool_calls)
