"""Exercise the rebuilt HTTP container against a live disposable Kuma fixture."""

from __future__ import annotations

import asyncio
import os

import httpx
from fastmcp import Client

from uptime_kuma_mcp.compatibility import READ_ONLY_TOOLS, SUPPORTED_KUMA_VERSION
from uptime_kuma_mcp.tokens import issue_token


async def main() -> None:
    base_url = os.environ.get("MCP_SMOKE_URL", "http://127.0.0.1:8000")
    secret = os.environ["MCP_JWT_SECRET"]
    issuer = os.environ["MCP_JWT_ISSUER"]
    audience = os.environ["MCP_JWT_AUDIENCE"]

    async with httpx.AsyncClient(base_url=base_url, timeout=5) as http:
        for _attempt in range(30):
            try:
                health = await http.get("/health")
                if health.status_code == 200 and health.json().get("ready") is True:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError("container did not become ready within 30 seconds")

        unauthenticated = await http.post("/mcp", json={})
        if unauthenticated.status_code != 401:
            raise RuntimeError(
                f"unauthenticated MCP returned {unauthenticated.status_code}, not 401"
            )

    token = issue_token(
        secret=secret,
        issuer=issuer,
        audience=audience,
        subject="ci-container-smoke",
        ttl_seconds=300,
    )
    async with Client(f"{base_url}/mcp", auth=token, timeout=10) as client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        if tool_names != set(READ_ONLY_TOOLS):
            raise RuntimeError(f"unexpected MCP tools: {sorted(tool_names)}")
        result = await client.call_tool("kuma_get_instance_info")
        data = result.data
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise RuntimeError(f"instance-info call failed: {data!r}")
        instance = data.get("data", {})
        if (
            instance.get("kuma_version") != SUPPORTED_KUMA_VERSION
            or instance.get("supported") is not True
        ):
            raise RuntimeError(f"unexpected compatibility result: {instance!r}")

    print(f"container smoke passed: {len(tool_names)} tools, Kuma {SUPPORTED_KUMA_VERSION}")


if __name__ == "__main__":
    asyncio.run(main())
