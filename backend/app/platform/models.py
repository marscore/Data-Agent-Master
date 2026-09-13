"""ORM models for the AI platform: agents (configurable behavior), trace runs
and spans (observability), and conversations/messages (memory + audit)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Agent(Base):
    """A configurable agent. data-master问数 is one instance; the platform is
    not tied to it. `mcp_sources` is the per-agent MCP registry."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    system_prompt: Mapped[str] = mapped_column(Text, default="")
    # model behavior (empty = inherit process defaults from settings)
    provider: Mapped[str] = mapped_column(String(32), default="")     # "" | bedrock | openai
    model: Mapped[str] = mapped_column(String(200), default="")
    max_tokens: Mapped[int] = mapped_column(Integer, default=0)       # 0 = inherit

    # orchestration
    routing_mode: Mapped[str] = mapped_column(String(32), default="supervisor")  # supervisor|react|direct
    max_tool_turns: Mapped[int] = mapped_column(Integer, default=0)   # 0 = inherit

    # RAG
    rag_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rag_top_k: Mapped[int] = mapped_column(Integer, default=0)        # 0 = inherit

    # MCP registry: list of source dicts (see app/mcp/client.McpSource)
    mcp_sources: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class TraceRun(Base):
    __tablename__ = "trace_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_sub: Mapped[str] = mapped_column(String(200), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    final_text: Mapped[str] = mapped_column(Text, default="")
    route: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|ok|error
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    spans: Mapped[list["TraceSpan"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="TraceSpan.seq"
    )


class TraceSpan(Base):
    __tablename__ = "trace_spans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("trace_runs.run_id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(16), default="node")   # node|llm|tool|retrieval|route
    name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(16), default="ok")   # ok|error
    detail: Mapped[Any] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped[TraceRun] = relationship(back_populates="spans")


class Conversation(Base):
    __tablename__ = "conversations"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    user_sub: Mapped[str] = mapped_column(String(200), default="", index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.session_id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))   # user|assistant
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
