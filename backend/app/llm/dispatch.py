"""Unified LLM dispatch shared by every agent node.

Two providers, one interface:
  - Bedrock + Anthropic model  -> native Messages API adapter (bedrock_anthropic)
  - anything else              -> OpenAI-compatible chat.completions
When LLM_ENABLED is false, returns deterministic mock output so the whole graph
(routing, tool loop, streaming, memory, trace) is exercisable fully offline.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.core.config import settings
from app.llm import bedrock_anthropic
from app.llm.openai_client import get_openai_client

logger = logging.getLogger(__name__)

CHAT = "chat"
REWRITER = "rewriter"


def resolve_model(kind: str = CHAT, override: Optional[str] = None) -> Tuple[str, bool]:
    """Return (model_id, use_anthropic) for the given role."""
    if override:
        model = override
    elif settings.LLM_PROVIDER == "bedrock":
        if kind == REWRITER:
            model = settings.BEDROCK_QUERY_REWRITER_MODEL or settings.BEDROCK_CHAT_MODEL
        else:
            model = settings.BEDROCK_CHAT_MODEL
    else:
        if kind == REWRITER:
            model = settings.OPENAI_QUERY_REWRITER_MODEL or settings.OPENAI_CHAT_MODEL
        else:
            model = settings.OPENAI_CHAT_MODEL
    use_anthropic = settings.LLM_PROVIDER == "bedrock" and bedrock_anthropic.is_anthropic_model(model)
    return model, use_anthropic


# ── mock (offline) ───────────────────────────────────────────────────────────

def _mock_choice(messages: List[Dict[str, Any]]) -> SimpleNamespace:
    last_user = next((m.get("content") for m in reversed(messages) if m.get("role") == "user"), "")
    text = f"[mock:{settings.LLM_PROVIDER}] 已收到问题：{str(last_user)[:120]}"
    return SimpleNamespace(
        finish_reason="stop",
        message=SimpleNamespace(content=text, tool_calls=None),
        anthropic_content=None,
        usage=SimpleNamespace(input_tokens=0, output_tokens=0),
    )


# ── non-streaming tool-calling turn ────────────────────────────────────────────

async def agent_turn(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model: Optional[str] = None,
) -> SimpleNamespace:
    if not settings.LLM_ENABLED:
        return _mock_choice(messages)
    resolved, use_anthropic = resolve_model(CHAT, model)
    if use_anthropic:
        return await bedrock_anthropic.agent_completion(messages, tools, resolved)

    client = get_openai_client()
    kwargs: Dict[str, Any] = {"model": resolved, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        if settings.LLM_TOOL_CHOICE:
            kwargs["tool_choice"] = settings.LLM_TOOL_CHOICE
    resp = await client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    # Normalise to the same shape the anthropic adapter returns.
    return SimpleNamespace(
        finish_reason=choice.finish_reason,
        message=choice.message,
        anthropic_content=None,
        usage=SimpleNamespace(
            input_tokens=getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
            output_tokens=getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
        ),
    )


# ── streaming text (final answer) ──────────────────────────────────────────────

async def stream_text(
    messages: List[Dict[str, Any]], model: Optional[str] = None
) -> AsyncGenerator[str, None]:
    if not settings.LLM_ENABLED:
        yield _mock_choice(messages).message.content
        return
    resolved, use_anthropic = resolve_model(CHAT, model)
    if use_anthropic:
        async for chunk in bedrock_anthropic.stream_chat(messages, resolved):
            yield chunk
        return
    client = get_openai_client()
    stream = await client.chat.completions.create(model=resolved, messages=messages, stream=True)
    async for event in stream:
        delta = event.choices[0].delta.content if event.choices else None
        if delta:
            yield delta


# ── small one-shot helpers (routing / query rewrite) ────────────────────────────

async def one_shot_text(
    system: str, user_content: str, kind: str = CHAT, model: Optional[str] = None, timeout: float = 12.0
) -> str:
    if not settings.LLM_ENABLED:
        return ""
    resolved, use_anthropic = resolve_model(kind, model)
    if use_anthropic:
        return await bedrock_anthropic.call_text(system, user_content, resolved, timeout=timeout)
    client = get_openai_client()
    resp = await client.chat.completions.create(
        model=resolved,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        timeout=timeout,
    )
    return resp.choices[0].message.content or ""


async def one_shot_json(
    system: str, user_content: str, kind: str = CHAT, model: Optional[str] = None, timeout: float = 12.0
) -> Dict[str, Any]:
    raw = await one_shot_text(system, user_content, kind=kind, model=model, timeout=timeout)
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("one_shot_json: unparseable LLM output: %r", raw[:200])
        return {}
