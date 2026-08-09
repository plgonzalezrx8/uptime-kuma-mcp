from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastmcp.client import Client

from uptime_kuma_mcp.compatibility import READ_ONLY_TOOLS
from uptime_kuma_mcp.server import build_mcp
from uptime_kuma_mcp.tokens import issue_token


@pytest.mark.asyncio
async def test_in_memory_mcp_exposes_only_approved_read_tools(settings, fake_client: Any) -> None:
    mcp = build_mcp(settings, client=fake_client)  # type: ignore[arg-type]
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == set(READ_ONLY_TOOLS)
        assert not any(
            word in tool.name
            for tool in tools
            for word in ("create", "update", "delete", "pause", "resume")
        )
        result = await client.call_tool("kuma_list_monitors", {"limit": 1})
        assert result.data["ok"] is True
        assert result.data["meta"]["pagination"]["returned"] == 1
    assert fake_client.started is True
    assert fake_client.stopped is True


@pytest.mark.asyncio
async def test_diagnostic_tool_survives_unsupported_version(settings, fake_client: Any) -> None:
    fake_client.version = "2.6.0"
    mcp = build_mcp(settings, client=fake_client)  # type: ignore[arg-type]
    async with Client(mcp) as client:
        diagnostic = await client.call_tool("kuma_get_instance_info")
        assert diagnostic.data["data"]["supported"] is False
        blocked = await client.call_tool("kuma_list_monitors", {"limit": 1}, raise_on_error=False)
        assert blocked.is_error is True
        assert "unsupported_version" in str(blocked.content[0])


@pytest.mark.asyncio
async def test_streamable_http_requires_valid_bearer_token(settings, fake_client: Any) -> None:
    mcp = build_mcp(settings, client=fake_client)  # type: ignore[arg-type]
    app = mcp.http_app(path="/mcp")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }
    headers = {"accept": "application/json, text/event-stream"}
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            missing = await client.post("/mcp", json=request, headers=headers)
            invalid = await client.post(
                "/mcp", json=request, headers={**headers, "authorization": "Bearer invalid"}
            )
            token = issue_token(
                secret=settings.mcp_jwt_secret,
                issuer=settings.mcp_jwt_issuer,
                audience=settings.mcp_jwt_audience,
                subject="pytest",
                ttl_seconds=3600,
            )
            valid = await client.post(
                "/mcp", json=request, headers={**headers, "authorization": f"Bearer {token}"}
            )
    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200
