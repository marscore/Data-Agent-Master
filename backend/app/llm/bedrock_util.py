"""AWS Bedrock helpers: bedrock-mantle Bearer token provider + base-URL derivation.

bedrock-mantle is the OpenAI-compatible + native-Anthropic gateway for Bedrock.
It accepts short-lived tokens signed locally from IAM role credentials. In
"sigv4" auth mode we skip the token entirely and let boto3 / the anthropic SDK
sign requests with the default credential chain (used locally where the SSO role
lacks bedrock:CallWithBearerToken).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_token_cache: Dict[str, dict] = {}
_cache_lock = threading.Lock()
_TOKEN_TTL_SECONDS = 50 * 60  # comfortably within the ~1h STS window


def get_bedrock_token(region: str) -> str:
    now = time.time()
    with _cache_lock:
        entry = _token_cache.get(region)
        if entry and now < entry["expires_at"]:
            return entry["token"]
        try:
            from aws_bedrock_token_generator import provide_token  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "aws-bedrock-token-generator not installed (pip install aws-bedrock-token-generator)"
            ) from exc
        try:
            token = provide_token(region=region)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"Failed to generate Bedrock token for region={region}. "
                f"Ensure AWS credentials are available. Original error: {exc}"
            ) from exc
        _token_cache[region] = {"token": token, "expires_at": now + _TOKEN_TTL_SECONDS}
        logger.debug("Bedrock token refreshed for region=%s (len=%d)", region, len(token))
        return token


def get_bedrock_base_url(region: str, override: str = "") -> str:
    if override:
        return override.rstrip("/")
    return f"https://bedrock-mantle.{region}.api.aws/v1"


def get_bedrock_anthropic_base_url(region: str, override: str = "") -> str:
    """Native Anthropic Messages API base (mantle serves it at /anthropic)."""
    if override:
        base = override.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        return f"{base}/anthropic"
    return f"https://bedrock-mantle.{region}.api.aws/anthropic"


def invalidate_token_cache(region: Optional[str] = None) -> None:
    with _cache_lock:
        if region is None:
            _token_cache.clear()
        else:
            _token_cache.pop(region, None)
