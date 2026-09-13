"""Conversation memory: list threads, read one, delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import session_scope
from app.platform import models, repository
from app.shared.auth import Principal, get_principal

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations(mine: bool = False, principal: Principal = Depends(get_principal)):
    return repository.list_conversations(user_sub=principal.sub if mine else None)


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str):
    with session_scope() as s:
        conv = s.get(models.Conversation, session_id)
        if not conv:
            raise HTTPException(404, "conversation not found")
        return {"session_id": conv.session_id, "agent_id": conv.agent_id, "title": conv.title,
                "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at}
                             for m in conv.messages]}


@router.delete("/conversations/{session_id}")
async def delete_conversation(session_id: str):
    with session_scope() as s:
        conv = s.get(models.Conversation, session_id)
        if conv:
            s.delete(conv)
    return {"deleted": session_id}
