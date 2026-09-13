"""Graph nodes: prepare -> supervisor -> {agent|rag|direct|clarify} -> finalize.

The ReAct tool loop runs entirely inside `agent_node` (bounded by the agent's
max_tool_turns), so tool messages never cross a superstep. Every answer-producing
node streams tokens via emit(); finalize emits the answer_end metadata + a final
event the runner uses to persist memory and close the trace.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langgraph.types import RunnableConfig
from app.agents.context import ctx_of
from app.agents.emit import emit
from app.agents.prompts import CLARIFY_SYSTEM, TOOL_GUIDANCE
from app.agents.state import RootState
from app.core.config import settings
from app.llm import dispatch
from app.rag import retriever

logger = logging.getLogger(__name__)


def _agent_model(ctx) -> str | None:
    return ctx.agent.get("model") or None


def _build_messages(system: str, history: List[Dict[str, str]], user: str) -> List[Dict[str, Any]]:
    msgs: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    for h in history or []:
        role = h.get("role")
        if role in ("user", "assistant") and h.get("content"):
            msgs.append({"role": role, "content": h["content"]})
    msgs.append({"role": "user", "content": user})
    return msgs


def _chunk_emit(text: str, size: int = 24) -> None:
    for i in range(0, max(len(text), 1), size):
        seg = text[i:i + size]
        if seg:
            emit({"type": "token", "content": seg})


# ── prepare ─────────────────────────────────────────────────────────────────────

async def prepare_node(state: RootState, config: RunnableConfig) -> Dict[str, Any]:
    ctx = ctx_of(config)
    user_message = state.get("user_message", "")

    tool_names: List[str] = []
    if ctx.federation:
        try:
            if ctx.tracer:
                with ctx.tracer.span("node", "discover_tools") as info:
                    tools = await ctx.federation.discover()
                    tool_names = [t.flat_name for t in tools]
                    info["tool_count"] = len(tool_names)
                    info["sources"] = [s.id for s in ctx.federation.sources]
            else:
                tools = await ctx.federation.discover()
                tool_names = [t.flat_name for t in tools]
        except Exception as e:  # noqa: BLE001
            logger.warning("tool discovery failed: %s", e)

    retrieved_docs: List[Dict[str, Any]] = []
    rag_context = ""
    if ctx.rag_enabled and ctx.agent.get("rag_enabled", True):
        try:
            if ctx.tracer:
                with ctx.tracer.span("retrieval", "rag_retrieve") as info:
                    retrieved_docs = await retriever.retrieve(ctx.agent["id"], user_message, ctx.top_k)
                    info["retrieved"] = len(retrieved_docs)
            else:
                retrieved_docs = await retriever.retrieve(ctx.agent["id"], user_message, ctx.top_k)
            rag_context = retriever.format_context(retrieved_docs)
        except Exception as e:  # noqa: BLE001
            logger.warning("RAG retrieve failed: %s", e)

    emit({"type": "status", "stage": "prepared",
          "tools": len(tool_names), "docs": len(retrieved_docs)})
    return {"tool_names": tool_names, "retrieved_docs": retrieved_docs,
            "rag_context": rag_context, "tool_calls": []}


# ── agent (ReAct tool loop) ──────────────────────────────────────────────────────

async def agent_node(state: RootState, config: RunnableConfig) -> Dict[str, Any]:
    ctx = ctx_of(config)
    fed = ctx.federation
    system = (ctx.agent.get("system_prompt") or "") + (state.get("rag_context") or "") + TOOL_GUIDANCE
    messages = _build_messages(system, state.get("history", []), state.get("user_message", ""))
    tools = fed.openai_tools() if fed else []
    max_turns = ctx.agent.get("max_tool_turns") or settings.AGENT_MAX_TOOL_TURNS

    tool_summaries: List[Dict[str, Any]] = []
    final_text = ""

    for turn in range(max_turns):
        choice = await dispatch.agent_turn(messages, tools, model=_agent_model(ctx))
        if ctx.tracer and getattr(choice, "usage", None):
            ctx.tracer.add_tokens(choice.usage.input_tokens, choice.usage.output_tokens)

        tool_calls = choice.message.tool_calls
        if choice.finish_reason == "tool_calls" and tool_calls:
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": choice.message.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            }
            if getattr(choice, "anthropic_content", None) is not None:
                assistant_msg["_anthropic_content"] = choice.anthropic_content
            messages.append(assistant_msg)

            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                emit({"type": "tool_call", "tool": tc.function.name, "args": args})
                if ctx.tracer:
                    with ctx.tracer.span("tool", tc.function.name, {"args": args}) as info:
                        result = await fed.call(tc.function.name, args)
                        info.update({"ok": result["ok"], "source": result.get("source"),
                                     "latency_ms": result.get("latency_ms")})
                else:
                    result = await fed.call(tc.function.name, args)
                emit({"type": "tool_result", "tool": result.get("tool"), "source": result.get("source"),
                      "ok": result["ok"], "latency_ms": result.get("latency_ms")})
                tool_summaries.append({"tool": result.get("tool"), "source": result.get("source"),
                                       "ok": result["ok"], "latency_ms": result.get("latency_ms")})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result["text"]})
            continue

        final_text = choice.message.content or ""
        break
    else:
        # budget exhausted: ask for a final answer without tools
        messages.append({"role": "user", "content": "请基于以上工具结果，直接给出最终答复。"})
        parts: List[str] = []
        async for tok in dispatch.stream_text(messages, model=_agent_model(ctx)):
            parts.append(tok)
        final_text = "".join(parts)

    emit({"type": "answer_start"})
    _chunk_emit(final_text)
    return {"final_text": final_text, "tool_calls": tool_summaries, "route": "agent"}


# ── rag / direct / clarify ────────────────────────────────────────────────────────

async def rag_node(state: RootState, config: RunnableConfig) -> Dict[str, Any]:
    ctx = ctx_of(config)
    system = ((ctx.agent.get("system_prompt") or "") + (state.get("rag_context") or "")
              + "\n\n请仅依据上述检索资料回答；资料不足时明确说明，不要编造。")
    messages = _build_messages(system, state.get("history", []), state.get("user_message", ""))
    emit({"type": "answer_start"})
    parts: List[str] = []
    async for tok in dispatch.stream_text(messages, model=_agent_model(ctx)):
        parts.append(tok)
        emit({"type": "token", "content": tok})
    return {"final_text": "".join(parts), "route": "rag"}


async def direct_node(state: RootState, config: RunnableConfig) -> Dict[str, Any]:
    ctx = ctx_of(config)
    system = ctx.agent.get("system_prompt") or "你是一个乐于助人的助手。"
    messages = _build_messages(system, state.get("history", []), state.get("user_message", ""))
    emit({"type": "answer_start"})
    parts: List[str] = []
    async for tok in dispatch.stream_text(messages, model=_agent_model(ctx)):
        parts.append(tok)
        emit({"type": "token", "content": tok})
    return {"final_text": "".join(parts), "route": "direct"}


async def clarify_node(state: RootState, config: RunnableConfig) -> Dict[str, Any]:
    ctx = ctx_of(config)
    try:
        question = await dispatch.one_shot_text(CLARIFY_SYSTEM, state.get("user_message", ""), timeout=12.0)
    except Exception:  # noqa: BLE001
        question = ""
    if not question:
        question = "能再说得具体一点吗？例如你想查询哪个指标、什么时间范围？"
    emit({"type": "answer_start"})
    _chunk_emit(question)
    return {"final_text": question, "route": "clarify"}


# ── finalize ─────────────────────────────────────────────────────────────────────

async def finalize_node(state: RootState, config: RunnableConfig) -> Dict[str, Any]:
    ctx = ctx_of(config)
    route = state.get("route", "")
    final_text = state.get("final_text", "")
    docs = state.get("retrieved_docs") or []
    sources = [
        {"id": d.get("id"), "title": d.get("title"),
         "score": round(float(d.get("score", 0.0)), 4),
         "rerank_score": (round(float(d["rerank_score"]), 4) if d.get("rerank_score") is not None else None)}
        for d in docs[:8]
    ]
    run_id = ctx.tracer.run_id if ctx.tracer else None
    emit({"type": "answer_end", "route": route, "sources": sources,
          "tool_calls": state.get("tool_calls") or [], "run_id": run_id})
    emit({"type": "final", "text": final_text, "route": route, "run_id": run_id})
    return {}
