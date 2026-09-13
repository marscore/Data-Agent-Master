"""Data Agent Master — 通用 AI Agent 平台 (backend).

FastAPI service: MCP-federated, RAG-augmented, LangGraph-orchestrated agents on
Bedrock or OpenAI-compatible models, with thread memory and run tracing. The
admin frontend is a separate deployable (frontend/); CORS is open so it can call
this API from its own origin. If a built frontend exists (frontend/dist) it is
also served here for convenience.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, chat, conversations, health, meta, traces
from app.core.config import settings
from app.core.lifespan import lifespan

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION,
              docs_url="/docs" if settings.DEBUG else None,
              redoc_url="/redoc" if settings.DEBUG else None,
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.CORS_ORIGINS.strip() == "*" else [o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

_API = "/api/v1"
app.include_router(health.router, prefix=_API)
app.include_router(meta.router, prefix=_API)
app.include_router(agents.router, prefix=_API)
app.include_router(chat.router, prefix=_API)
app.include_router(conversations.router, prefix=_API)
app.include_router(traces.router, prefix=_API)


@app.get("/api")
async def api_root():
    return {"app": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}


# Serve a built frontend if present (prod convenience; dev uses Vite on its own port).
_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
