"""Cross-encoder reranking via AWS Bedrock (Cohere rerank v3.5) or a remote
POST /rerank endpoint. Returns docs sorted by relevance with a min-max
normalised `rerank_score` in [0,1] plus the raw provider score.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_bedrock_client = None
_client_lock = threading.Lock()


def _get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        with _client_lock:
            if _bedrock_client is None:
                import boto3
                from botocore.config import Config

                _bedrock_client = boto3.client(
                    "bedrock-runtime",
                    region_name=settings.BEDROCK_RERANKER_REGION,
                    config=Config(max_pool_connections=32),
                )
    return _bedrock_client


def _minmax(scores: List[float]) -> List[float]:
    if not scores:
        return scores
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [1.0] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


def _passage(doc: Dict[str, Any]) -> str:
    title = (doc.get("title") or "").strip()
    text = (doc.get("text") or "").strip()
    return f"{title}\n{text}" if title else text


def _rerank_bedrock(query: str, passages: List[str]) -> List[Dict[str, Any]]:
    client = _get_bedrock_client()
    body = json.dumps({
        "api_version": 2, "query": query, "documents": passages, "top_n": len(passages),
    })
    resp = client.invoke_model(modelId=settings.BEDROCK_RERANKER_MODEL, body=body)
    results = json.loads(resp["body"].read())["results"]
    return [{"index": r["index"], "score": r["relevance_score"]} for r in results]


def _rerank_api(query: str, passages: List[str]) -> List[Dict[str, Any]]:
    import httpx

    url = settings.RERANKER_API_URL.rstrip("/") + "/rerank"
    resp = httpx.post(url, json={"query": query, "texts": passages}, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


class RerankerService:
    def available(self) -> bool:
        return settings.RERANKER_BEDROCK_ENABLED or settings.RERANKER_API_ENABLED

    def rerank(
        self, query: str, documents: List[Dict[str, Any]], top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not documents or not self.available():
            return documents[:top_k] if top_k else documents
        passages = [_passage(d) for d in documents]
        if settings.RERANKER_BEDROCK_ENABLED:
            results = _rerank_bedrock(query, passages)
        else:
            results = _rerank_api(query, passages)
        raw = [r["score"] for r in results]
        norm = _minmax(raw)
        for r, n in zip(results, norm):
            documents[r["index"]]["rerank_score"] = n
            documents[r["index"]]["rerank_score_raw"] = r["score"]
        ranked = [documents[r["index"]] for r in results]
        return ranked[:top_k] if top_k else ranked


reranker_service = RerankerService()
