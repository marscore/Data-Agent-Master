"""Anthropic Claude on AWS Bedrock — native Messages API adapter.

The bedrock-mantle gateway does not expose OpenAI-compatible /chat/completions
for Anthropic models; they are served at the native Anthropic Messages API. So
Anthropic models (anthropic.claude-*) go through this module:
  - AsyncAnthropicBedrock for cross-region inference IDs (global./us./eu./...)
    via bedrock-runtime; AsyncAnthropicBedrockMantle for bare model IDs.
  - auth mode "bearer" (explicit api_key from a mantle token) or "sigv4"
    (api_key=None -> boto3 default credential chain, our local SSO role).
  - OpenAI-style messages/tools are converted to Anthropic format.
  - Sonnet 5 keeps adaptive thinking always on, so text is extracted by
    filtering content blocks (never content[0]); raw blocks are replayed
    verbatim on the next turn to preserve thinking/tool_use signatures.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Dict, List, Tuple, Union

from anthropic import AsyncAnthropicBedrock, AsyncAnthropicBedrockMantle

from app.core.config import settings
from app.llm.bedrock_util import get_bedrock_anthropic_base_url, get_bedrock_token

logger = logging.getLogger(__name__)

_AnthropicClient = Union[AsyncAnthropicBedrock, AsyncAnthropicBedrockMantle]
_TOKEN_TTL_SECONDS = 50 * 60

_clients: Dict[str, Dict[str, Any]] = {}
_client_lock = threading.Lock()

# Cross-region inference profile prefixes — only registered on bedrock-runtime.
_CROSS_REGION_PREFIXES = ("us.", "eu.", "global.", "apac.", "jp.")


def is_anthropic_model(model_id: str) -> bool:
    return "anthropic." in model_id


def _uses_bedrock_runtime(model_id: str) -> bool:
    return model_id.startswith(_CROSS_REGION_PREFIXES)


def get_client(model_id: str) -> _AnthropicClient:
    kind = "runtime" if _uses_bedrock_runtime(model_id) else "mantle"
    use_sigv4 = settings.BEDROCK_ANTHROPIC_AUTH_MODE == "sigv4"
    now = time.time()
    with _client_lock:
        entry = _clients.get(kind)
        if entry is None or (entry["expires_at"] is not None and now >= entry["expires_at"]):
            region = settings.BEDROCK_REGION
            api_key = None if use_sigv4 else get_bedrock_token(region)
            if kind == "runtime":
                client: _AnthropicClient = AsyncAnthropicBedrock(
                    aws_region=region, api_key=api_key, max_retries=0, timeout=60.0
                )
            else:
                client = AsyncAnthropicBedrockMantle(
                    aws_region=region,
                    api_key=api_key,
                    base_url=get_bedrock_anthropic_base_url(region, settings.BEDROCK_BASE_URL),
                    max_retries=0,
                    timeout=60.0,
                )
            expires_at = None if use_sigv4 else now + _TOKEN_TTL_SECONDS
            entry = {"client": client, "expires_at": expires_at}
            _clients[kind] = entry
            logger.info(
                "Anthropic Bedrock client init: kind=%s base_url=%s auth=%s",
                kind, client.base_url, "sigv4" if use_sigv4 else "bearer",
            )
        return entry["client"]


def convert_messages(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """OpenAI-style messages -> (system, anthropic_messages)."""
    system_parts: List[str] = []
    converted: List[Dict[str, Any]] = []

    def _last_is_tool_result_msg() -> bool:
        if not converted or converted[-1]["role"] != "user":
            return False
        content = converted[-1]["content"]
        return isinstance(content, list) and all(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            if msg.get("content"):
                system_parts.append(msg["content"])
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id"),
                "content": msg.get("content") or "",
            }
            if _last_is_tool_result_msg():
                converted[-1]["content"].append(block)
            else:
                converted.append({"role": "user", "content": [block]})
            continue
        if role == "assistant":
            raw_blocks = msg.get("_anthropic_content")
            if raw_blocks:
                converted.append({"role": "assistant", "content": raw_blocks})
                continue
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                blocks: List[Dict[str, Any]] = []
                if msg.get("content"):
                    blocks.append({"type": "text", "text": msg["content"]})
                for tc in tool_calls:
                    try:
                        tc_input = json.loads(tc["function"]["arguments"] or "{}")
                    except (json.JSONDecodeError, TypeError):
                        tc_input = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": tc_input,
                    })
                converted.append({"role": "assistant", "content": blocks})
            elif msg.get("content"):
                converted.append({"role": "assistant", "content": msg["content"]})
            continue
        converted.append({"role": "user", "content": msg.get("content") or ""})

    return "\n\n".join(system_parts), converted


def convert_tools(openai_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tools: List[Dict[str, Any]] = []
    for t in openai_tools:
        fn = t.get("function", t)
        tools.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return tools


def extract_text(response: Any) -> str:
    return "".join(b.text for b in response.content if b.type == "text")


async def stream_chat(messages: List[Dict[str, Any]], model: str) -> AsyncGenerator[str, None]:
    client = get_client(model)
    system, anth_messages = convert_messages(messages)
    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": settings.BEDROCK_ANTHROPIC_MAX_TOKENS,
        "messages": anth_messages,
    }
    if system:
        kwargs["system"] = system
    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield text
        final = await stream.get_final_message()
        logger.info(
            "Bedrock Anthropic(%s) model=%s stop=%s in=%s out=%s",
            settings.BEDROCK_REGION, model, final.stop_reason,
            final.usage.input_tokens, final.usage.output_tokens,
        )


async def call_text(system: str, user_content: str, model: str, timeout: float = 30.0) -> str:
    client = get_client(model)
    resp = await client.with_options(timeout=timeout).messages.create(
        model=model,
        max_tokens=settings.BEDROCK_ANTHROPIC_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return extract_text(resp)


async def agent_completion(
    messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], model: str
) -> SimpleNamespace:
    """Non-streaming tool-decision turn; returns an OpenAI-choice-shaped object.

    choice.anthropic_content carries the raw response blocks — the caller must
    stash them as assistant_msg["_anthropic_content"] for the next turn.
    """
    client = get_client(model)
    system, anth_messages = convert_messages(messages)
    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": settings.BEDROCK_ANTHROPIC_MAX_TOKENS,
        "messages": anth_messages,
    }
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = convert_tools(tools)

    resp = await client.messages.create(**kwargs)
    logger.info(
        "Bedrock Anthropic(%s) model=%s stop=%s in=%s out=%s",
        settings.BEDROCK_REGION, model, resp.stop_reason,
        resp.usage.input_tokens, resp.usage.output_tokens,
    )
    tool_calls = [
        SimpleNamespace(
            id=b.id,
            type="function",
            function=SimpleNamespace(
                name=b.name,
                arguments=json.dumps(b.input, ensure_ascii=False, default=str),
            ),
        )
        for b in resp.content
        if b.type == "tool_use"
    ]
    if resp.stop_reason == "tool_use":
        finish_reason = "tool_calls"
    elif resp.stop_reason == "max_tokens":
        finish_reason = "length"
    else:
        finish_reason = "stop"
    text = extract_text(resp)
    return SimpleNamespace(
        finish_reason=finish_reason,
        message=SimpleNamespace(content=text or None, tool_calls=tool_calls or None),
        anthropic_content=list(resp.content),
        usage=SimpleNamespace(
            input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens
        ),
    )
