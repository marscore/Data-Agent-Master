"""Federate tools across many MCP servers into one flat tool set for the LLM.

Tool names from different servers can collide (data-master and Superset could
both expose `search`), so every tool the model sees is namespaced to
`{source_id}__{sanitized_tool}`; `call` looks the pair back up to route to the
right server. Tool *schemas* are cached per URL (a property of the server, not
the caller); nothing about which sources exist this turn is cached.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.mcp import client as mcp_client
from app.mcp.client import McpSource, RawTool, describe_exception

logger = logging.getLogger(__name__)

_NAME_SANITIZE = re.compile(r"[^a-zA-Z0-9_-]")
_CACHE_TTL = 300.0
_tools_cache: Dict[str, Tuple[float, List[RawTool]]] = {}  # keyed by url


def _sanitize(name: str) -> str:
    return _NAME_SANITIZE.sub("_", name)


@dataclass
class FederatedTool:
    flat_name: str
    real_name: str
    source: McpSource
    description: str
    input_schema: Dict[str, Any]

    def to_openai(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.flat_name,
                "description": self.description,
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }


async def _list_source_tools(source: McpSource, access_token: Optional[str]) -> List[RawTool]:
    now = time.monotonic()
    cached = _tools_cache.get(source.url)
    if cached and cached[0] > now:
        return cached[1]
    tools = await mcp_client.list_tools(source, access_token)
    _tools_cache[source.url] = (now + _CACHE_TTL, tools)
    return tools


def invalidate_cache(url: Optional[str] = None) -> None:
    if url is None:
        _tools_cache.clear()
    else:
        _tools_cache.pop(url, None)


class Federation:
    """Request-scoped view of every enabled MCP source for one agent turn."""

    def __init__(self, sources: List[McpSource], access_token: Optional[str]):
        self.sources = sources
        self.access_token = access_token
        self._index: Dict[str, FederatedTool] = {}

    async def discover(self) -> List[FederatedTool]:
        """List + flatten tools from every source. Failures degrade to skipping
        that source (logged), never abort the whole turn."""
        tools: List[FederatedTool] = []
        for source in self.sources:
            try:
                raw = await _list_source_tools(source, self.access_token)
            except Exception as e:  # noqa: BLE001
                logger.warning("MCP source '%s' tools/list failed: %s", source.id, describe_exception(e))
                continue
            allow = set(source.allowed_tools or [])
            for name, desc, schema in raw:
                if allow and name not in allow:
                    continue
                flat = f"{source.id}__{_sanitize(name)}"
                ft = FederatedTool(flat, name, source, desc, schema)
                self._index[flat] = ft
                tools.append(ft)
        return tools

    def openai_tools(self) -> List[Dict[str, Any]]:
        return [t.to_openai() for t in self._index.values()]

    async def call(self, flat_name: str, args: dict) -> Dict[str, Any]:
        ft = self._index.get(flat_name)
        if ft is None:
            return {"ok": False, "source": None, "tool": flat_name, "text": f"未知工具: {flat_name}"}
        start = time.monotonic()
        try:
            text = await mcp_client.call_tool(ft.source, ft.real_name, args, self.access_token)
            ok = True
        except Exception as e:  # noqa: BLE001
            text = f"工具调用失败: {describe_exception(e)}"
            ok = False
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"ok": ok, "source": ft.source.id, "tool": ft.real_name,
                "flat_name": flat_name, "text": text, "latency_ms": latency_ms}


async def probe(source: McpSource, access_token: Optional[str]) -> Dict[str, Any]:
    """Connectivity check used by the admin console. Never raises."""
    start = time.monotonic()
    try:
        tools = await mcp_client.list_tools(source, access_token)
        return {
            "id": source.id, "ok": True, "tool_count": len(tools),
            "tools": [t[0] for t in tools][:50],
            "latency_ms": int((time.monotonic() - start) * 1000),
        }
    except Exception as e:  # noqa: BLE001
        return {"id": source.id, "ok": False, "error": describe_exception(e),
                "latency_ms": int((time.monotonic() - start) * 1000)}
