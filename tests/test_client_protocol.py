from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from uptime_kuma_mcp.client import KumaClient, KumaError


@pytest.mark.asyncio
async def test_all_cache_handlers_and_health_states(settings) -> None:
    client = KumaClient(settings)
    await client._on_connect()
    assert client.connected
    await client._on_info({"version": "2.5.0", "serverTimezone": "UTC"})
    await client._on_info({"serverTimezone": "America/New_York"})
    await client._on_info("ignored")
    assert client.version == "2.5.0"
    assert client.server_timezone == "America/New_York"

    await client._on_monitor_list({"1": {"id": 1, "name": "One", "active": True}})
    await client._on_monitor_update({"1": {"id": 1, "name": "Updated"}})
    await client._on_heartbeat_list(
        1, [{"id": 1, "status": 1, "time": "2026-01-01", "msg": "ok"}], True
    )
    await client._on_heartbeat_list(
        1, [{"id": 2, "status": 0, "time": "2026-01-02", "msg": "down"}], False
    )
    await client._on_heartbeat_list(2, "invalid", False)
    await client._on_avg_ping(1, 12)
    await client._on_avg_ping(2, "unknown")
    await client._on_uptime(1, 24, 0.99)
    await client._on_uptime(2, 24, None)
    await client._on_maintenance_list({"7": {"id": 7, "title": "Window"}})
    await client._on_status_page_list({"3": {"id": 3, "title": "Status", "slug": "s"}})
    await client._on_notification_list("invalid")
    await client._on_notification_list([{"id": 5, "name": "Slack", "config": {"type": "slack"}}])

    assert client.monitors["1"]["name"] == "Updated"
    assert [item["id"] for item in client.heartbeats["1"]] == [2, 1]
    assert client.avg_ping == {"1": 12.0, "2": None}
    assert client.uptime["1"]["24"] == 0.99
    client.authenticated = True
    assert client.health() == {"status": "ok", "ready": True}

    await client._on_monitor_delete(1)
    assert "1" not in client.monitors
    await client._on_connect_error(None)
    assert client.last_error_code == "connection_failed"
    await client._on_disconnect("transport close")
    assert not client.connected and not client.authenticated


@pytest.mark.asyncio
async def test_live_heartbeat_event_retains_the_newest_100_rows(settings) -> None:
    client = KumaClient(settings)
    assert "heartbeat" in client._socket.handlers["/"]

    await client._on_heartbeat_list(
        1,
        [
            {
                "id": heartbeat_id,
                "monitorID": 1,
                "status": 1,
                "time": f"2026-01-01T00:{heartbeat_id:02}:00Z",
            }
            for heartbeat_id in range(1, 101)
        ],
        True,
    )
    await client._on_heartbeat(
        {
            "id": 101,
            "monitorID": 1,
            "status": 0,
            "time": "2026-01-01T02:00:00Z",
            "msg": "token=secret",
        }
    )

    assert [row["id"] for row in client.heartbeats["1"]] == list(range(2, 102))
    assert client.heartbeats["1"][-1]["msg"] == "token=[REDACTED]"


class LoginSocket:
    def __init__(self, owner: KumaClient, response: object) -> None:
        self.owner = owner
        self.response = response
        self.connected = False
        self.events: list[tuple[str, object]] = []

    async def connect(self, *_args: object, **_kwargs: object) -> None:
        self.connected = True
        await self.owner._on_connect()
        await self.owner._on_info({"serverTimezone": "UTC"})

    async def call(self, event: str, data: object = None, **_kwargs: object) -> object:
        self.events.append((event, data))
        if event in {"login", "loginByToken"} and isinstance(self.response, dict):
            if self.response.get("ok") is True:
                await self.owner._on_info({"version": "2.5.0", "serverTimezone": "UTC"})
                await self.owner._on_monitor_list({})
                await self.owner._on_maintenance_list({})
                await self.owner._on_notification_list([])
                await self.owner._on_status_page_list({})
        return self.response

    async def disconnect(self) -> None:
        self.connected = False


class DelayedInitialStateSocket(LoginSocket):
    def __init__(self, owner: KumaClient) -> None:
        super().__init__(owner, {"ok": True})
        self.release_initial_state = asyncio.Event()
        self.delivery_task: asyncio.Task[None] | None = None

    async def call(self, event: str, data: object = None, **_kwargs: object) -> object:
        self.events.append((event, data))
        if event in {"login", "loginByToken"}:
            await self.owner._on_info({"version": "2.5.0", "serverTimezone": "UTC"})
            await self.owner._on_monitor_list({})

            async def deliver_remaining_state() -> None:
                await self.release_initial_state.wait()
                await self.owner._on_maintenance_list({})
                await self.owner._on_notification_list([])
                await self.owner._on_status_page_list({})

            self.delivery_task = asyncio.create_task(deliver_remaining_state())
        return self.response


