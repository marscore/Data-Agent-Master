"""Per-run tracer. Records the agent run (question -> route -> tool calls ->
answer) as a TraceRun plus ordered TraceSpans. Persistence never breaks a chat:
every DB write is best-effort. Spans are also buffered in-memory so the chat
stream can emit them live.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.database import session_scope
from app.platform import models

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:16]


class RunTracer:
    def __init__(self, agent_id: str, session_id: str, user_sub: str, question: str,
                 run_id: Optional[str] = None):
        self.run_id = run_id or new_run_id()
        self.agent_id = agent_id
        self.session_id = session_id
        self.user_sub = user_sub
        self.question = question
        self.route = ""
        self.tokens_in = 0
        self.tokens_out = 0
        self._seq = 0
        self._start = time.monotonic()
        self.spans: List[Dict[str, Any]] = []

    def start(self) -> None:
        try:
            with session_scope() as s:
                s.add(models.TraceRun(
                    run_id=self.run_id, agent_id=self.agent_id, session_id=self.session_id,
                    user_sub=self.user_sub, question=self.question, status="running",
                    started_at=datetime.now(timezone.utc),
                ))
        except Exception as e:  # noqa: BLE001
            logger.warning("trace start failed: %s", e)

    def add_tokens(self, tin: int, tout: int) -> None:
        self.tokens_in += int(tin or 0)
        self.tokens_out += int(tout or 0)

    def record(self, kind: str, name: str, status: str = "ok",
               detail: Optional[Dict[str, Any]] = None, duration_ms: int = 0) -> Dict[str, Any]:
        self._seq += 1
        span = {"seq": self._seq, "kind": kind, "name": name, "status": status,
                "duration_ms": duration_ms, "detail": detail or {}}
        self.spans.append(span)
        try:
            with session_scope() as s:
                s.add(models.TraceSpan(
                    run_id=self.run_id, seq=span["seq"], kind=kind, name=name,
                    status=status, detail=detail or {}, duration_ms=duration_ms,
                ))
        except Exception as e:  # noqa: BLE001
            logger.warning("trace span failed: %s", e)
        return span

    @contextmanager
    def span(self, kind: str, name: str, detail: Optional[Dict[str, Any]] = None):
        start = time.monotonic()
        status = "ok"
        info: Dict[str, Any] = dict(detail or {})
        try:
            yield info
        except Exception as e:  # noqa: BLE001
            status = "error"
            info["error"] = str(e)
            raise
        finally:
            self.record(kind, name, status=status, detail=info,
                        duration_ms=int((time.monotonic() - start) * 1000))

    def finish(self, final_text: str, status: str = "ok", error: Optional[str] = None) -> None:
        duration_ms = int((time.monotonic() - self._start) * 1000)
        try:
            with session_scope() as s:
                run = s.get(models.TraceRun, self.run_id)
                if run:
                    run.final_text = final_text or ""
                    run.route = self.route
                    run.status = status
                    run.error = error
                    run.tokens_in = self.tokens_in
                    run.tokens_out = self.tokens_out
                    run.ended_at = datetime.now(timezone.utc)
                    run.duration_ms = duration_ms
        except Exception as e:  # noqa: BLE001
            logger.warning("trace finish failed: %s", e)
