from __future__ import annotations

import sys
from typing import Any

import jwt
import pytest

from uptime_kuma_mcp import cli


class FakeMCP:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    def run(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def test_cli_issues_scoped_token(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    secret = "q" * 32
    monkeypatch.setenv("MCP_JWT_SECRET", secret)
    monkeypatch.setenv("MCP_JWT_ISSUER", "issuer")
    monkeypatch.setenv("MCP_JWT_AUDIENCE", "audience")
    monkeypatch.setattr(sys, "argv", ["uptime-kuma-mcp", "issue-token", "--subject", "pedro"])
    cli.main()
    token = capsys.readouterr().out.strip()
    claims = jwt.decode(token, secret, algorithms=["HS256"], audience="audience", issuer="issuer")
    assert claims["sub"] == "pedro"
    assert claims["scope"] == "read:kuma"


def test_cli_runs_streamable_http(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMCP()
    monkeypatch.setattr(cli, "build_mcp", lambda _settings: fake)
    monkeypatch.setattr(sys, "argv", ["uptime-kuma-mcp", "run"])
    for key, value in {
        "KUMA_URL": "http://kuma:3001",
        "KUMA_USERNAME": "reader",
        "KUMA_PASSWORD": "password",
        "MCP_JWT_SECRET": "q" * 32,
        "MCP_JWT_ISSUER": "issuer",
        "MCP_JWT_AUDIENCE": "audience",
    }.items():
        monkeypatch.setenv(key, value)
    cli.main()
    assert fake.kwargs is not None
    assert fake.kwargs["transport"] == "http"
    assert fake.kwargs["path"] == "/mcp"
    assert fake.kwargs["host_origin_protection"] is True


def test_cli_configuration_error_is_safe(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("MCP_JWT_SECRET", raising=False)
    monkeypatch.setattr(sys, "argv", ["uptime-kuma-mcp", "issue-token"])
    with pytest.raises(SystemExit) as caught:
        cli.main()
    assert caught.value.code == 2
    assert "MCP_JWT_SECRET" in capsys.readouterr().err
