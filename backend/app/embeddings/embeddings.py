"""Dense embeddings via AWS Bedrock (Cohere embed-v4 / Titan) or an
OpenAI-compatible /v1/embeddings endpoint. No local torch model — this project
runs against hosted embedding models only.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import numpy as np

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
                    region_name=settings.BEDROCK_EMBEDDING_REGION,
                    config=Config(max_pool_connections=32),
                )
    return _bedrock_client


def _embed_bedrock_cohere(client, model_id: str, texts: List[str], dim: int, input_type: str) -> np.ndarray:
    body = json.dumps({
        "texts": texts,
        "input_type": input_type,
        "embedding_types": ["float"],
        "output_dimension": dim,
    })
    resp = client.invoke_model(modelId=model_id, body=body)
    result = json.loads(resp["body"].read())
    return np.array(result["embeddings"]["float"], dtype=np.float32)


def _embed_bedrock_titan(client, model_id: str, texts: List[str], dim: int) -> np.ndarray:
    def _one(text: str) -> list:
        body = json.dumps({"inputText": text, "dimensions": dim, "normalize": True})
        resp = client.invoke_model(modelId=model_id, body=body)
        return json.loads(resp["body"].read())["embedding"]

    out: list = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=min(8, len(texts) or 1)) as pool:
        fut = {pool.submit(_one, t): i for i, t in enumerate(texts)}
        for f in as_completed(fut):
            out[fut[f]] = f.result()
    return np.array(out, dtype=np.float32)


def _embed_bedrock(texts: List[str], input_type: str) -> np.ndarray:
    client = _get_bedrock_client()
    model_id = settings.BEDROCK_EMBEDDING_MODEL
    dim = settings.BEDROCK_EMBEDDING_DIMENSION
    if "cohere" in model_id:
        return _embed_bedrock_cohere(client, model_id, texts, dim, input_type)
    return _embed_bedrock_titan(client, model_id, texts, dim)


def _embed_api(texts: List[str]) -> np.ndarray:
    import httpx

    url = settings.EMBEDDING_API_URL.rstrip("/") + "/v1/embeddings"
    headers = {"Content-Type": "application/json"}
    if settings.EMBEDDING_API_KEY:
        headers["Authorization"] = f"Bearer {settings.EMBEDDING_API_KEY}"
    resp = httpx.post(
        url, headers=headers,
        json={"model": settings.EMBEDDING_API_MODEL, "input": texts}, timeout=60.0,
    )
    resp.raise_for_status()
    items = sorted(resp.json()["data"], key=lambda x: x["index"])
    return np.array([it["embedding"] for it in items], dtype=np.float32)


class EmbeddingService:
    def _provider(self) -> str:
        if settings.EMBEDDING_BEDROCK_ENABLED:
            return "bedrock"
        if settings.EMBEDDING_API_ENABLED:
            return "api"
        raise RuntimeError("No embedding provider enabled (set EMBEDDING_BEDROCK_ENABLED or EMBEDDING_API_ENABLED).")

    def dimension(self) -> int:
        if settings.EMBEDDING_BEDROCK_ENABLED:
            return settings.BEDROCK_EMBEDDING_DIMENSION
        return settings.EMBEDDING_DIMENSION

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension()), dtype=np.float32)
        if self._provider() == "bedrock":
            return _embed_bedrock(texts, "search_document")
        return _embed_api(texts)

    def embed_queries(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension()), dtype=np.float32)
        if self._provider() == "bedrock":
            return _embed_bedrock(texts, "search_query")
        return _embed_api(texts)


embedding_service = EmbeddingService()
