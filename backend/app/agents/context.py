"""Per-request runtime context. Lives in config["configurable"], never in graph
State (State may be checkpointed; these fields are non-serializable clients,
live credentials, or PII)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RequestContext:
    user_sub: str
    access_token: Optional[str] = None      # platform JWT, passed through to MCP servers
    agent: Dict[str, Any] = field(default_factory=dict)
    federation: Any = None                  # app.mcp.federation.Federation
    tracer: Any = None                      # app.trace.tracer.RunTracer
    session_id: Optional[str] = None
    rag_enabled: bool = True
    top_k: int = 6


def ctx_of(config: dict) -> RequestContext:
    return config["configurable"]["ctx"]
