from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from uptime_kuma_mcp.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env(
        {
            "KUMA_URL": "http://kuma.test:3001",
            "KUMA_USERNAME": "reader",
            "KUMA_PASSWORD": "test-password",
            "MCP_JWT_SECRET": "x" * 32,
            "MCP_JWT_ISSUER": "uptime-kuma-mcp-test",
            "MCP_JWT_AUDIENCE": "uptime-kuma-mcp-test",
        }
    )


class FakeKumaClient:
    def __init__(self, version: str = "2.5.0") -> None:
        self.version = version
        self.observed_at = "2026-08-08T12:00:00+00:00"
        self.started = False
        self.stopped = False
        self.snapshot: dict[str, Any] = {
            "monitors": {
                "1": {
                    "id": 1,
                    "name": "Alpha API",
                    "type": "http",
                    "active": True,
                    "url": "https://api.example.test/health",
                },
                "2": {
                    "id": 2,
                    "name": "Beta DNS",
                    "type": "dns",
                    "active": False,
                    "hostname": "dns.example.test",
                },
            },
            "heartbeats": {
                "1": [
                    {
                        "id": 10,
                        "monitor_id": 1,
                        "status": 1,
                        "time": "2026-08-08 11:59:00",
                        "msg": "200 - OK",
                        "ping": 12.3,
                    }
                ],
                "2": [],
            },
            "avg_ping": {"1": 12.3},
            "uptime": {"1": {"24": 0.999}},
            "maintenance": {"7": {"id": 7, "title": "Patch window", "active": True}},
            "status_pages": {
                "1": {"id": 1, "title": "Public", "slug": "public", "published": True}
            },
            "notifications": [{"id": 4, "name": "Ops Slack", "type": "slack", "active": True}],
            "observed_at": self.observed_at,
        }

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "ready": self.version == "2.5.0"}

    async def instance_info(self) -> dict[str, Any]:
        return {
            "connected": True,
            "authenticated": True,
            "kuma_version": self.version,
            "supported": self.version == "2.5.0",
            "supported_version": "2.5.0",
            "server_timezone": "America/New_York",
            "auth_mode": "password",
            "capabilities": [],
            "last_error_code": None if self.version == "2.5.0" else "unsupported_version",
            "observed_at": self.observed_at,
        }

    def _supported(self) -> None:
        from uptime_kuma_mcp.client import KumaError

        if self.version != "2.5.0":
            raise KumaError("unsupported_version", "unsupported test version")

    async def refresh_monitors(self) -> dict[str, dict[str, Any]]:
        self._supported()
        return deepcopy(self.snapshot["monitors"])

    async def operational_snapshot(self) -> dict[str, Any]:
        self._supported()
        return deepcopy(self.snapshot)

    async def get_monitor(self, monitor_id: int) -> dict[str, Any]:
        self._supported()
        return deepcopy(self.snapshot["monitors"][str(monitor_id)])

    async def get_heartbeats(self, monitor_id: int, _period_hours: int) -> list[dict[str, Any]]:
        self._supported()
        return deepcopy(self.snapshot["heartbeats"][str(monitor_id)])

    async def get_chart_data(self, monitor_id: int, period_hours: int) -> Any:
        self._supported()
        return [{"monitor_id": monitor_id, "period_hours": period_hours, "uptime": 0.999}]

    async def get_tags(self) -> list[dict[str, Any]]:
        self._supported()
        return [{"id": 2, "name": "prod", "color": "#00ff00"}]

    async def refresh_maintenance(self) -> dict[str, dict[str, Any]]:
        self._supported()
        return deepcopy(self.snapshot["maintenance"])


@pytest.fixture
def fake_client() -> FakeKumaClient:
    return FakeKumaClient()
