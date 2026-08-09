from __future__ import annotations

from typing import Any

import pytest

from uptime_kuma_mcp.service import KumaService


@pytest.mark.asyncio
async def test_monitor_summary_and_filters(fake_client: Any) -> None:
    service = KumaService(fake_client)
    summary = await service.monitor_summary()
    assert summary["data"] == {
        "monitor_count": 2,
        "active": 1,
        "inactive": 1,
        "status_counts": {
            "down": 0,
            "up": 1,
            "pending": 0,
            "maintenance": 0,
            "unknown": 1,
        },
    }

    monitors = await service.list_monitors(
        active=True,
        monitor_type="http",
        status=1,
        query="alpha",
        offset=0,
        limit=10,
    )
    assert [item["id"] for item in monitors["data"]] == [1]
    assert monitors["data"][0]["latestHeartbeat"]["status"] == 1
    assert monitors["meta"]["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_pagination_and_newest_first_heartbeats(fake_client: Any) -> None:
    fake_client.snapshot["heartbeats"]["1"] = [
        {"id": 1, "monitor_id": 1, "status": 0, "time": "2026-08-08 10:00:00"},
        {"id": 2, "monitor_id": 1, "status": 1, "time": "2026-08-08 12:00:00"},
    ]
    result = await KumaService(fake_client).get_heartbeats(1, 24, 0, 1)
    assert result["data"][0]["id"] == 2
    assert result["meta"]["pagination"] == {
        "offset": 0,
        "limit": 1,
        "returned": 1,
        "total": 2,
        "has_more": True,
    }


@pytest.mark.asyncio
async def test_inventory_reads_are_deterministic(fake_client: Any) -> None:
    service = KumaService(fake_client)
    assert (await service.list_tags(0, 100))["data"][0]["name"] == "prod"
    assert (await service.list_maintenance(0, 100))["data"][0]["id"] == 7
    assert (await service.list_status_pages(0, 100))["data"][0]["slug"] == "public"
    notifications = await service.list_notifications(0, 100)
    assert notifications["data"] == [
        {"id": 4, "name": "Ops Slack", "type": "slack", "active": True}
    ]