class DelayedHeartbeatSocket(LoginSocket):
    def __init__(self, owner: KumaClient) -> None:
        super().__init__(owner, {"ok": True})
        self.release_heartbeat = asyncio.Event()
        self.delivery_task: asyncio.Task[None] | None = None

    async def call(self, event: str, data: object = None, **_kwargs: object) -> object:
        self.events.append((event, data))
        if event in {"login", "loginByToken"}:
            await self.owner._on_info({"version": "2.5.0", "serverTimezone": "UTC"})
            await self.owner._on_monitor_list({"1": {"id": 1, "name": "One"}})
            await self.owner._on_maintenance_list({})
            await self.owner._on_notification_list([])
            await self.owner._on_status_page_list({})

            async def deliver_heartbeat() -> None:
                await self.release_heartbeat.wait()
                await self.owner._on_heartbeat_list(1, [], True)

            self.delivery_task = asyncio.create_task(deliver_heartbeat())
        return self.response


class DisconnectDuringLoginSocket(LoginSocket):
    def __init__(self, owner: KumaClient) -> None:
        super().__init__(owner, {"ok": True, "token": "issued-session-jwt"})
        self.disconnect_during_login = True
        self.fail_next_connect = False

    async def connect(self, *args: object, **kwargs: object) -> None:
        if self.fail_next_connect:
            self.fail_next_connect = False
            self.connected = False
            raise OSError("connection unavailable")
        await super().connect(*args, **kwargs)

    async def call(self, event: str, data: object = None, **kwargs: object) -> object:
        response = await super().call(event, data, **kwargs)
        if event in {"login", "loginByToken"} and self.disconnect_during_login:
            self.disconnect_during_login = False
            self.connected = False
            await self.owner._on_disconnect()
        return response


class VersionlessReconnectSocket(LoginSocket):
    def __init__(self, owner: KumaClient) -> None:
        super().__init__(owner, {"ok": True, "token": "issued-session-jwt"})
        self.login_count = 0

    async def call(self, event: str, data: object = None, **kwargs: object) -> object:
        if event not in {"login", "loginByToken"}:
            return await super().call(event, data, **kwargs)
        self.login_count += 1
        if self.login_count == 1:
            return await super().call(event, data, **kwargs)

        self.events.append((event, data))
        await self.owner._on_info({"serverTimezone": "UTC"})
        await self.owner._on_monitor_list({})
        await self.owner._on_maintenance_list({})
        await self.owner._on_notification_list([])
        await self.owner._on_status_page_list({})
        return self.response


@pytest.mark.asyncio
async def test_password_login_connects_and_populates_compatibility(settings) -> None:
    client = KumaClient(settings)
    socket = LoginSocket(client, {"ok": True})
    client._socket = socket  # type: ignore[assignment]
    await client._ensure_session()
    assert client.authenticated
    assert client.version == "2.5.0"
    assert client._socket_ready_event.is_set()
    assert socket.events[0][0] == "login"
    assert socket.events[0][1] == {"username": "reader", "password": "test-password"}
    await client.stop()
    assert socket.connected is False


@pytest.mark.asyncio
async def test_login_waits_for_all_initial_read_caches(settings) -> None:
    client = KumaClient(settings)
    socket = DelayedInitialStateSocket(client)
    client._socket = socket  # type: ignore[assignment]

    login_task = asyncio.create_task(client._ensure_session())
    await asyncio.sleep(0.01)
    completed_before_initial_state = login_task.done()
    socket.release_initial_state.set()
    await login_task
    if socket.delivery_task is not None:
        await socket.delivery_task

    assert completed_before_initial_state is False


@pytest.mark.asyncio
async def test_login_waits_for_each_monitors_initial_heartbeat_list(settings) -> None:
    client = KumaClient(settings)
    client.heartbeats = {"1": [{"id": "stale"}]}
    socket = DelayedHeartbeatSocket(client)
    client._socket = socket  # type: ignore[assignment]

    login_task = asyncio.create_task(client._ensure_session())
    await asyncio.sleep(0.01)

    assert login_task.done() is False
    assert client.authenticated is False
    assert client.heartbeats == {}

    socket.release_heartbeat.set()
    await login_task
    if socket.delivery_task is not None:
        await socket.delivery_task

    assert client.authenticated is True
    assert client.heartbeats == {"1": []}


