"""FastMCP server definition and read-only tool schemas."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Annotated, Any, cast

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from uptime_kuma_mcp import __version__
from uptime_kuma_mcp.client import KumaClient, KumaError
from uptime_kuma_mcp.config import Settings
from uptime_kuma_mcp.service import KumaService

PageLimit = Annotated[int, Field(ge=1, le=100, description="Maximum rows to return")]
PageOffset = Annotated[int, Field(ge=0, description="Zero-based row offset")]
MonitorID = Annotated[int, Field(ge=1, description="Uptime Kuma monitor ID")]
PeriodHours = Annotated[int, Field(ge=1, le=720, description="Bounded lookback in hours")]
StatusCode = Annotated[
    int | None,
    Field(description="Optional Kuma state: 0=down, 1=up, 2=pending, 3=maintenance"),
]


def _client(ctx: Context) -> KumaClient:
    return cast(KumaClient, ctx.lifespan_context["kuma"])


async def _invoke(operation: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    try:
        return await operation
    except KumaError as exc:
        raise ToolError(f"{exc.code}: {exc}") from None


def build_mcp(settings: Settings, client: KumaClient | None = None) -> FastMCP:
    """Create the authenticated MCP application around one Kuma client."""
    kuma = client or KumaClient(settings)

    @asynccontextmanager
    async def app_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, KumaClient]]:
        await kuma.start()
        try:
            yield {"kuma": kuma}
        finally:
            await kuma.stop()

    verifier = JWTVerifier(
        public_key=settings.mcp_jwt_secret,
        issuer=settings.mcp_jwt_issuer,
        audience=settings.mcp_jwt_audience,
        algorithm="HS256",
        required_scopes=["read:kuma"],
    )
    mcp = FastMCP(
        "Uptime Kuma MCP",
        version=__version__,
        instructions=(
            "Read-only monitoring tools for exactly Uptime Kuma 2.5.0. "
            "No tool in this server mutates Kuma state."
        ),
        auth=verifier,
        lifespan=app_lifespan,
        mask_error_details=True,
        strict_input_validation=True,
    )

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(kuma.health())

    @mcp.tool
    async def kuma_get_instance_info(ctx: Context) -> dict[str, Any]:
        """Report connectivity, exact Kuma version compatibility, and read-only capabilities."""
        return await _invoke(KumaService(_client(ctx)).instance_info())

    @mcp.tool
    async def kuma_get_monitor_summary(ctx: Context) -> dict[str, Any]:
        """Summarize monitor counts and latest states without returning full monitor records."""
        return await _invoke(KumaService(_client(ctx)).monitor_summary())

    @mcp.tool
    async def kuma_list_monitors(
        ctx: Context,
        active: bool | None = None,
        monitor_type: str | None = None,
        status: StatusCode = None,
        query: str | None = None,
        offset: PageOffset = 0,
        limit: PageLimit = 50,
    ) -> dict[str, Any]:
        """List sanitized monitors with optional filters and deterministic pagination."""
        if status is not None and status not in {0, 1, 2, 3}:
            raise ToolError("invalid_status: status must be 0, 1, 2, or 3")
        return await _invoke(
            KumaService(_client(ctx)).list_monitors(
                active=active,
                monitor_type=monitor_type,
                status=status,
                query=query,
                offset=offset,
                limit=limit,
            )
        )

    @mcp.tool
    async def kuma_get_monitor(ctx: Context, monitor_id: MonitorID) -> dict[str, Any]:
        """Get one sanitized monitor owned by the authenticated Kuma user."""
        return await _invoke(KumaService(_client(ctx)).get_monitor(monitor_id))

    @mcp.tool
    async def kuma_get_heartbeats(
        ctx: Context,
        monitor_id: MonitorID,
        period_hours: PeriodHours = 24,
        offset: PageOffset = 0,
        limit: PageLimit = 100,
    ) -> dict[str, Any]:
        """Return newest-first sanitized heartbeat history for an owned monitor."""
        return await _invoke(
            KumaService(_client(ctx)).get_heartbeats(monitor_id, period_hours, offset, limit)
        )

    @mcp.tool
    async def kuma_get_chart_data(
        ctx: Context, monitor_id: MonitorID, period_hours: PeriodHours = 24
    ) -> dict[str, Any]:
        """Return Kuma's bounded aggregate chart data for an owned monitor."""
        return await _invoke(KumaService(_client(ctx)).get_chart_data(monitor_id, period_hours))

    @mcp.tool
    async def kuma_list_tags(
        ctx: Context, offset: PageOffset = 0, limit: PageLimit = 100
    ) -> dict[str, Any]:
        """List sanitized Kuma tags with deterministic pagination."""
        return await _invoke(KumaService(_client(ctx)).list_tags(offset, limit))

    @mcp.tool
    async def kuma_list_maintenance(
        ctx: Context, offset: PageOffset = 0, limit: PageLimit = 100
    ) -> dict[str, Any]:
        """List sanitized maintenance windows with deterministic pagination."""
        return await _invoke(KumaService(_client(ctx)).list_maintenance(offset, limit))

    @mcp.tool
    async def kuma_list_status_pages(
        ctx: Context, offset: PageOffset = 0, limit: PageLimit = 100
    ) -> dict[str, Any]:
        """List sanitized status-page metadata from the authenticated session."""
        return await _invoke(KumaService(_client(ctx)).list_status_pages(offset, limit))

    @mcp.tool
    async def kuma_list_notifications(
        ctx: Context, offset: PageOffset = 0, limit: PageLimit = 100
    ) -> dict[str, Any]:
        """List notification names/types only; provider configuration is never returned."""
        return await _invoke(KumaService(_client(ctx)).list_notifications(offset, limit))

    return mcp
