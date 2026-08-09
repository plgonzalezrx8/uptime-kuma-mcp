"""Environment-backed configuration with fail-closed validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


class ConfigError(ValueError):
    """Configuration is missing or unsafe."""


def _required(env: dict[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigError(f"{key} is required")
    return value


def _boolean(env: dict[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be true or false")


def _integer(env: dict[str, str], key: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = env.get(key, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{key} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated server and Kuma connection settings."""

    kuma_url: str
    kuma_username: str | None
    kuma_password: str | None
    kuma_jwt: str | None
    kuma_2fa_token: str | None
    kuma_tls_verify: bool
    kuma_connect_timeout: int
    kuma_request_timeout: int
    mcp_jwt_secret: str
    mcp_jwt_issuer: str
    mcp_jwt_audience: str
    mcp_host: str
    mcp_port: int
    mcp_allowed_hosts: tuple[str, ...]

    @property
    def kuma_auth_mode(self) -> str:
        return "jwt" if self.kuma_jwt else "password"

    @classmethod
    def from_env(cls, source: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ if source is None else source)
        kuma_url = _required(env, "KUMA_URL").rstrip("/")
        parsed = urlsplit(kuma_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigError("KUMA_URL must be an absolute http or https URL")
        if parsed.username or parsed.password:
            raise ConfigError("KUMA_URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ConfigError("KUMA_URL must not contain a query string or fragment")

        kuma_jwt = env.get("KUMA_JWT", "").strip() or None
        username = env.get("KUMA_USERNAME", "").strip() or None
        password = env.get("KUMA_PASSWORD", "") or None
        twofa = env.get("KUMA_2FA_TOKEN", "").strip() or None
        if kuma_jwt and (username or password or twofa):
            raise ConfigError("KUMA_JWT cannot be combined with password authentication")
        if not kuma_jwt and not (username and password):
            raise ConfigError("set KUMA_JWT or both KUMA_USERNAME and KUMA_PASSWORD")
        if bool(username) != bool(password):
            raise ConfigError("KUMA_USERNAME and KUMA_PASSWORD must be set together")

        secret = _required(env, "MCP_JWT_SECRET")
        if len(secret.encode()) < 32:
            raise ConfigError("MCP_JWT_SECRET must be at least 32 bytes")

        allowed_hosts_raw = env.get("MCP_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
        allowed_hosts = tuple(item.strip() for item in allowed_hosts_raw.split(",") if item.strip())
        if not allowed_hosts:
            raise ConfigError("MCP_ALLOWED_HOSTS must contain at least one host")

        return cls(
            kuma_url=kuma_url,
            kuma_username=username,
            kuma_password=password,
            kuma_jwt=kuma_jwt,
            kuma_2fa_token=twofa,
            kuma_tls_verify=_boolean(env, "KUMA_TLS_VERIFY", True),
            kuma_connect_timeout=_integer(env, "KUMA_CONNECT_TIMEOUT", 10, minimum=1, maximum=120),
            kuma_request_timeout=_integer(env, "KUMA_REQUEST_TIMEOUT", 15, minimum=1, maximum=120),
            mcp_jwt_secret=secret,
            mcp_jwt_issuer=_required(env, "MCP_JWT_ISSUER"),
            mcp_jwt_audience=_required(env, "MCP_JWT_AUDIENCE"),
            mcp_host=env.get("MCP_HOST", "127.0.0.1").strip() or "127.0.0.1",
            mcp_port=_integer(env, "MCP_PORT", 8000, minimum=1, maximum=65535),
            mcp_allowed_hosts=allowed_hosts,
        )