@pytest.mark.asyncio
async def test_kuma_jwt_login_path(settings) -> None:
    token_settings = replace(settings, kuma_username=None, kuma_password=None, kuma_jwt="jwt")
    client = KumaClient(token_settings)
    socket = LoginSocket(client, {"ok": True})
    client._socket = socket  # type: ignore[assignment]
    await client._ensure_session()
    assert socket.events[0] == ("loginByToken", "jwt")


@pytest.mark.asyncio
async def test_2fa_password_login_reuses_issued_session_jwt_on_reconnect(settings) -> None:
    test_totp = "123456"
    token_settings = replace(settings, kuma_2fa_token=test_totp)
    client = KumaClient(token_settings)
    socket = LoginSocket(client, {"ok": True, "token": "issued-session-jwt"})
    client._socket = socket  # type: ignore[assignment]

    await client._ensure_session()
    assert socket.events[0] == (
        "login",
        {"username": "reader", "password": "test-password", "token": test_totp},
    )

    await client._on_disconnect()
    socket.connected = False
    await client._ensure_session()

    assert socket.events[-1] == ("loginByToken", "issued-session-jwt")
    assert [event for event, _data in socket.events] == ["login", "loginByToken"]


@pytest.mark.asyncio
async def test_disconnect_before_login_completion_fails_closed_and_reauthenticates(
    settings,
) -> None:
    client = KumaClient(settings)
    client.status_pages = {"cached": {"id": "cached", "title": "stale"}}
    socket = DisconnectDuringLoginSocket(client)
    client._socket = socket  # type: ignore[assignment]

    with pytest.raises(KumaError) as login_error:
        await client._ensure_session()

    assert login_error.value.code == "connection_lost"
    assert client.connected is False
    assert client.authenticated is False

    socket.fail_next_connect = True
    with pytest.raises(KumaError) as snapshot_error:
        await client.operational_snapshot()

    assert snapshot_error.value.code == "connection_failed"
    assert client.authenticated is False

    await client._ensure_session()

    assert client.connected is True
    assert client.authenticated is True
    assert socket.events == [
        (
            "login",
            {"username": "reader", "password": "test-password"},
        ),
        ("loginByToken", "issued-session-jwt"),
    ]


@pytest.mark.asyncio
async def test_operational_snapshot_rejects_stale_disconnected_state(settings) -> None:
    client = KumaClient(settings)
    client.version = "2.5.0"
    client.connected = False
    client.authenticated = True
    client.status_pages = {"cached": {"id": "cached", "title": "stale"}}
    client._socket.connected = True
    client._ensure_session = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(KumaError) as caught:
        await client.operational_snapshot()

    assert caught.value.code == "connection_lost"
    assert client.authenticated is False


@pytest.mark.asyncio
async def test_reconnect_cannot_reuse_stale_supported_version(settings) -> None:
    client = KumaClient(settings)
    socket = VersionlessReconnectSocket(client)
    client._socket = socket  # type: ignore[assignment]

    await client.ensure_operational()
    assert client.version == "2.5.0"

    await client._on_disconnect()
    socket.connected = False

    with pytest.raises(KumaError) as caught:
        await client.ensure_operational()

    assert caught.value.code == "version_unknown"
    assert client.version is None
    assert socket.events == [
        ("login", {"username": "reader", "password": "test-password"}),
        ("loginByToken", "issued-session-jwt"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "code"),
    [
        (None, "invalid_response"),
        ({"tokenRequired": True}, "two_factor_required"),
        ({"ok": False, "msg": "bad"}, "authentication_failed"),
    ],
)
async def test_login_response_failures_are_categorized(
    settings, response: object, code: str
) -> None:
    client = KumaClient(settings)
    client._socket = LoginSocket(client, response)  # type: ignore[assignment]
    with pytest.raises(KumaError) as caught:
        await client._ensure_session()
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_start_degrades_and_instance_info_remains_available(settings) -> None:
    client = KumaClient(settings)
    client._ensure_session = AsyncMock(side_effect=KumaError("connection_failed", "no"))  # type: ignore[method-assign]
    await client.start()
    info = await client.instance_info()
    assert client.started
    assert info["last_error_code"] == "connection_failed"
    assert info["supported"] is False


