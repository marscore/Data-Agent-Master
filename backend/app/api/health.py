"""Health + provider connectivity checks."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.llm import dispatch

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION,
            "provider": settings.LLM_PROVIDER, "llm_enabled": settings.LLM_ENABLED}


@router.get("/health/providers")
async def providers(deep: bool = False):
    """deep=true issues one real embedding + one tiny chat call to verify creds."""
    out = {
        "provider": settings.LLM_PROVIDER,
        "chat_model": (settings.BEDROCK_CHAT_MODEL if settings.LLM_PROVIDER == "bedrock" else settings.OPENAI_CHAT_MODEL),
        "embedding_bedrock": settings.EMBEDDING_BEDROCK_ENABLED,
        "embedding_model": settings.BEDROCK_EMBEDDING_MODEL if settings.EMBEDDING_BEDROCK_ENABLED else settings.EMBEDDING_API_MODEL,
        "reranker_bedrock": settings.RERANKER_BEDROCK_ENABLED,
        "auth_mode": settings.BEDROCK_ANTHROPIC_AUTH_MODE,
    }
    if deep:
        from app.embeddings.embeddings import embedding_service
        try:
            v = embedding_service.embed_queries(["ping"])
            out["embedding_check"] = {"ok": True, "dim": int(v.shape[1])}
        except Exception as e:  # noqa: BLE001
            out["embedding_check"] = {"ok": False, "error": str(e)}
        try:
            txt = await dispatch.one_shot_text("你是助手。", "回复两个字：在的", timeout=30)
            out["chat_check"] = {"ok": True, "sample": txt[:40]}
        except Exception as e:  # noqa: BLE001
            out["chat_check"] = {"ok": False, "error": str(e)}
    return out
