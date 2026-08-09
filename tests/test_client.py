from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from uptime_kuma_mcp.client import KumaClient, KumaError
from uptime_kuma_mcp.compatibility import READ_ONLY_TOOLS


@pytest.mark.asyncio
async def test_event_cache_is_sanitized_at_ingress(settings) -> None:
    client = KumaClient(settings)
    await client._on_monitor_list(
        {
            "1": {
                "id": 1,
                "name": "API",
                "url": "https://example.test/health?token=secret",
                "headers": {"Authorization": "Bearer secret"},
                "basic_auth_pass": "secret",
            }
        }
    )
    await client._on_notification_list(
        [
            {
                "id": 2,
                "name": "Webhook",
                "config": '{"type":"webhook","webhookURL":"https://secret"}',
            }
        ]
    )
    assert "headers" not in client.monitors["1"]
    assert "basic_auth_pass" not in client.monitors["1"]
    assert "secret" not in str(client.monitors)
    assert client.notifications[0]["type"] == "webhook"
    assert "config" not in client.notifications[0]


@pytest.mark.asyncio
async def test_unowned_monitor_is_rejected_before_weak_kuma_read_event(settings) -> None:
    client = KumaClient(settings)
    client.monitors = {"1": {"id": 1, "name": "Owned"}}
    client.ensure_operational = AsyncMock()  # type: ignore[method-assign]
    client._call = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(KumaError, match="not found for the authenticated user") as caught:
        await client.get_heartbeats(999, 24)
    assert caught.value.code == "monitor_not_found"
    client._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_version_fails_closed(settings) -> None:
    client = KumaClient(settings)
    client.version = "2.6.0"
    client.connected = True
    client.authenticated = True
    client._socket.connected = True
    client._ensure_session = AsyncMock()  # type: ignore[method-assign]
    with pytest.raises(KumaError, match="expected 2.5.0") as caught:
        await client.ensure_operational()
    assert caught.value.code == "unsupported_version"


@pytest.mark.asyncio
async def test_instance_info_reports_only_currently_enabled_capabilities(settings) -> None:
    client = KumaClient(settings)
    client._ensure_session = AsyncMock()  # type: ignore[method-assign]

    disconnected = await client.instance_info()
    assert disconnected["capabilities"] == []

    client.connected = True
    client.authenticated = True
    client.version = "2.5.0"
    operational = await client.instance_info()
    assert operational["capabilities"] == list(READ_ONLY_TOOLS)


@pytest.mark.asyncio
async def test_heartbeat_request_is_rejected_before_unbounded_upstream_read(settings) -> None:
    client = KumaClient(settings)
    client.monitors = {"1": {"id": 1, "interval": 1, "retryInterval": 1}}
    client.ensure_operational = AsyncMock()  # type: ignore[method-assign]
    client._call = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(KumaError, match="row safety budget") as caught:
        await client.get_heartbeats(1, 24)

    assert caught.value.code == "heartbeat_budget_exceeded"
    client._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_response_over_hard_row_budget_is_rejected(settings) -> None:
    client = KumaClient(settings)
    client.monitors = {"1": {"id": 1, "interval": 3600, "retryInterval": 3600}}
    client.ensure_operational = AsyncMock()  # type: ignore[method-assign]
    client._call = AsyncMock(return_value={"ok": True, "data": [{}] * 10_001})  # type: ignore[method-assign]

    with pytest.raises(KumaError, match="row safety budget") as caught:
        await client.get_heartbeats(1, 24)

    assert caught.value.code == "heartbeat_budget_exceeded"
