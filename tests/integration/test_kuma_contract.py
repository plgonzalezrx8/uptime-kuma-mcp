from __future__ import annotations

import asyncio
import os

import pytest

from uptime_kuma_mcp.client import KumaClient
from uptime_kuma_mcp.compatibility import SUPPORTED_KUMA_VERSION
from uptime_kuma_mcp.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_KUMA_CONTRACT") != "1",
        reason="set RUN_KUMA_CONTRACT=1 for the disposable Kuma contract",
    ),
]


@pytest.mark.asyncio
async def test_exact_kuma_socket_contract() -> None:
    settings = Settings.from_env()
    client = KumaClient(settings)
    await client.start()
    try:
        info = await client.instance_info()
        assert info["connected"] is True
        assert info["authenticated"] is True
        assert info["kuma_version"] == SUPPORTED_KUMA_VERSION
        assert info["supported"] is True

        monitors = await client.refresh_monitors()
        assert monitors, "the disposable fixture must contain a monitor"
        monitor_id = int(next(iter(monitors)))
        monitor_key = str(monitor_id)
        assert monitor_key in client.heartbeats, (
            "login readiness must include the monitor's initial heartbeatList"
        )
        monitor = await client.get_monitor(monitor_id)
        assert monitor["id"] == monitor_id
        assert "password" not in monitor
        assert "headers" not in monitor

        beats = await client.get_heartbeats(monitor_id, 24)
        assert isinstance(beats, list)
        chart = await client.get_chart_data(monitor_id, 24)
        assert isinstance(chart, list)
        tags = await client.get_tags()
        assert isinstance(tags, list)
        maintenance = await client.refresh_maintenance()
        assert isinstance(maintenance, dict)

        initial_heartbeat_ids = {
            heartbeat.get("id") for heartbeat in client.heartbeats.get(monitor_key, [])
        }
        current_heartbeat_ids = initial_heartbeat_ids
        for _ in range(35):
            current_heartbeat_ids = {
                heartbeat.get("id") for heartbeat in client.heartbeats.get(monitor_key, [])
            }
            if current_heartbeat_ids - initial_heartbeat_ids:
                break
            await asyncio.sleep(1)
        assert current_heartbeat_ids - initial_heartbeat_ids, (
            "the live heartbeat event must advance the post-login cache"
        )

        snapshot = await client.operational_snapshot()
        assert isinstance(snapshot["status_pages"], dict)
        assert isinstance(snapshot["notifications"], list)
    finally:
        await client.stop()
