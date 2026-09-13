"""Supervisor: choose a route for this turn (agent | rag | direct | clarify).

Respects the agent's routing_mode: "direct" and "react" are deterministic;
"supervisor" asks a small LLM, constrained to routes that are actually
available (no tools -> no "agent"; no retrieved docs -> "rag" collapses to
"direct"). Always fails safe to a sensible default.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.types import RunnableConfig
from app.agents.context import ctx_of
from app.agents.prompts import ROUTER_SYSTEM
from app.agents.state import RootState
from app.llm import dispatch

logger = logging.getLogger(__name__)


async def supervisor_node(state: RootState, config: RunnableConfig) -> Dict[str, Any]:
    ctx = ctx_of(config)
    mode = (ctx.agent.get("routing_mode") or "supervisor").lower()
    has_tools = bool(state.get("tool_names"))
    has_docs = bool(state.get("retrieved_docs"))

    def _record(route: str, reason: str) -> Dict[str, Any]:
        if ctx.tracer:
            ctx.tracer.route = route
            ctx.tracer.record("route", f"route:{route}", detail={"reason": reason, "mode": mode})
        return {"route": route}

    if mode == "direct":
        return _record("direct", "routing_mode=direct")
    if mode == "react":
        if has_tools:
            return _record("agent", "routing_mode=react")
        return _record("rag" if has_docs else "direct", "react but no tools")

    # supervisor mode
    if not dispatch.settings.LLM_ENABLED:
        if has_tools:
            return _record("agent", "llm disabled -> default agent")
        return _record("rag" if has_docs else "direct", "llm disabled")

    caps = []
    if has_tools:
        caps.append(f"可用工具: {', '.join(state['tool_names'][:20])}")
    if has_docs:
        caps.append(f"检索到 {len(state['retrieved_docs'])} 条相关资料")
    caps_text = "；".join(caps) or "无工具、无检索资料"
    user = f"用户问题：{state.get('user_message','')}\n当前能力：{caps_text}"
    try:
        data = await dispatch.one_shot_json(ROUTER_SYSTEM, user, timeout=12.0)
    except Exception as e:  # noqa: BLE001
        logger.warning("router LLM failed: %s", e)
        data = {}
    route = (data.get("route") or "").strip().lower()
    reason = data.get("reason", "")
    if route not in ("agent", "rag", "direct", "clarify"):
        route = "agent" if has_tools else ("rag" if has_docs else "direct")
        reason = reason or "fallback"
    if route == "agent" and not has_tools:
        route = "rag" if has_docs else "direct"
    if route == "rag" and not has_docs:
        route = "direct"
    return _record(route, reason)
