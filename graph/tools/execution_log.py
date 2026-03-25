from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, List

_MAX_TRACES = 500
_TRACE_STORE: Deque[Dict[str, Any]] = deque(maxlen=_MAX_TRACES)
_TRACE_LOCK = Lock()


def append_trace(trace: Dict[str, Any]) -> None:
    """Store tool traces for UI visibility and debugging."""
    with _TRACE_LOCK:
        _TRACE_STORE.append(trace)


def get_execution_log() -> List[Dict[str, Any]]:
    with _TRACE_LOCK:
        return list(_TRACE_STORE)


def clear_execution_log() -> None:
    with _TRACE_LOCK:
        _TRACE_STORE.clear()
