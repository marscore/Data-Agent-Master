"""LangGraph checkpointer factory (thread-scoped graph-state memory).

thread_id = session_id, so a compiled graph resumes a conversation's state
across turns within the process. Durable, human-readable memory lives in the DB
(conversations/messages) and is reloaded as `history` each turn — that is the
memory the UI shows and what survives restarts.

The graph runs async (astream), so the checkpointer must implement async
methods. MemorySaver does and needs zero infra, so it is the default and the
safe fallback. (The sync SqliteSaver raises on async graphs; wiring the async
AsyncSqliteSaver/AsyncPostgresSaver into a lazily-compiled singleton is loop-
fragile, so graph-state persistence beyond process lifetime is deferred — the
DB already provides durable conversation memory.)
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_checkpointer = None


def get_checkpointer():
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    from langgraph.checkpoint.memory import MemorySaver

    kind = (settings.CHECKPOINTER or "memory").lower()
    if kind not in ("memory", ""):
        logger.info("CHECKPOINTER=%s: graph-state persistence deferred; using MemorySaver "
                    "(durable conversation memory is in the DB).", kind)
    _checkpointer = MemorySaver()
    logger.info("Checkpointer: MemorySaver (thread_id=session_id)")
    return _checkpointer
