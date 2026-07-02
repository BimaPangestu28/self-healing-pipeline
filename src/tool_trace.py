"""Structured tool-usage trace: input + output for every tool call.

Unlike a plain log, each entry captures a tool invocation as (tool, input, output,
ok), so the UI can show exactly what went in and what came back — kubectl commands
and their results, LLM tool calls and their returned data, etc.
"""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import asdict, dataclass
from threading import Lock

_MAX_FIELD = 600


@dataclass(frozen=True)
class ToolEvent:
    id: int
    tool: str
    input: str
    output: str
    ok: bool


class ToolTrace:
    """Thread-safe ring buffer of tool events."""

    def __init__(self, capacity: int = 600) -> None:
        self._buffer: deque[ToolEvent] = deque(maxlen=capacity)
        self._lock = Lock()
        self._counter = itertools.count(1)

    def record(self, tool: str, input: str, output: str, ok: bool = True) -> None:
        with self._lock:
            self._buffer.append(
                ToolEvent(
                    id=next(self._counter),
                    tool=tool,
                    input=_clip(input),
                    output=_clip(output),
                    ok=bool(ok),
                )
            )

    def after(self, cursor: int) -> list[dict]:
        with self._lock:
            return [asdict(e) for e in self._buffer if e.id > cursor]


def _clip(value: str) -> str:
    text = str(value).strip()
    return text if len(text) <= _MAX_FIELD else text[:_MAX_FIELD] + " …"


_TRACE = ToolTrace()


def record(tool: str, input: str, output: str, ok: bool = True) -> None:
    """Record a tool usage (input + output)."""
    _TRACE.record(tool, input, output, ok)


def events_after(cursor: int) -> list[dict]:
    """Return tool events with id greater than ``cursor``."""
    return _TRACE.after(cursor)
