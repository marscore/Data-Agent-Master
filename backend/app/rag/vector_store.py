"""Milvus-backed vector store (one collection per agent).

VECTOR_DB_URI pointing at a *.db file uses milvus-lite (embedded, zero infra);
any other URI connects to a Milvus server. Dynamic fields let each doc carry
arbitrary metadata (metric name, source, catalog...) without schema changes.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

import numpy as np

from app.core.config import resolve_data_path, settings
from app.embeddings.embeddings import embedding_service

logger = logging.getLogger(__name__)

_client = None
_lock = threading.Lock()
_ensured: set = set()


def _get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                # pymilvus autoloads CWD .env and treats MILVUS_URI as a *server* URI;
                # ensure our file-path config never leaks into its reserved key.
                os.environ.pop("MILVUS_URI", None)
                from pymilvus import MilvusClient

                uri = settings.VECTOR_DB_URI
                if uri.endswith(".db") or uri.endswith(".sqlite"):
                    uri = resolve_data_path(uri)
                    os.makedirs(os.path.dirname(uri) or ".", exist_ok=True)
                token = settings.VECTOR_DB_TOKEN or None
                _client = MilvusClient(uri=uri, token=token, db_name=settings.VECTOR_DB_NAME)
                logger.info("Milvus client connected: uri=%s", uri)
    return _client


def collection_name(agent_id: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in agent_id)
    return f"{settings.VECTOR_COLLECTION_PREFIX}_{safe}"


def ensure_collection(agent_id: str) -> str:
    name = collection_name(agent_id)
    if name in _ensured:
        return name
    client = _get_client()
    from pymilvus import DataType

    if not client.has_collection(name):
        dim = embedding_service.dimension()
        schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=512)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field("title", DataType.VARCHAR, max_length=2048)
        schema.add_field("text", DataType.VARCHAR, max_length=65535)
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="vector", metric_type="COSINE", index_type="AUTOINDEX")
        client.create_collection(collection_name=name, schema=schema, index_params=index_params)
        logger.info("Created Milvus collection '%s' (dim=%d)", name, dim)
    client.load_collection(collection_name=name)
    _ensured.add(name)
    return name


def upsert_documents(agent_id: str, docs: List[Dict[str, Any]]) -> int:
    """docs: [{id, title, text, **metadata}]. Embeds text and upserts."""
    if not docs:
        return 0
    name = ensure_collection(agent_id)
    client = _get_client()
    vectors = embedding_service.embed_documents([d.get("text", "") for d in docs])
    rows: List[Dict[str, Any]] = []
    for d, vec in zip(docs, vectors):
        row = {k: v for k, v in d.items() if k not in ("vector",)}
        row.setdefault("title", "")
        row.setdefault("text", "")
        row["id"] = str(d["id"])
        row["vector"] = vec.tolist() if isinstance(vec, np.ndarray) else list(vec)
        rows.append(row)
    client.upsert(collection_name=name, data=rows)
    return len(rows)


def search(agent_id: str, query: str, limit: int, extra_queries: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Vector search across the query and any rewrites; merged + de-duped by id."""
    name = collection_name(agent_id)
    client = _get_client()
    if not client.has_collection(name):
        return []
    if name not in _ensured:
        client.load_collection(collection_name=name)
        _ensured.add(name)
    queries = [query] + [q for q in (extra_queries or []) if q and q != query]
    qvecs = embedding_service.embed_queries(queries)
    hits: Dict[str, Dict[str, Any]] = {}
    results = client.search(
        collection_name=name,
        data=[v.tolist() for v in qvecs],
        limit=limit,
        output_fields=["title", "text"],
        search_params={"metric_type": "COSINE"},
    )
    for per_query in results:
        for hit in per_query:
            doc_id = str(hit.get("id"))
            entity = hit.get("entity", {}) or {}
            score = float(hit.get("distance", 0.0))
            prev = hits.get(doc_id)
            if prev is None or score > prev["score"]:
                hits[doc_id] = {
                    "id": doc_id,
                    "title": entity.get("title", ""),
                    "text": entity.get("text", ""),
                    "score": score,
                    "metadata": {k: v for k, v in entity.items() if k not in ("title", "text")},
                }
    return sorted(hits.values(), key=lambda d: d["score"], reverse=True)


def stats(agent_id: str) -> Dict[str, Any]:
    name = collection_name(agent_id)
    client = _get_client()
    if not client.has_collection(name):
        return {"collection": name, "exists": False, "count": 0}
    try:
        count = client.query(collection_name=name, filter="", output_fields=["count(*)"])
        n = count[0]["count(*)"] if count else 0
    except Exception:  # noqa: BLE001
        n = client.get_collection_stats(name).get("row_count", 0)
    return {"collection": name, "exists": True, "count": int(n)}


def drop(agent_id: str) -> None:
    name = collection_name(agent_id)
    client = _get_client()
    if client.has_collection(name):
        client.drop_collection(name)
    _ensured.discard(name)
