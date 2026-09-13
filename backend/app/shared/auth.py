"""Identity: validate the platform JWT (HS256 local dev) and pass the raw token
through to MCP servers. The platform makes no authz decision — the target
system's ACL is the boundary. In ALLOW_ANONYMOUS mode a dev principal is used
when no token is supplied (local only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Header, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    sub: str
    access_token: Optional[str]   # raw JWT, forwarded verbatim to MCP servers


def _decode_sub(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(
            token, settings.PLATFORM_JWT_SECRET, algorithms=[settings.PLATFORM_JWT_ALG],
            options={"verify_aud": False},
        )
        return payload.get("sub") or payload.get("user") or payload.get("email")
    except Exception as e:  # noqa: BLE001
        logger.debug("JWT decode failed: %s", e)
        return None


async def get_principal(authorization: Optional[str] = Header(None)) -> Principal:
    token: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip() or None

    if token:
        sub = _decode_sub(token)
        if sub is None and not settings.ALLOW_ANONYMOUS:
            raise HTTPException(status_code=401, detail="invalid token")
        # Forward the raw token to MCP regardless of local verification result;
        # the MCP target validates it. sub is best-effort for tracing.
        return Principal(sub=sub or settings.DEV_PRINCIPAL_SUB, access_token=token)

    if settings.ALLOW_ANONYMOUS:
        return Principal(sub=settings.DEV_PRINCIPAL_SUB, access_token=None)
    raise HTTPException(status_code=401, detail="missing bearer token")
