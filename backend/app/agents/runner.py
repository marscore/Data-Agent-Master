"""Public entrypoint: drive the compiled graph for one turn and yield SSE bytes.

Builds the request-scoped MCP federation + tracer, streams the graph's custom
events to the client, then persists the turn to conversation memory and closes
the trace. Any mid-stream failure degrades to an `error` event, never a raw 500.
"""

from __future__ import annotations

import logging
import uuid
from typing import AsyncGenerator, Optional

from app.agents.context import RequestContext
from app.agents.graph import get_graph
from app.core.config import settings
from app.mcp.federation import Federation
from app.platform import repository
from app.shared.sse import DONE, format_sse
from app.trace.tracer import RunTracer

logger = logging.getLogger(__name__)


def new_session_id() -> str:
    return "sess_" + uuid.uuid4().hex[:16]


async def run_agent_stream(
    *, agent_id: str, message: str, session_id: Optional[str],
    user_sub: str, access_token: Optional[str],
) -> AsyncGenerator[str, None]:
    session_id = session_id or new_session_id()

    agent = repository.get_agent(agent_id)
    if agent is None:
        yield format_sse({"type": "error", "message": f"未知 agent: {agent_id}"})
        yield DONE
        return
    if not agent.get("enabled", True):
        yield format_sse({"type": "error", "message": f"agent 已停用: {agent_id}"})
        yield DONE
        return

    sources = repository.to_mcp_sources(agent)
    federation = Federation(sources, access_token)
    tracer = RunTracer(agent_id, session_id, user_sub, message)
    tracer.start()
    history = repository.load_history(session_id)

    ctx = RequestContext(
        user_sub=user_sub, access_token=access_token, agent=agent, federation=federation,
        tracer=tracer, session_id=session_id, rag_enabled=agent.get("rag_enabled", True),
        top_k=agent.get("rag_top_k") or settings.RAG_TOP_K,
    )
    config = {"configurable": {"ctx": ctx, "thread_id": session_id}}
    inputs = {"user_message": message, "history": history}

    yield format_sse({"type": "session", "session_id": session_id, "run_id": tracer.run_id})

    final_text, route = "", ""
    try:
        graph = get_graph()
        async for event in graph.astream(inputs, config=config, stream_mode="custom"):
            if event.get("type") == "final":
                final_text = event.get("text", "")
                route = event.get("route", "")
                continue
            yield format_sse(event)
    except Exception as e:  # noqa: BLE001
        logger.error("session=%s agent run failed: %s", session_id, e, exc_info=True)
        yield format_sse({"type": "error", "message": str(e)})
        tracer.finish(final_text, status="error", error=str(e))
        yield DONE
        return

    try:
        repository.append_turn(session_id, agent_id, user_sub, message, final_text)
    except Exception as e:  # noqa: BLE001
        logger.warning("append_turn failed: %s", e)
    tracer.finish(final_text, status="ok")
    logger.info("session=%s run=%s route=%s done (%d chars)", session_id, tracer.run_id, route, len(final_text))
    yield DONE
