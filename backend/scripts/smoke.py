"""End-to-end smoke test against a running Data Agent Master backend + mock MCP server.

Exercises the whole loop with REAL Bedrock:
  create agent -> reindex RAG from MCP -> streaming chat (routing + tool loop +
  answer) -> trace inspection -> multi-turn memory.

Usage:  python scripts/smoke.py   (backend on :8700, mock MCP on :8790)
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import json
import sys

import httpx

BASE = "http://localhost:8700/api/v1"
MOCK_URL = "http://localhost:8790/mcp"
AGENT_ID = "smoke"

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def sse_chat(client: httpx.Client, message: str, session_id: str | None) -> dict:
    events: list[dict] = []
    payload = {"agent_id": AGENT_ID, "message": message, "session_id": session_id}
    with client.stream("POST", f"{BASE}/chat", json=payload, timeout=120) as r:
        for line in r.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                events.append(json.loads(data))
            except json.JSONDecodeError:
                pass
    tokens = "".join(e.get("content", "") for e in events if e.get("type") == "token")
    return {"events": events, "text": tokens,
            "tool_calls": [e for e in events if e.get("type") == "tool_call"],
            "session": next((e for e in events if e.get("type") == "session"), {}),
            "answer_end": next((e for e in events if e.get("type") == "answer_end"), {})}


def main() -> int:
    c = httpx.Client()

    # 0) meta / providers
    meta = c.get(f"{BASE}/meta").json()
    check("meta reachable", meta.get("provider") == "bedrock", f"provider={meta.get('provider')} model={meta.get('chat_model')}")

    # 1) create/update the smoke agent -> mock MCP
    agent_body = {
        "id": AGENT_ID, "name": "Smoke 问数", "description": "e2e",
        "system_prompt": "你是数据问数助手。用中文回答。先用工具取数再作答，不要编造。",
        "routing_mode": "supervisor", "rag_enabled": True,
        "mcp_sources": [{"id": "mock", "label": "mock-dm", "url": MOCK_URL,
                         "transport": "jsonrpc_http", "auth_mode": "none", "enabled": True}],
    }
    r = c.post(f"{BASE}/agents", json=agent_body)
    if r.status_code == 409:
        r = c.patch(f"{BASE}/agents/{AGENT_ID}", json=agent_body)
    check("agent created/updated", r.status_code in (200, 201), f"http {r.status_code}")

    # 2) tools discovered through MCP federation
    tools = c.get(f"{BASE}/agents/{AGENT_ID}/tools").json()
    names = {t["real_name"] for t in tools.get("tools", [])}
    check("MCP tools discovered", {"list_metrics", "get_metric", "query_metric"} <= names, f"tools={sorted(names)}")

    # 3) reindex RAG from MCP
    rep = c.post(f"{BASE}/agents/{AGENT_ID}/reindex", timeout=120).json()
    check("RAG reindex from MCP", rep.get("indexed", 0) >= 3, f"indexed={rep.get('indexed')}")

    # 4) streaming chat — routing + tool loop + answer
    turn1 = sse_chat(c, "帮我查一下本月的月活跃用户 MAU 是多少？", None)
    session_id = turn1["session"].get("session_id")
    run_id = turn1["session"].get("run_id")
    used_query_metric = any(t.get("tool", "").endswith("query_metric") for t in turn1["tool_calls"])
    check("turn1 got session/run id", bool(session_id and run_id), f"session={session_id}")
    check("turn1 called query_metric", used_query_metric, f"tool_calls={[t.get('tool') for t in turn1['tool_calls']]}")
    check("turn1 produced an answer", len(turn1["text"]) > 5, f"answer[:60]={turn1['text'][:60]!r}")
    check("turn1 answer mentions the number", ("128" in turn1["text"] or "1,284" in turn1["text"] or "1284" in turn1["text"]),
          "expected ~1,284,500 to appear")

    # 5) trace inspection
    tr = c.get(f"{BASE}/traces/{run_id}").json()
    kinds = {s["kind"] for s in tr.get("spans", [])}
    check("trace recorded with spans", tr.get("status") == "ok" and "tool" in kinds,
          f"status={tr.get('status')} span_kinds={sorted(kinds)} route={tr.get('route')}")

    # 6) multi-turn memory (follow-up refers to prior turn)
    turn2 = sse_chat(c, "再按渠道拆一下", session_id)
    check("turn2 reused session", turn2["session"].get("session_id") == session_id, "same session id")
    check("turn2 produced an answer", len(turn2["text"]) > 5, f"answer[:60]={turn2['text'][:60]!r}")

    conv = c.get(f"{BASE}/conversations/{session_id}").json()
    check("conversation memory persisted", len(conv.get("messages", [])) >= 4,
          f"messages={len(conv.get('messages', []))}")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\n==== SMOKE: {passed}/{total} passed ====")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
