"""Single choke point for SSE-shaped events a graph node produces. Nodes call
emit(event); the runner turns them into wire bytes."""

from __future__ import annotations

from typing import Any, Dict

from langgraph.config import get_stream_writer


def emit(event: Dict[str, Any]) -> None:
    writer = get_stream_writer()
    writer(event)