@pytest.mark.asyncio
async def test_login_waits_for_kuma_socket_initialization(settings) -> None:
    client = KumaClient(replace(settings, kuma_request_timeout=1))
    socket = LoginSocket(client, {"ok": True})
    socket.connect = AsyncMock(
        side_effect=lambda *_args, **_kwargs: setattr(socket, "connected", True)
    )
    client._socket = socket  # type: ignore[assignment]

    with pytest.raises(KumaError) as caught:
        await client._ensure_session()

    assert caught.value.code == "socket_initialization_timeout"
    assert socket.events == []


@pytest.mark.asyncio
async def test_call_envelopes_and_read_methods(settings) -> None:
    client = KumaClient(settings)
    client.monitors = {"1": {"id": 1, "name": "Owned", "interval": 20}}
    client.ensure_operational = AsyncMock()  # type: ignore[method-assign]

    responses: dict[str, object] = {
        "getMonitor": {
            "ok": True,
            "monitor": {"id": 1, "name": "Owned", "password": "secret"},
        },
        "getMonitorBeats": {
            "ok": True,
            "data": [{"id": 9, "status": 1, "msg": "Bearer secret"}],
        },
        "getMonitorChartData": {"ok": True, "data": [{"value": 1}]},
        "getTags": {"ok": True, "tags": [{"id": 1, "name": "prod"}]},
    }

    async def fake_call(event: str, **_kwargs: object) -> object:
        return responses[event]

    client._socket.call = fake_call  # type: ignore[method-assign]
    monitor = await client.get_monitor(1)
    beats = await client.get_heartbeats(1, 24)
    chart = await client.get_chart_data(1, 24)
    tags = await client.get_tags()
    assert "password" not in monitor
    assert beats[0]["msg"] == "Bearer [REDACTED]"
    assert chart == [{"value": 1}]
    assert tags[0]["name"] == "prod"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "code"),
    [
        (None, "invalid_response"),
        ({"ok": False, "msg": "token=secret"}, "request_rejected"),
    ],
)
async def test_call_failures_are_sanitized(settings, response: object, code: str) -> None:
    client = KumaClient(settings)
    client.ensure_operational = AsyncMock()  # type: ignore[method-assign]
    client._socket.call = AsyncMock(return_value=response)  # type: ignore[method-assign]
    with pytest.raises(KumaError) as caught:
        await client._call("test")
    assert caught.value.code == code
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_refresh_events_and_snapshot(settings) -> None:
    client = KumaClient(settings)

    async def emit(event: str, *_args: Any) -> dict[str, bool]:
        if event == "getMonitorList":
            await client._on_monitor_list({"1": {"id": 1, "name": "One"}})
        if event == "getMaintenanceList":
            await client._on_maintenance_list({"2": {"id": 2, "title": "Window"}})
        return {"ok": True}

    client._call = emit  # type: ignore[method-assign]
    assert (await client.refresh_monitors())["1"]["name"] == "One"
    assert (await client.refresh_maintenance())["2"]["title"] == "Window"
    client.ensure_operational = AsyncMock()  # type: ignore[method-assign]
    snapshot = await client.operational_snapshot()
    assert snapshot["monitors"]["1"]["name"] == "One"


@pytest.mark.asyncio
async def test_concurrent_monitor_refreshes_serialize_complete_transactions(settings) -> None:
    client = KumaClient(settings)
    active_calls = 0
    maximum_active_calls = 0

    async def emit(_event: str) -> dict[str, bool]:
        nonlocal active_calls, maximum_active_calls
        active_calls += 1
        maximum_active_calls = max(maximum_active_calls, active_calls)
        await asyncio.sleep(0.01)
        await client._on_monitor_list({"1": {"id": 1, "name": "One"}})
        active_calls -= 1
        return {"ok": True}

    client._call = emit  # type: ignore[method-assign]
    await asyncio.gather(client.refresh_monitors(), client.refresh_monitors())

    assert maximum_active_calls == 1


@pytest.mark.asyncio
async def test_concurrent_maintenance_refreshes_serialize_complete_transactions(settings) -> None:
    client = KumaClient(settings)
    active_calls = 0
    maximum_active_calls = 0

    async def emit(_event: str) -> dict[str, bool]:
        nonlocal active_calls, maximum_active_calls
        active_calls += 1
        maximum_active_calls = max(maximum_active_calls, active_calls)
        await asyncio.sleep(0.01)
        await client._on_maintenance_list({"2": {"id": 2, "title": "Window"}})
        active_calls -= 1
        return {"ok": True}

    client._call = emit  # type: ignore[method-assign]
    await asyncio.gather(client.refresh_maintenance(), client.refresh_maintenance())

    assert maximum_active_calls == 1
