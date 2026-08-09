"""Read-only application service with deterministic pagination and summaries."""

from __future__ import annotations

from typing import Any

from uptime_kuma_mcp.client import KumaClient

_STATUS_NAMES = {0: "down", 1: "up", 2: "pending", 3: "maintenance"}


def _latest_heartbeat(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda row: str(row.get("time", "")))


def _paginate(
    items: list[dict[str, Any]], offset: int, limit: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total = len(items)
    page = items[offset : offset + limit]
    return page, {
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "total": total,
        "has_more": offset + len(page) < total,
    }


def _envelope(data: Any, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True, "data": data, "meta": meta or {}}


class KumaService:
    """Purpose-built read operations over the sanitized Kuma client."""

    def __init__(self, client: KumaClient) -> None:
        self.client = client

    async def instance_info(self) -> dict[str, Any]:
        return _envelope(await self.client.instance_info())

    async def monitor_summary(self) -> dict[str, Any]:
        await self.client.refresh_monitors()
        snapshot = await self.client.operational_snapshot()
        status_counts = {name: 0 for name in _STATUS_NAMES.values()}
        status_counts["unknown"] = 0
        active = 0
        inactive = 0
        for key, monitor in snapshot["monitors"].items():
            if monitor.get("active"):
                active += 1
            else:
                inactive += 1
            latest = _latest_heartbeat(snapshot["heartbeats"].get(key, []))
            status = latest.get("status") if latest else None
            status_name = (
                _STATUS_NAMES.get(status, "unknown") if isinstance(status, int) else "unknown"
            )
            status_counts[status_name] += 1
        return _envelope(
            {
                "monitor_count": len(snapshot["monitors"]),
                "active": active,
                "inactive": inactive,
                "status_counts": status_counts,
            },
            meta={"observed_at": snapshot["observed_at"]},
        )

    async def list_monitors(
        self,
        *,
        active: bool | None,
        monitor_type: str | None,
        status: int | None,
        query: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        await self.client.refresh_monitors()
        snapshot = await self.client.operational_snapshot()
        normalized_query = query.casefold().strip() if query else None
        items: list[dict[str, Any]] = []
        for key, monitor in snapshot["monitors"].items():
            latest = _latest_heartbeat(snapshot["heartbeats"].get(key, []))
            latest_status = latest.get("status") if latest else None
            if active is not None and bool(monitor.get("active")) is not active:
                continue
            if monitor_type and monitor.get("type") != monitor_type:
                continue
            if status is not None and latest_status != status:
                continue
            if normalized_query:
                haystack = " ".join(
                    str(monitor.get(field, "")) for field in ("name", "type", "url", "hostname")
                ).casefold()
                if normalized_query not in haystack:
                    continue
            item = dict(monitor)
            item["latestHeartbeat"] = latest
            item["avgPing"] = snapshot["avg_ping"].get(key)
            item["uptime"] = snapshot["uptime"].get(key, {})
            items.append(item)
        items.sort(key=lambda item: (str(item.get("name", "")).casefold(), int(item.get("id", 0))))
        page, pagination = _paginate(items, offset, limit)
        return _envelope(
            page,
            meta={"pagination": pagination, "observed_at": snapshot["observed_at"]},
        )

    async def get_monitor(self, monitor_id: int) -> dict[str, Any]:
        monitor = await self.client.get_monitor(monitor_id)
        snapshot = await self.client.operational_snapshot()
        key = str(monitor_id)
        monitor["latestHeartbeat"] = _latest_heartbeat(snapshot["heartbeats"].get(key, []))
        monitor["avgPing"] = snapshot["avg_ping"].get(key)
        monitor["uptime"] = snapshot["uptime"].get(key, {})
        return _envelope(monitor, meta={"observed_at": snapshot["observed_at"]})

    async def get_heartbeats(
        self, monitor_id: int, period_hours: int, offset: int, limit: int
    ) -> dict[str, Any]:
        rows = await self.client.get_heartbeats(monitor_id, period_hours)
        rows.sort(key=lambda row: str(row.get("time", "")), reverse=True)
        page, pagination = _paginate(rows, offset, limit)
        return _envelope(
            page,
            meta={"monitor_id": monitor_id, "period_hours": period_hours, "pagination": pagination},
        )

    async def get_chart_data(self, monitor_id: int, period_hours: int) -> dict[str, Any]:
        data = await self.client.get_chart_data(monitor_id, period_hours)
        return _envelope(data, meta={"monitor_id": monitor_id, "period_hours": period_hours})

    async def list_tags(self, offset: int, limit: int) -> dict[str, Any]:
        items = await self.client.get_tags()
        items.sort(key=lambda item: (str(item.get("name", "")).casefold(), int(item.get("id", 0))))
        page, pagination = _paginate(items, offset, limit)
        return _envelope(page, meta={"pagination": pagination})

    async def list_maintenance(self, offset: int, limit: int) -> dict[str, Any]:
        maintenance = await self.client.refresh_maintenance()
        items = list(maintenance.values())
        items.sort(key=lambda item: (str(item.get("title", "")).casefold(), int(item.get("id", 0))))
        page, pagination = _paginate(items, offset, limit)
        return _envelope(
            page, meta={"pagination": pagination, "observed_at": self.client.observed_at}
        )

    async def list_status_pages(self, offset: int, limit: int) -> dict[str, Any]:
        snapshot = await self.client.operational_snapshot()
        items = list(snapshot["status_pages"].values())
        items.sort(
            key=lambda item: (str(item.get("title", "")).casefold(), str(item.get("slug", "")))
        )
        page, pagination = _paginate(items, offset, limit)
        return _envelope(
            page, meta={"pagination": pagination, "observed_at": snapshot["observed_at"]}
        )

    async def list_notifications(self, offset: int, limit: int) -> dict[str, Any]:
        snapshot = await self.client.operational_snapshot()
        items = list(snapshot["notifications"])
        items.sort(
            key=lambda item: (str(item.get("name", "")).casefold(), int(item.get("id") or 0))
        )
        page, pagination = _paginate(items, offset, limit)
        return _envelope(
            page, meta={"pagination": pagination, "observed_at": snapshot["observed_at"]}
        )
