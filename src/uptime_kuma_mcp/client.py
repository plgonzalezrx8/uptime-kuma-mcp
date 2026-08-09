"""Async, version-aware adapter for Uptime Kuma's internal Socket.IO API."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import socketio  # type: ignore[import-untyped]

from uptime_kuma_mcp.compatibility import READ_ONLY_TOOLS, SUPPORTED_KUMA_VERSION, is_supported
from uptime_kuma_mcp.config import Settings
from uptime_kuma_mcp.redaction import (
    redact,
    redact_text,
    safe_heartbeat,
    safe_maintenance,
    safe_monitor,
    safe_notification,
    safe_status_page,
)

MAX_HEARTBEAT_ROWS = 10_000


class KumaError(RuntimeError):
    """A sanitized, categorized Kuma integration failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(redact_text(message))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _dict_items(value: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if not isinstance(value, Mapping):
        return []
    result: list[tuple[str, Mapping[str, Any]]] = []
    for key, item in value.items():
        if isinstance(item, Mapping):
            result.append((str(key), item))
    return result


class KumaClient:
    """Own one authenticated Kuma session and sanitized event cache."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._socket = socketio.AsyncClient(
            reconnection=True,
            reconnection_attempts=5,
            reconnection_delay=1,
            reconnection_delay_max=10,
            randomization_factor=0.5,
            ssl_verify=settings.kuma_tls_verify,
            logger=False,
            engineio_logger=False,
        )
        self._session_lock = asyncio.Lock()
        self._call_lock = asyncio.Lock()
        self._monitor_refresh_lock = asyncio.Lock()
        self._maintenance_refresh_lock = asyncio.Lock()
        self._socket_ready_event = asyncio.Event()
        self._info_event = asyncio.Event()
        self._monitor_event = asyncio.Event()
        self._maintenance_event = asyncio.Event()
        self._status_page_event = asyncio.Event()
        self._notification_event = asyncio.Event()
        self._initial_heartbeat_event = asyncio.Event()
        self._initial_heartbeat_ids_seen: set[str] = set()
        self._awaiting_initial_state = False
        self.connected = False
        self.authenticated = False
        self.started = False
        self.last_error_code: str | None = None
        self.version: str | None = None
        self.server_timezone: str | None = None
        self.observed_at: str | None = None
        self._session_jwt = settings.kuma_jwt
        self.monitors: dict[str, dict[str, Any]] = {}
        self.heartbeats: dict[str, list[dict[str, Any]]] = {}
        self.avg_ping: dict[str, float | None] = {}
        self.uptime: dict[str, dict[str, float | None]] = {}
        self.maintenance: dict[str, dict[str, Any]] = {}
        self.status_pages: dict[str, dict[str, Any]] = {}
        self.notifications: list[dict[str, Any]] = []
        self._register_handlers()

    def _register_handlers(self) -> None:
        self._socket.on("connect", handler=self._on_connect)
        self._socket.on("connect_error", handler=self._on_connect_error)
        self._socket.on("disconnect", handler=self._on_disconnect)
        self._socket.on("info", handler=self._on_info)
        self._socket.on("monitorList", handler=self._on_monitor_list)
        self._socket.on("updateMonitorIntoList", handler=self._on_monitor_update)
        self._socket.on("deleteMonitorFromList", handler=self._on_monitor_delete)
        self._socket.on("heartbeatList", handler=self._on_heartbeat_list)
        self._socket.on("heartbeat", handler=self._on_heartbeat)
        self._socket.on("avgPing", handler=self._on_avg_ping)
        self._socket.on("uptime", handler=self._on_uptime)
        self._socket.on("maintenanceList", handler=self._on_maintenance_list)
        self._socket.on("statusPageList", handler=self._on_status_page_list)
        self._socket.on("notificationList", handler=self._on_notification_list)

    async def _on_connect(self) -> None:
        self.connected = True
        self.last_error_code = None

    async def _on_connect_error(self, _data: object) -> None:
        self.connected = False
        self.authenticated = False
        self._socket_ready_event.clear()
        self.last_error_code = "connection_failed"

    async def _on_disconnect(self, *_args: object) -> None:
        self.connected = False
        self.authenticated = False
        self._socket_ready_event.clear()

    async def _on_info(self, data: object) -> None:
        if not isinstance(data, Mapping):
            return
        version = data.get("version")
        timezone = data.get("serverTimezone")
        if isinstance(version, str):
            self.version = version
        if isinstance(timezone, str):
            self.server_timezone = timezone
        self.observed_at = _now()
        self._socket_ready_event.set()
        self._info_event.set()

    async def _on_monitor_list(self, data: object) -> None:
        self.monitors = {key: safe_monitor(item) for key, item in _dict_items(data)}
        self.observed_at = _now()
        self._monitor_event.set()
        self._update_initial_heartbeat_readiness()

    async def _on_monitor_update(self, data: object) -> None:
        for key, item in _dict_items(data):
            self.monitors[key] = safe_monitor(item)
        self.observed_at = _now()

    async def _on_monitor_delete(self, monitor_id: object) -> None:
        key = str(monitor_id)
        self.monitors.pop(key, None)
        self.heartbeats.pop(key, None)
        self.avg_ping.pop(key, None)
        self.uptime.pop(key, None)
        self.observed_at = _now()

    async def _on_heartbeat_list(
        self, monitor_id: object, data: object, overwrite: bool = False
    ) -> None:
        rows = [safe_heartbeat(item) for _, item in _dict_items_from_sequence(data)]
        key = str(monitor_id)
        if overwrite or key not in self.heartbeats:
            self.heartbeats[key] = rows
        else:
            self.heartbeats[key] = rows + self.heartbeats[key]
        self.heartbeats[key] = self.heartbeats[key][-100:]
        self.observed_at = _now()
        if self._awaiting_initial_state:
            self._initial_heartbeat_ids_seen.add(key)
            self._update_initial_heartbeat_readiness()

    def _update_initial_heartbeat_readiness(self) -> None:
        if not self._awaiting_initial_state or not self._monitor_event.is_set():
            return
        if set(self.monitors).issubset(self._initial_heartbeat_ids_seen):
            self._initial_heartbeat_event.set()

    async def _on_heartbeat(self, data: object) -> None:
        if not isinstance(data, Mapping):
            return
        monitor_id = data.get("monitorID")
        if monitor_id is None:
            return
        key = str(monitor_id)
        self.heartbeats.setdefault(key, []).append(safe_heartbeat(data))
        self.heartbeats[key] = self.heartbeats[key][-100:]
        self.observed_at = _now()

    async def _on_avg_ping(self, monitor_id: object, value: object) -> None:
        self.avg_ping[str(monitor_id)] = float(value) if isinstance(value, int | float) else None

    async def _on_uptime(self, monitor_id: object, period: object, value: object) -> None:
        monitor = self.uptime.setdefault(str(monitor_id), {})
        monitor[str(period)] = float(value) if isinstance(value, int | float) else None

    async def _on_maintenance_list(self, data: object) -> None:
        self.maintenance = {key: safe_maintenance(item) for key, item in _dict_items(data)}
        self.observed_at = _now()
        self._maintenance_event.set()

    async def _on_status_page_list(self, data: object) -> None:
        self.status_pages = {key: safe_status_page(item) for key, item in _dict_items(data)}
        self.observed_at = _now()
        self._status_page_event.set()

    async def _on_notification_list(self, data: object) -> None:
        if not isinstance(data, list):
            self.notifications = []
            self._notification_event.set()
            return
        self.notifications = [safe_notification(item) for item in data if isinstance(item, Mapping)]
        self.observed_at = _now()
        self._notification_event.set()

    async def start(self) -> None:
        """Attempt startup compatibility probing without preventing diagnostics."""
        self.started = True
        try:
            await self._ensure_session()
        except KumaError as exc:
            self.last_error_code = exc.code

    async def stop(self) -> None:
        if self._socket.connected:
            await self._socket.disconnect()
        self.connected = False
        self.authenticated = False

    async def _ensure_session(self) -> None:
        async with self._session_lock:
            if not self._socket.connected:
                self._socket_ready_event.clear()
                try:
                    await self._socket.connect(
                        self.settings.kuma_url,
                        socketio_path="socket.io",
                        wait=True,
                        wait_timeout=self.settings.kuma_connect_timeout,
                    )
                except Exception:
                    self.connected = False
                    self.authenticated = False
                    self.last_error_code = "connection_failed"
                    raise KumaError(
                        "connection_failed", "Unable to connect to Uptime Kuma"
                    ) from None
            self.connected = True
            if not self.authenticated:
                try:
                    await asyncio.wait_for(
                        self._socket_ready_event.wait(), self.settings.kuma_request_timeout
                    )
                except TimeoutError:
                    self.last_error_code = "socket_initialization_timeout"
                    raise KumaError(
                        "socket_initialization_timeout",
                        "Uptime Kuma did not finish Socket.IO initialization",
                    ) from None
                await self._login()

    async def _login(self) -> None:
        self.authenticated = False
        self.version = None
        self._awaiting_initial_state = True
        self._initial_heartbeat_ids_seen.clear()
        self._initial_heartbeat_event.clear()
        self.heartbeats.clear()
        self._info_event.clear()
        self._monitor_event.clear()
        self._maintenance_event.clear()
        self._status_page_event.clear()
        self._notification_event.clear()
        try:
            if self._session_jwt:
                response = await self._socket.call(
                    "loginByToken",
                    data=self._session_jwt,
                    timeout=self.settings.kuma_request_timeout,
                )
            else:
                payload: dict[str, str] = {
                    "username": self.settings.kuma_username or "",
                    "password": self.settings.kuma_password or "",
                }
                if self.settings.kuma_2fa_token:
                    payload["token"] = self.settings.kuma_2fa_token
                response = await self._socket.call(
                    "login", data=payload, timeout=self.settings.kuma_request_timeout
                )
        except Exception:
            self._awaiting_initial_state = False
            self.last_error_code = "authentication_failed"
            raise KumaError("authentication_failed", "Uptime Kuma authentication failed") from None

        if not isinstance(response, Mapping):
            self._awaiting_initial_state = False
            self.last_error_code = "invalid_response"
            raise KumaError("invalid_response", "Uptime Kuma returned an invalid login response")
        if response.get("tokenRequired"):
            self._awaiting_initial_state = False
            self.last_error_code = "two_factor_required"
            raise KumaError("two_factor_required", "Uptime Kuma requires a two-factor token")
        if response.get("ok") is not True:
            self._awaiting_initial_state = False
            self.last_error_code = "authentication_failed"
            raise KumaError("authentication_failed", "Uptime Kuma rejected authentication")

        issued_token = response.get("token")
        if isinstance(issued_token, str) and issued_token:
            self._session_jwt = issued_token

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    self._info_event.wait(),
                    self._monitor_event.wait(),
                    self._maintenance_event.wait(),
                    self._status_page_event.wait(),
                    self._notification_event.wait(),
                    self._initial_heartbeat_event.wait(),
                ),
                self.settings.kuma_request_timeout,
            )
        except TimeoutError:
            self._awaiting_initial_state = False
            self.last_error_code = "initial_state_timeout"
            raise KumaError(
                "initial_state_timeout", "Uptime Kuma did not provide required initial state"
            ) from None
        self._awaiting_initial_state = False
        if not self._socket.connected or not self.connected:
            self.authenticated = False
            self.last_error_code = "connection_lost"
            raise KumaError("connection_lost", "Uptime Kuma disconnected before login completed")
        self.authenticated = True
        self.last_error_code = None

    async def _call(self, event: str, *args: object) -> Mapping[str, Any]:
        await self.ensure_operational()
        data: object | None
        if not args:
            data = None
        elif len(args) == 1:
            data = args[0]
        else:
            data = tuple(args)
        async with self._call_lock:
            try:
                response = await self._socket.call(
                    event, data=data, timeout=self.settings.kuma_request_timeout
                )
            except Exception:
                self.last_error_code = "request_failed"
                raise KumaError("request_failed", f"Uptime Kuma request {event} failed") from None
        if not isinstance(response, Mapping):
            raise KumaError(
                "invalid_response", f"Uptime Kuma request {event} returned invalid data"
            )
        if response.get("ok") is not True:
            message = response.get("msg")
            safe_message = redact_text(message) if isinstance(message, str) else "request rejected"
            raise KumaError("request_rejected", f"Uptime Kuma {event}: {safe_message}")
        return response

    async def ensure_operational(self) -> None:
        await self._ensure_session()
        if not self._socket.connected or not self.connected or not self.authenticated:
            self.authenticated = False
            self.last_error_code = "connection_lost"
            raise KumaError("connection_lost", "Uptime Kuma connection is not authenticated")
        if self.version is None:
            raise KumaError("version_unknown", "Uptime Kuma version was not reported")
        if not is_supported(self.version):
            self.last_error_code = "unsupported_version"
            raise KumaError(
                "unsupported_version",
                f"Uptime Kuma {self.version} is unsupported; expected {SUPPORTED_KUMA_VERSION}",
            )

    def _require_owned_monitor(self, monitor_id: int) -> str:
        key = str(monitor_id)
        if key not in self.monitors:
            raise KumaError("monitor_not_found", "Monitor not found for the authenticated user")
        return key

    async def instance_info(self) -> dict[str, Any]:
        try:
            await self._ensure_session()
        except KumaError:
            pass
        operational = self.connected and self.authenticated and is_supported(self.version)
        return {
            "connected": self.connected,
            "authenticated": self.authenticated,
            "kuma_version": self.version,
            "supported": is_supported(self.version),
            "supported_version": SUPPORTED_KUMA_VERSION,
            "server_timezone": self.server_timezone,
            "auth_mode": self.settings.kuma_auth_mode,
            "capabilities": list(READ_ONLY_TOOLS) if operational else [],
            "last_error_code": self.last_error_code,
            "observed_at": self.observed_at,
        }

    async def refresh_monitors(self) -> dict[str, dict[str, Any]]:
        async with self._monitor_refresh_lock:
            self._monitor_event.clear()
            await self._call("getMonitorList")
            try:
                await asyncio.wait_for(
                    self._monitor_event.wait(), self.settings.kuma_request_timeout
                )
            except TimeoutError:
                raise KumaError("refresh_timeout", "Monitor list refresh timed out") from None
            return {key: dict(item) for key, item in self.monitors.items()}

    async def get_monitor(self, monitor_id: int) -> dict[str, Any]:
        await self.ensure_operational()
        self._require_owned_monitor(monitor_id)
        response = await self._call("getMonitor", monitor_id)
        monitor = response.get("monitor")
        if not isinstance(monitor, Mapping):
            raise KumaError("invalid_response", "Uptime Kuma returned invalid monitor data")
        return safe_monitor(monitor)

    async def get_heartbeats(self, monitor_id: int, period_hours: int) -> list[dict[str, Any]]:
        await self.ensure_operational()
        key = self._require_owned_monitor(monitor_id)
        monitor = self.monitors[key]
        intervals = [
            value
            for field in ("interval", "retryInterval")
            if isinstance((value := monitor.get(field)), int)
            and not isinstance(value, bool)
            and value >= 1
        ]
        shortest_interval = min(intervals, default=1)
        estimated_rows = (period_hours * 3600 + shortest_interval - 1) // shortest_interval + 1
        if estimated_rows > MAX_HEARTBEAT_ROWS:
            raise KumaError(
                "heartbeat_budget_exceeded",
                "Requested heartbeat period exceeds the row safety budget; reduce period_hours",
            )
        response = await self._call("getMonitorBeats", monitor_id, period_hours)
        data = response.get("data")
        if not isinstance(data, list):
            raise KumaError("invalid_response", "Uptime Kuma returned invalid heartbeat data")
        if len(data) > MAX_HEARTBEAT_ROWS:
            raise KumaError(
                "heartbeat_budget_exceeded",
                "Uptime Kuma heartbeat response exceeds the row safety budget",
            )
        return [safe_heartbeat(item) for item in data if isinstance(item, Mapping)]

    async def get_chart_data(self, monitor_id: int, period_hours: int) -> Any:
        await self.ensure_operational()
        self._require_owned_monitor(monitor_id)
        response = await self._call("getMonitorChartData", monitor_id, period_hours)
        return redact(response.get("data"))

    async def get_tags(self) -> list[dict[str, Any]]:
        response = await self._call("getTags")
        tags = response.get("tags")
        if not isinstance(tags, list):
            raise KumaError("invalid_response", "Uptime Kuma returned invalid tag data")
        return [redact(dict(item)) for item in tags if isinstance(item, Mapping)]

    async def refresh_maintenance(self) -> dict[str, dict[str, Any]]:
        async with self._maintenance_refresh_lock:
            self._maintenance_event.clear()
            await self._call("getMaintenanceList")
            try:
                await asyncio.wait_for(
                    self._maintenance_event.wait(), self.settings.kuma_request_timeout
                )
            except TimeoutError:
                raise KumaError("refresh_timeout", "Maintenance list refresh timed out") from None
            return {key: dict(item) for key, item in self.maintenance.items()}

    async def operational_snapshot(self) -> dict[str, Any]:
        await self.ensure_operational()
        return {
            "monitors": {key: dict(item) for key, item in self.monitors.items()},
            "heartbeats": {
                key: [dict(item) for item in rows] for key, rows in self.heartbeats.items()
            },
            "avg_ping": dict(self.avg_ping),
            "uptime": {key: dict(item) for key, item in self.uptime.items()},
            "maintenance": {key: dict(item) for key, item in self.maintenance.items()},
            "status_pages": {key: dict(item) for key, item in self.status_pages.items()},
            "notifications": [dict(item) for item in self.notifications],
            "observed_at": self.observed_at,
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "ready": self.connected and self.authenticated and is_supported(self.version),
        }


def _dict_items_from_sequence(value: object) -> list[tuple[str, Mapping[str, Any]]]:
    if not isinstance(value, list):
        return []
    return [(str(index), item) for index, item in enumerate(value) if isinstance(item, Mapping)]
