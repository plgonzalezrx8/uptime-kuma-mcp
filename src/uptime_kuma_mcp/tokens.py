"""Minimal HS256 token issuer for this MCP resource server."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_token(
    *,
    secret: str,
    issuer: str,
    audience: str,
    subject: str,
    ttl_seconds: int,
    now: int | None = None,
) -> str:
    """Issue a scoped HS256 JWT without exposing the signing secret."""
    if len(secret.encode()) < 32:
        raise ValueError("signing secret must be at least 32 bytes")
    if not subject.strip():
        raise ValueError("subject must not be empty")
    if not 60 <= ttl_seconds <= 31_536_000:
        raise ValueError("ttl_seconds must be between 60 and 31536000")
    issued_at = int(time.time()) if now is None else now
    header: dict[str, Any] = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "client_id": subject,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + ttl_seconds,
        "jti": secrets.token_hex(16),
        "scope": "read:kuma",
        "scopes": ["read:kuma"],
    }
    encoded_header = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"
