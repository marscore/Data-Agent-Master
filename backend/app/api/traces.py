"""Trace / observability API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.trace import store

router = APIRouter(tags=["traces"])


@router.get("/traces")
async def list_traces(agent_id: Optional[str] = None, session_id: Optional[str] = None, limit: int = 50):
    return store.list_runs(agent_id=agent_id, session_id=session_id, limit=limit)


@router.get("/traces/{run_id}")
async def get_trace(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "trace not found")
    return run
