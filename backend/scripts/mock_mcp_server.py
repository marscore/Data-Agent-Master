"""Mock data-master MCP server — implements the exact JSON-RPC 2.0 contract of
data-master's POST /api/mcp (initialize / tools/list / tools/call), exposing
list_metrics / get_metric / query_metric with canned semantic data.

Lets AgentWorks prove the full loop (MCP federation -> RAG -> tool loop -> answer
-> memory -> trace) end-to-end without running the Java backend. Point a source
at http://localhost:8790/mcp (transport=jsonrpc_http, auth=none).

Run:  uvicorn scripts.mock_mcp_server:app --port 8790
"""

from __future__ import annotations

import json
from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="mock-data-master-mcp")

METRICS = {
    "mau": {"name": "mau", "displayName": "月活跃用户", "description": "自然月内有过登录或交易行为的去重用户数。",
            "grain": "month", "unit": "人", "owner": "growth", "domain": "user",
            "dimensions": ["channel", "region", "platform"],
            "definition": "COUNT(DISTINCT user_id) WHERE active_in_month = true"},
    "gmv": {"name": "gmv", "displayName": "成交总额", "description": "订单成交总金额（含税，未扣退款）。",
            "grain": "day", "unit": "元", "owner": "finance", "domain": "trade",
            "dimensions": ["channel", "product_line", "region"],
            "definition": "SUM(order_amount) WHERE order_status IN ('paid','shipped','done')"},
    "new_users": {"name": "new_users", "displayName": "新增用户", "description": "首次注册的用户数。",
                  "grain": "day", "unit": "人", "owner": "growth", "domain": "user",
                  "dimensions": ["channel", "region"],
                  "definition": "COUNT(user_id) WHERE first_register_date = day"},
}

_VALUES = {"mau": 1284500, "gmv": 8630000.0, "new_users": 20450}
_BY_CHANNEL = {
    "mau": {"app": 812300, "web": 402100, "mini_program": 70100},
    "gmv": {"app": 5210000.0, "web": 2870000.0, "mini_program": 550000.0},
    "new_users": {"app": 12100, "web": 6900, "mini_program": 1450},
}


def _tools():
    obj = {"type": "object"}
    return [
        {"name": "list_metrics", "description": "列出所有可用指标（名称/口径/粒度/维度）。",
         "inputSchema": {**obj, "properties": {}}},
        {"name": "get_metric", "description": "按名称获取单个指标的完整口径定义。",
         "inputSchema": {**obj, "properties": {"name": {"type": "string", "description": "指标名，从 list_metrics 获取"}}, "required": ["name"]}},
        {"name": "query_metric", "description": "按口径受治执行取指标值，支持维度拆分/过滤/时间范围/同环比。",
         "inputSchema": {**obj, "properties": {
             "metricName": {"type": "string"},
             "dimensions": {"type": "array", "items": {"type": "string"}},
             "filters": {"type": "object"},
             "grain": {"type": "string"},
             "dateFrom": {"type": "string"}, "dateTo": {"type": "string"},
             "compareWith": {"type": "string"}, "freshness": {"type": "string"},
             "limit": {"type": "integer"}}, "required": ["metricName"]}},
    ]


def _call(name: str, args: dict) -> str:
    if name == "list_metrics":
        return json.dumps([{k: m[k] for k in ("name", "displayName", "description", "grain", "unit", "dimensions")}
                           for m in METRICS.values()], ensure_ascii=False)
    if name == "get_metric":
        m = METRICS.get(args.get("name", ""))
        return json.dumps(m or {"error": "unknown metric"}, ensure_ascii=False)
    if name == "query_metric":
        mn = args.get("metricName", "")
        if mn not in METRICS:
            return json.dumps({"error": f"unknown metric: {mn}"}, ensure_ascii=False)
        dims = args.get("dimensions") or []
        result = {"metricName": mn, "definition": METRICS[mn]["definition"],
                  "unit": METRICS[mn]["unit"], "grain": args.get("grain") or METRICS[mn]["grain"],
                  "freshness": "T-1", "dataThrough": str(date.today()), "source": "starrocks:ads.mv_" + mn}
        if "channel" in dims:
            result["rows"] = [{"channel": c, "value": v} for c, v in _BY_CHANNEL[mn].items()]
        else:
            result["value"] = _VALUES[mn]
        return json.dumps(result, ensure_ascii=False)
    return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)


@app.post("/mcp")
async def mcp(req: Request):
    body = await req.json()
    rid = body.get("id")
    method = body.get("method", "")
    if rid is None:
        return Response(status_code=202)
    if method == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "mock-data-master", "version": "1.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": _tools()}
    elif method == "tools/call":
        params = body.get("params", {})
        text = _call(params.get("name", ""), params.get("arguments") or {})
        result = {"content": [{"type": "text", "text": text}]}
    else:
        return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}})
    return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": result})
