"""
Aegis — API Security & Authentication Middleware

Provides API key and Bearer token verification dependencies to protect
administrative, self-healing, and source management endpoints.
"""

from __future__ import annotations

import hmac
from core.config.settings import get_settings
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer

settings = get_settings()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def verify_api_key(
    api_key: str | None = Security(api_key_header),
) -> str:
    """
    Validate inbound X-API-Key header against configured API secret key.
    If no secret key is set (e.g. development mode), passes through.
    """
    expected_key = getattr(settings, "api_secret_key", None) or "aegis-dev-secret-key"

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-API-Key header",
        )

    # Timing-safe string comparison to prevent side-channel timing attacks
    if not hmac.compare_digest(api_key.encode("utf-8"), expected_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    return api_key
