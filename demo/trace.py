"""In-memory activity log so the demo can surface what happens under the hood.

Captures INFO logs from the app's loggers into a ring buffer that the UI polls,
letting a technical audience watch the real operations (kubectl commands, cgroup
reads, rollout restarts, LLM tool calls) behind each button click.
"""

from __future__ import annotations

import itertools
import logging
from collections import deque
from threading import Lock


class RingBufferHandler(logging.Handler):
    """A logging handler that keeps the most recent records in memory."""

    def __init__(self, capacity: int = 800) -> None:
        super().__init__()
        self._buffer: deque[dict] = deque(maxlen=capacity)
        self._lock = Lock()
        self._counter = itertools.count(1)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return
        entry = {
            "id": next(self._counter),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        with self._lock:
            self._buffer.append(entry)

    def entries_after(self, after: int) -> list[dict]:
        """Return buffered entries with id greater than ``after``."""
        with self._lock:
            return [entry for entry in self._buffer if entry["id"] > after]


def install(capacity: int = 800, loggers: tuple[str, ...] = ("src", "demo")) -> RingBufferHandler:
    """Attach a ring-buffer handler to the given logger namespaces at INFO."""
    handler = RingBufferHandler(capacity)
    handler.setLevel(logging.INFO)
    for name in loggers:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
    return handler
