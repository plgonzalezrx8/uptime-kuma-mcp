"""Initialize the disposable Kuma 2.5.0 CI fixture and add one monitor."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from urllib.request import urlopen

import socketio  # type: ignore[import-untyped]

KUMA_URL = os.environ.get("KUMA_URL", "http://127.0.0.1:3001")
USERNAME = os.environ.get("KUMA_USERNAME", "mcp-contract")
PASSWORD = os.environ.get("KUMA_PASSWORD", "McpContract-2.5.0-Test!")
MONITOR_URL = os.environ.get("CONTRACT_MONITOR_URL", "http://127.0.0.1:3001/api/entry-page")


async def wait_for_http() -> None:
    def probe() -> None:
        with urlopen(f"{KUMA_URL}/api/entry-page", timeout=3) as response:  # noqa: S310
            if response.status != 200:
                raise RuntimeError("Kuma HTTP fixture is not ready")
            payload = json.load(response)
            if not isinstance(payload, Mapping) or payload.get("type") != "entryPage":
                raise RuntimeError("Kuma application server is not ready")

    for attempt in range(120):
        try:
            await asyncio.to_thread(probe)
            return
        except Exception:
            if attempt == 119:
                raise
            await asyncio.sleep(1)


async def main() -> None:
    client = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)
    monitor_list: dict[str, object] = {}
    socket_ready = asyncio.Event()

    async def on_info(_data: object) -> None:
        socket_ready.set()

    async def on_monitor_list(data: object) -> None:
        nonlocal monitor_list
        monitor_list = dict(data) if isinstance(data, Mapping) else {}

    client.on("monitorList", handler=on_monitor_list)
    client.on("info", handler=on_info)

    await wait_for_http()
    await client.connect(KUMA_URL, wait_timeout=10)
    try:
        await asyncio.wait_for(socket_ready.wait(), timeout=15)
        needs_setup = await client.call("needSetup", timeout=15)
        if needs_setup:
            setup = await client.call("setup", data=(USERNAME, PASSWORD), timeout=30)
            if not isinstance(setup, Mapping) or setup.get("ok") is not True:
                raise RuntimeError("disposable Kuma setup failed")

        login = await client.call(
            "login", data={"username": USERNAME, "password": PASSWORD}, timeout=30
        )
        if not isinstance(login, Mapping) or login.get("ok") is not True:
            raise RuntimeError("disposable Kuma login failed")

        await asyncio.sleep(0.5)
        if not monitor_list:
            monitor = {
                "name": "Contract HTTP monitor",
                "type": "http",
                "url": MONITOR_URL,
                "method": "GET",
                "active": True,
                "interval": 20,
                "retryInterval": 20,
                "resendInterval": 0,
                "maxretries": 0,
                "timeout": 10,
                "expiryNotification": False,
                "ignoreTls": False,
                "upsideDown": False,
                "notificationIDList": {},
                "accepted_statuscodes": ["200-299"],
                "kafkaProducerBrokers": [],
                "kafkaProducerSaslOptions": {},
                "conditions": [],
                "rabbitmqNodes": [],
            }
            added = await client.call("add", data=monitor, timeout=30)
            if not isinstance(added, Mapping) or added.get("ok") is not True:
                raise RuntimeError("disposable Kuma monitor creation failed")
            print(f"fixture_monitor_id={added.get('monitorID')}")
        else:
            print(f"fixture_monitor_count={len(monitor_list)}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"contract fixture bootstrap failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
