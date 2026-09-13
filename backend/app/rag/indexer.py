"""Build the RAG index for an agent.

Primary source: the agent's own MCP tools. If a federated tool named
`*__list_metrics` exists (data-master), we enumerate metrics and index one doc
per metric (enriched via `*__get_metric` when available). Any tool output that
is a JSON list of objects with name/description is indexed generically, so this
also works for OpenMetadata glossary terms etc. Callers may also push arbitrary
documents directly (admin upload).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.mcp.federation import Federation
from app.rag import vector_store

logger = logging.getLogger(__name__)


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _as_items(parsed: Any) -> List[Dict[str, Any]]:
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        for key in ("items", "data", "metrics", "results", "content"):
            v = parsed.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _doc_from_item(prefix: str, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = item.get("name") or item.get("metricName") or item.get("fullyQualifiedName") or item.get("id")
    if not name:
        return None
    title = str(item.get("displayName") or name)
    parts = [f"名称: {name}"]
    for k in ("displayName", "description", "definition", "expression", "formula", "grain",
              "unit", "owner", "domain", "dimensions", "tags"):
        v = item.get(k)
        if v:
            parts.append(f"{k}: {v if not isinstance(v, (list, dict)) else json.dumps(v, ensure_ascii=False)}")
    return {
        "id": f"{prefix}:{name}",
        "title": title,
        "text": "\n".join(parts),
        "kind": prefix,
        "name": str(name),
    }


async def reindex_from_mcp(agent_id: str, federation: Federation) -> Dict[str, Any]:
    """Discover the agent's tools, pull metric/glossary knowledge, upsert docs."""
    await federation.discover()
    tools = list(federation._index.values())  # noqa: SLF001 (intentional internal use)
    docs: List[Dict[str, Any]] = []
    tool_reports: List[Dict[str, Any]] = []

    # 1) metrics via list_metrics + get_metric
    list_tool = next((t for t in tools if t.real_name == "list_metrics"), None)
    get_tool = next((t for t in tools if t.real_name == "get_metric"), None)
    if list_tool:
        res = await federation.call(list_tool.flat_name, {})
        items = _as_items(_safe_json(res.get("text", ""))) if res.get("ok") else []
        tool_reports.append({"tool": "list_metrics", "ok": res.get("ok"), "found": len(items)})
        for it in items:
            enriched = it
            name = it.get("name") or it.get("metricName")
            if get_tool and name:
                gr = await federation.call(get_tool.flat_name, {"name": name})
                parsed = _safe_json(gr.get("text", "")) if gr.get("ok") else None
                if isinstance(parsed, dict):
                    enriched = {**it, **parsed}
            doc = _doc_from_item("metric", enriched)
            if doc:
                docs.append(doc)

    # 2) generic: any *list*/*search* tool whose output is a JSON list of named objects
    for t in tools:
        if t.real_name in ("list_metrics", "get_metric"):
            continue
        if not (t.real_name.startswith("list_") or "search" in t.real_name):
            continue
        try:
            res = await federation.call(t.flat_name, {})
        except Exception:  # noqa: BLE001
            continue
        if not res.get("ok"):
            continue
        items = _as_items(_safe_json(res.get("text", "")))
        added = 0
        for it in items:
            doc = _doc_from_item(t.real_name, it)
            if doc:
                docs.append(doc)
                added += 1
        if added:
            tool_reports.append({"tool": t.real_name, "ok": True, "found": added})

    # de-dupe by id
    seen: Dict[str, Dict[str, Any]] = {d["id"]: d for d in docs}
    unique = list(seen.values())
    count = vector_store.upsert_documents(agent_id, unique) if unique else 0
    logger.info("reindex agent=%s indexed=%d from %d tools", agent_id, count, len(tool_reports))
    return {"agent_id": agent_id, "indexed": count, "sources": tool_reports}


def index_documents(agent_id: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    count = vector_store.upsert_documents(agent_id, docs)
    return {"agent_id": agent_id, "indexed": count}
