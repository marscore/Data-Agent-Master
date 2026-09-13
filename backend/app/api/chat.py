"""Streaming chat endpoint (SSE)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agents.runner import run_agent_stream
from app.platform.schemas import ChatRequest
from app.shared.auth import Principal, get_principal

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(req: ChatRequest, principal: Principal = Depends(get_principal)):
    gen = run_agent_stream(
        agent_id=req.agent_id, message=req.message, session_id=req.session_id,
        user_sub=principal.sub, access_token=principal.access_token,
    )
    return StreamingResponse(
        gen, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
