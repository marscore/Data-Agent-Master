"""Transport-agnostic MCP client.

Three transports, one interface (`list_tools` / `call_tool`):
  - "jsonrpc_http"    : a plain JSON-RPC 2.0 POST endpoint (data-master's
                        /api/mcp — stateless request/response, no MCP session).
  - "streamable_http" : the MCP standard remote transport (OpenMetadata, Superset).
  - "sse"             : the legacy MCP remote transport some servers still speak.

Every source declares its own auth header; identity is passed through verbatim
(this project never signs its own credential — the target system's ACL is the
authorization boundary).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

RawTool = Tuple[str, str, Dict[str, Any]]  # (name, description, inputSchema)


@dataclass
class McpSource:
    id: str
    url: str
    transport: str = "jsonrpc_http"        # jsonrpc_http | streamable_http | sse
    label: str = ""
    auth_mode: str = "passthrough"          # passthrough | static | none
    static_secret: str = ""
    header_name: str = "Authorization"
    header_prefix: str = "Bearer "
    allowed_tools: List[str] = field(default_factory=list)  # empty = all
    timeout: float = 20.0
    verify_tls: bool = True

    def headers(self, access_token: Optional[str]) -> Dict[str, str]:
        secret = self.static_secret if self.auth_mode == "static" else access_token
        if self.auth_mode == "none" or not secret:
            return {}
        return {self.header_name: f"{self.header_prefix}{secret}"}


def flatten_exception_group(e: BaseException) -> List[BaseException]:
    if isinstance(e, BaseExceptionGroup):  # noqa: F821 (py3.11+ builtin)
        leaves: List[BaseException] = []
        for sub in e.exceptions:
            leaves.extend(flatten_exception_group(sub))
        return leaves
    return [e]


def describe_exception(e: BaseException) -> str:
    leaves = flatten_exception_group(e)
    return "; ".join(f"{type(x).__name__}: {x}" for x in leaves)


# ── JSON-RPC over plain HTTP (data-master /api/mcp) ────────────────────────────

async def _jsonrpc(source: McpSource, method: str, params: Optional[dict], headers: Dict[str, str]) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    async with httpx.AsyncClient(timeout=source.timeout, verify=source.verify_tls) as http:
        resp = await http.post(source.url, json=payload, headers={"Content-Type": "application/json", **headers})
        resp.raise_for_status()
        if resp.status_code == 202 or not resp.content:
            return {}
        body = resp.json()
        if "error" in body and body["error"]:
            err = body["error"]
            raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
        return body.get("result", {})


async def _jsonrpc_list_tools(source: McpSource, headers: Dict[str, str]) -> List[RawTool]:
    result = await _jsonrpc(source, "tools/list", {}, headers)
    out: List[RawTool] = []
    for t in result.get("tools", []):
        out.append((t.get("name", ""), t.get("description", ""), t.get("inputSchema") or {}))
    return out


async def _jsonrpc_call_tool(source: McpSource, name: str, args: dict, headers: Dict[str, str]) -> str:
    result = await _jsonrpc(source, "tools/call", {"name": name, "arguments": args}, headers)
    return _extract_text(result.get("content", []))


# ── MCP SDK transports (streamable_http / sse) ─────────────────────────────────

def _insecure_httpx_factory(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
    kwargs: Dict[str, Any] = {"follow_redirects": True, "verify": False}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if headers is not None:
        kwargs["headers"] = headers
    if auth is not None:
        kwargs["auth"] = auth
    return httpx.AsyncClient(**kwargs)


@asynccontextmanager
async def _mcp_session(source: McpSource, headers: Dict[str, str]):
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamablehttp_client

    client_kwargs: Dict[str, Any] = {} if source.verify_tls else {"httpx_client_factory": _insecure_httpx_factory}
    if source.transport == "sse":
        async with sse_client(source.url, headers=headers, timeout=source.timeout, **client_kwargs) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        async with streamablehttp_client(
            source.url, headers=headers, timeout=source.timeout, **client_kwargs
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def _sdk_list_tools(source: McpSource, headers: Dict[str, str]) -> List[RawTool]:
    async with _mcp_session(source, headers) as session:
        result = await session.list_tools()
        return [(t.name, t.description or "", t.inputSchema or {}) for t in result.tools]


async def _sdk_call_tool(source: McpSource, name: str, args: dict, headers: Dict[str, str]) -> str:
    async with _mcp_session(source, headers) as session:
        result = await session.call_tool(name, arguments=args)
        blocks = [{"type": getattr(c, "type", "text"), "text": getattr(c, "text", "")} for c in result.content]
        return _extract_text(blocks)


def _extract_text(content: List[dict]) -> str:
    parts = [c.get("text", "") for c in content if c.get("type", "text") == "text"]
    return "\n".join(p for p in parts if p)


# ── public interface ───────────────────────────────────────────────────────────

async def list_tools(source: McpSource, access_token: Optional[str]) -> List[RawTool]:
    headers = source.headers(access_token)
    if source.transport == "jsonrpc_http":
        return await _jsonrpc_list_tools(source, headers)
    return await _sdk_list_tools(source, headers)


async def call_tool(source: McpSource, name: str, args: dict, access_token: Optional[str]) -> str:
    headers = source.headers(access_token)
    if source.transport == "jsonrpc_http":
        return await _jsonrpc_call_tool(source, name, args, headers)
    return await _sdk_call_tool(source, name, args, headers)
