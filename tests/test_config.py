from __future__ import annotations

import pytest

from uptime_kuma_mcp.config import ConfigError, Settings

BASE = {
    "KUMA_URL": "https://kuma.example.test",
    "KUMA_USERNAME": "reader",
    "KUMA_PASSWORD": "password",
    "MCP_JWT_SECRET": "s" * 32,
    "MCP_JWT_ISSUER": "issuer",
    "MCP_JWT_AUDIENCE": "audience",
}


def test_password_configuration_is_valid() -> None:
    settings = Settings.from_env(BASE)
    assert settings.kuma_auth_mode == "password"
    assert settings.kuma_tls_verify is True
    assert settings.mcp_host == "127.0.0.1"


def test_kuma_token_configuration_is_valid() -> None:
    env = {**BASE, "KUMA_JWT": "kuma-token"}
    env.pop("KUMA_USERNAME")
    env.pop("KUMA_PASSWORD")
    assert Settings.from_env(env).kuma_auth_mode == "jwt"


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"MCP_JWT_SECRET": "short"}, "at least 32 bytes"),
        ({"KUMA_URL": "ftp://bad.example"}, "absolute http or https"),
        ({"KUMA_URL": "https://user:pass@kuma.example"}, "must not contain credentials"),
        ({"KUMA_URL": "https://kuma.example?x=1"}, "query string or fragment"),
        ({"KUMA_JWT": "token"}, "cannot be combined"),
        ({"KUMA_USERNAME": ""}, "set KUMA_JWT"),
        ({"KUMA_PASSWORD": ""}, "set KUMA_JWT"),
        ({"KUMA_TLS_VERIFY": "perhaps"}, "must be true or false"),
        ({"KUMA_REQUEST_TIMEOUT": "zero"}, "must be an integer"),
        ({"KUMA_REQUEST_TIMEOUT": "0"}, "between 1 and 120"),
        ({"MCP_ALLOWED_HOSTS": ","}, "at least one host"),
    ],
)
def test_unsafe_configuration_fails_closed(updates: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Settings.from_env({**BASE, **updates})
