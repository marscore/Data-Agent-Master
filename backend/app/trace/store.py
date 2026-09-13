"""Read-side helpers for the trace API / admin console."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.core.database import session_scope
from app.platform import models


def _run_dict(run: models.TraceRun, with_spans: bool = False) -> Dict[str, Any]:
    d = {
        "run_id": run.run_id, "agent_id": run.agent_id, "session_id": run.session_id,
        "user_sub": run.user_sub, "question": run.question, "final_text": run.final_text,
        "route": run.route, "status": run.status, "error": run.error,
        "tokens_in": run.tokens_in, "tokens_out": run.tokens_out,
        "duration_ms": run.duration_ms, "started_at": run.started_at, "ended_at": run.ended_at,
    }
    if with_spans:
        d["spans"] = [
            {"seq": sp.seq, "kind": sp.kind, "name": sp.name, "status": sp.status,
             "duration_ms": sp.duration_ms, "detail": sp.detail}
            for sp in run.spans
        ]
    return d


def list_runs(agent_id: Optional[str] = None, session_id: Optional[str] = None,
              limit: int = 50) -> List[Dict[str, Any]]:
    with session_scope() as s:
        stmt = select(models.TraceRun).order_by(models.TraceRun.started_at.desc()).limit(limit)
        if agent_id:
            stmt = stmt.where(models.TraceRun.agent_id == agent_id)
        if session_id:
            stmt = stmt.where(models.TraceRun.session_id == session_id)
        return [_run_dict(r) for r in s.execute(stmt).scalars().all()]


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as s:
        run = s.get(models.TraceRun, run_id)
        return _run_dict(run, with_spans=True) if run else None
