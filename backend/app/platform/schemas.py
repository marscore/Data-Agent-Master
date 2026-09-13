"""Pydantic schemas for the platform admin/config API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class McpSourceIn(BaseModel):
    id: str
    url: str
    transport: str = "jsonrpc_http"      # jsonrpc_http | streamable_http | sse
    label: str = ""
    auth_mode: str = "passthrough"        # passthrough | static | none
    static_secret: str = ""
    header_name: str = "Authorization"
    header_prefix: str = "Bearer "
    allowed_tools: List[str] = Field(default_factory=list)
    timeout: float = 20.0
    verify_tls: bool = True
    enabled: bool = True


class AgentIn(BaseModel):
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    system_prompt: str = ""
    provider: str = ""
    model: str = ""
    max_tokens: int = 0
    routing_mode: str = "supervisor"
    max_tool_turns: int = 0
    rag_enabled: bool = True
    rag_top_k: int = 0
    mcp_sources: List[McpSourceIn] = Field(default_factory=list)


class AgentPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    system_prompt: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    routing_mode: Optional[str] = None
    max_tool_turns: Optional[int] = None
    rag_enabled: Optional[bool] = None
    rag_top_k: Optional[int] = None
    mcp_sources: Optional[List[McpSourceIn]] = None


class AgentOut(AgentIn):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatRequest(BaseModel):
    agent_id: str = "data-master"
    message: str
    session_id: Optional[str] = None
    stream: bool = True


class SpanOut(BaseModel):
    seq: int
    kind: str
    name: str
    status: str
    duration_ms: int
    detail: Any = None


class TraceRunOut(BaseModel):
    run_id: str
    agent_id: str
    session_id: str
    user_sub: str
    question: str
    final_text: str
    route: str
    status: str
    error: Optional[str] = None
    tokens_in: int
    tokens_out: int
    duration_ms: int
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    spans: List[SpanOut] = Field(default_factory=list)
