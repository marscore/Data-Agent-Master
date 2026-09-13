"""OpenAI-compatible client factory (DashScope / vLLM / OpenAI / Bedrock gateway).

Kept separate from the Bedrock-Anthropic adapter so the dispatch layer can pick
per model. base_url may point at any /v1 endpoint. In bearer-token Bedrock mode
the gateway token can be injected here too, but the common local path is a plain
OpenAI-compatible server with a static API key.
"""

from __future__ import annotations

import threading
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings

_client: Optional[AsyncOpenAI] = None
_lock = threading.Lock()


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                base_url = settings.OPENAI_BASE_URL or None
                api_key = settings.OPENAI_API_KEY or "sk-noauth"
                _client = AsyncOpenAI(base_url=base_url, api_key=api_key, max_retries=0, timeout=60.0)
    return _client
