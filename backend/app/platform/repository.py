"""CRUD for agents + conversation memory, and the default seed.

The seed creates two agents to make the point that the platform is generic:
  - "data-master"  : the flagship 数据问数 agent, federating data-master's /api/mcp
                     (+ disabled OpenMetadata / Superset placeholders).
  - "general"      : a plain assistant with no MCP and RAG off.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import session_scope
from app.mcp.client import McpSource
from app.platform import models
from app.platform.schemas import AgentIn, AgentPatch

logger = logging.getLogger(__name__)


DATA_MASTER_PROMPT = (
    "你是「数据问数」助手，帮助用户用自然语言查询企业指标与数据关系。\n"
    "工作方式分三步：\n"
    "1) 理解：先用检索/元数据类工具（如 list_metrics、搜索类工具）找到候选指标与口径，"
    "结合检索到的上下文确认用户真正要问的指标、维度与时间范围；不确定时向用户澄清。\n"
    "2) 执行：调用受治工具 query_metric 按口径取值（可带 dimensions/filters/grain/dateFrom/dateTo/"
    "compareWith/freshness）。不要自己写 SQL，不要直连数据库——口径与取值以 data-master 为准。\n"
    "3) 沉淀：回答里给出口径原文、数据截止时间与来源；如可出图则调用图表类工具并回链。\n"
    "只根据工具返回的数据作答，不要编造指标或数值。"
)

GENERAL_PROMPT = "你是一个通用 AI 助手，简洁准确地回答用户问题。"


def _default_agents() -> List[AgentIn]:
    return [
        AgentIn(
            id="data-master",
            name="数据问数 (data-master)",
            description="联邦 data-master / OpenMetadata / Superset MCP 的自然语言问数 Agent。",
            system_prompt=DATA_MASTER_PROMPT,
            routing_mode="supervisor",
            rag_enabled=True,
            mcp_sources=[
                {
                    "id": "data-master",
                    "label": "data-master 平台",
                    "url": "http://localhost:18888/api/mcp",
                    "transport": "jsonrpc_http",
                    "auth_mode": "passthrough",
                    "enabled": True,
                },
                {
                    "id": "openmetadata",
                    "label": "OpenMetadata",
                    "url": "http://localhost:8585/mcp",
                    "transport": "streamable_http",
                    "auth_mode": "static",
                    "static_secret": "",
                    "enabled": False,
                },
                {
                    "id": "superset",
                    "label": "Superset",
                    "url": "http://localhost:8088/mcp",
                    "transport": "streamable_http",
                    "auth_mode": "passthrough",
                    "enabled": False,
                },
            ],
        ),
        AgentIn(
            id="general",
            name="通用助手",
            description="不接 MCP、不做 RAG 的通用对话 Agent（示例：平台不绑定 data-master）。",
            system_prompt=GENERAL_PROMPT,
            routing_mode="direct",
            rag_enabled=False,
            mcp_sources=[],
        ),
    ]


# ── agent CRUD ─────────────────────────────────────────────────────────────────

def _to_out_dict(a: models.Agent) -> Dict[str, Any]:
    return {
        "id": a.id, "name": a.name, "description": a.description, "enabled": a.enabled,
        "system_prompt": a.system_prompt, "provider": a.provider, "model": a.model,
        "max_tokens": a.max_tokens, "routing_mode": a.routing_mode,
        "max_tool_turns": a.max_tool_turns, "rag_enabled": a.rag_enabled,
        "rag_top_k": a.rag_top_k, "mcp_sources": a.mcp_sources or [],
        "created_at": a.created_at, "updated_at": a.updated_at,
    }


def list_agents() -> List[Dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(select(models.Agent).order_by(models.Agent.id)).scalars().all()
        return [_to_out_dict(a) for a in rows]


def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as s:
        a = s.get(models.Agent, agent_id)
        return _to_out_dict(a) if a else None


def create_agent(data: AgentIn) -> Dict[str, Any]:
    with session_scope() as s:
        if s.get(models.Agent, data.id):
            raise ValueError(f"agent '{data.id}' already exists")
        a = models.Agent(
            id=data.id, name=data.name, description=data.description, enabled=data.enabled,
            system_prompt=data.system_prompt, provider=data.provider, model=data.model,
            max_tokens=data.max_tokens, routing_mode=data.routing_mode,
            max_tool_turns=data.max_tool_turns, rag_enabled=data.rag_enabled,
            rag_top_k=data.rag_top_k, mcp_sources=[m.model_dump() for m in data.mcp_sources],
        )
        s.add(a)
        s.flush()
        return _to_out_dict(a)


def update_agent(agent_id: str, patch: AgentPatch) -> Optional[Dict[str, Any]]:
    with session_scope() as s:
        a = s.get(models.Agent, agent_id)
        if not a:
            return None
        data = patch.model_dump(exclude_unset=True)
        if "mcp_sources" in data and data["mcp_sources"] is not None:
            data["mcp_sources"] = [m if isinstance(m, dict) else m.model_dump() for m in patch.mcp_sources]
        for k, v in data.items():
            setattr(a, k, v)
        s.flush()
        return _to_out_dict(a)


def delete_agent(agent_id: str) -> bool:
    with session_scope() as s:
        a = s.get(models.Agent, agent_id)
        if not a:
            return False
        s.delete(a)
        return True


def to_mcp_sources(agent: Dict[str, Any]) -> List[McpSource]:
    out: List[McpSource] = []
    for src in agent.get("mcp_sources") or []:
        if not src.get("enabled", True):
            continue
        out.append(McpSource(
            id=src["id"], url=src["url"], transport=src.get("transport", "jsonrpc_http"),
            label=src.get("label", ""), auth_mode=src.get("auth_mode", "passthrough"),
            static_secret=src.get("static_secret", ""), header_name=src.get("header_name", "Authorization"),
            header_prefix=src.get("header_prefix", "Bearer "), allowed_tools=src.get("allowed_tools", []),
            timeout=float(src.get("timeout", 20.0)), verify_tls=bool(src.get("verify_tls", True)),
        ))
    return out


def seed_defaults() -> None:
    with session_scope() as s:
        existing = set(s.execute(select(models.Agent.id)).scalars().all())
    for a in _default_agents():
        if a.id not in existing:
            create_agent(a)
            logger.info("seeded agent '%s'", a.id)


# ── conversation memory ─────────────────────────────────────────────────────────

def load_history(session_id: str, limit: int = 20) -> List[Dict[str, str]]:
    with session_scope() as s:
        conv = s.get(models.Conversation, session_id)
        if not conv:
            return []
        msgs = conv.messages[-limit:]
        return [{"role": m.role, "content": m.content} for m in msgs]


def append_turn(session_id: str, agent_id: str, user_sub: str, user_msg: str, assistant_msg: str) -> None:
    with session_scope() as s:
        conv = s.get(models.Conversation, session_id)
        if not conv:
            conv = models.Conversation(
                session_id=session_id, agent_id=agent_id, user_sub=user_sub,
                title=(user_msg or "")[:80],
            )
            s.add(conv)
            s.flush()
        s.add(models.Message(session_id=session_id, role="user", content=user_msg))
        s.add(models.Message(session_id=session_id, role="assistant", content=assistant_msg))


def list_conversations(user_sub: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    with session_scope() as s:
        stmt = select(models.Conversation).order_by(models.Conversation.updated_at.desc()).limit(limit)
        if user_sub:
            stmt = stmt.where(models.Conversation.user_sub == user_sub)
        rows = s.execute(stmt).scalars().all()
        return [{"session_id": c.session_id, "agent_id": c.agent_id, "title": c.title,
                 "user_sub": c.user_sub, "updated_at": c.updated_at,
                 "message_count": len(c.messages)} for c in rows]
