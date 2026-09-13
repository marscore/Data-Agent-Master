"""Multi-query rewrite: expand a user question into a few retrieval queries to
improve recall (synonyms, decomposition, EN/中文). Fails safe to [query]."""

from __future__ import annotations

import logging
from typing import List

from app.core.config import settings
from app.llm import dispatch

logger = logging.getLogger(__name__)

_SYS = (
    "你是检索查询改写器。把用户问题改写为若干条更利于向量检索的查询，"
    "覆盖同义词、术语、指标口径与中英文表达，必要时做子问题拆解。"
    "只输出 JSON: {\"queries\": [\"...\", \"...\"]}，不要解释。"
)


async def rewrite(query: str) -> List[str]:
    if not settings.QUERY_REWRITE_ENABLED or not settings.LLM_ENABLED:
        return [query]
    n = settings.QUERY_REWRITE_MAX_QUERIES
    try:
        data = await dispatch.one_shot_json(
            _SYS, f"用户问题：{query}\n最多输出 {n} 条查询。", kind=dispatch.REWRITER, timeout=12.0
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("query rewrite failed: %s", e)
        return [query]
    queries = data.get("queries") if isinstance(data, dict) else None
    if not isinstance(queries, list) or not queries:
        return [query]
    out, seen = [], set()
    for q in [query, *queries]:
        q = str(q).strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[: n + 1]
