"""SSE wire formatting — single place that turns an event dict into bytes."""

from __future__ import annotations

import json
from typing import Any, Dict


def format_sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


DONE = "data: [DONE]\n\n"
