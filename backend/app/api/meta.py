"""Config summary for the admin dashboard."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["meta"])


@router.get("/meta")
async def meta():
    return {
        "app": settings.APP_NAME, "version": settings.APP_VERSION,
        "provider": settings.LLM_PROVIDER, "llm_enabled": settings.LLM_ENABLED,
        "chat_model": settings.BEDROCK_CHAT_MODEL if settings.LLM_PROVIDER == "bedrock" else settings.OPENAI_CHAT_MODEL,
        "embedding": {
            "provider": "bedrock" if settings.EMBEDDING_BEDROCK_ENABLED else ("api" if settings.EMBEDDING_API_ENABLED else "none"),
            "model": settings.BEDROCK_EMBEDDING_MODEL if settings.EMBEDDING_BEDROCK_ENABLED else settings.EMBEDDING_API_MODEL,
            "dim": settings.BEDROCK_EMBEDDING_DIMENSION if settings.EMBEDDING_BEDROCK_ENABLED else settings.EMBEDDING_DIMENSION,
        },
        "reranker": "bedrock" if settings.RERANKER_BEDROCK_ENABLED else ("api" if settings.RERANKER_API_ENABLED else "none"),
        "auth_mode": settings.BEDROCK_ANTHROPIC_AUTH_MODE,
        "region": settings.BEDROCK_REGION,
        "checkpointer": settings.CHECKPOINTER,
        "vector_store": settings.VECTOR_DB_URI,
        "transports": ["jsonrpc_http", "streamable_http", "sse"],
        "routing_modes": ["supervisor", "react", "direct"],
    }
