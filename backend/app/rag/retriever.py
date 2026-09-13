"""RAG retrieval pipeline: query-rewrite -> vector search -> rerank -> threshold.

Used by the agent's "understand" step to recall candidate metrics / glossary /
docs before it decides which governed tool to call. Recall only — the authoritative
metric definition and value still come from data-master via MCP.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.core.config import settings
from app.embeddings.reranker import reranker_service
from app.rag import query_rewrite, vector_store

logger = logging.getLogger(__name__)


async def retrieve(agent_id: str, query: str, top_k: int | None = None) -> List[Dict[str, Any]]:
    top_k = top_k or settings.RAG_TOP_K
    rewrites = await query_rewrite.rewrite(query)
    candidates = vector_store.search(
        agent_id, query, limit=settings.RAG_CANDIDATE_K, extra_queries=rewrites[1:]
    )
    if not candidates:
        return []
    if settings.RAG_RERANK_ENABLED and reranker_service.available():
        ranked = reranker_service.rerank(query, candidates, top_k=top_k)
        kept = [d for d in ranked if d.get("rerank_score", 1.0) >= settings.RAG_SCORE_THRESHOLD]
        return kept or ranked[:top_k]
    return candidates[:top_k]


def format_context(docs: List[Dict[str, Any]]) -> str:
    """Render retrieved docs as a compact context block for the LLM prompt."""
    if not docs:
        return ""
    lines = ["以下是检索到的候选口径/术语/文档（仅供理解，取值仍需经受治工具）："]
    for i, d in enumerate(docs, 1):
        title = d.get("title") or d.get("metadata", {}).get("name") or f"文档{i}"
        text = (d.get("text") or "").strip()
        lines.append(f"[{i}] {title}\n{text}")
    return "\n\n".join(lines)
