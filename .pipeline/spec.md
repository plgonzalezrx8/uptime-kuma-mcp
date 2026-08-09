# Implementation specification

OPEN QUESTIONS: none

## Governing decisions

- `docs/adr/0001-fastmcp-uptime-kuma-2-5-0.md`
- `docs/proposals/0001-initial-architecture.md`
- Canonical Command Center ADR-0033

## Deliverable

A working read-only FastMCP server for exactly Uptime Kuma 2.5.0, published as an implementation branch and pull request. Live infrastructure deployment is out of scope.

## Files to create or modify

- Python package under `src/uptime_kuma_mcp/`: configuration, compatibility manifest, redaction, async Socket.IO adapter, tool service, HTTP application, and token issuer CLI.
- `tests/`: unit, MCP protocol, and opt-in digest-pinned integration tests.
- `pyproject.toml` and `uv.lock`: exact runtime dependencies and development tools.
- `Dockerfile`, `compose.yaml`, `.dockerignore`, `.env.example`: hardened Docker-first delivery.
- `.github/workflows/ci.yml`: lint, type, unit, MCP protocol, Compose validation, build, and integration gates.
- `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, and compatibility/testing documentation.
- `.pipeline/changes.md`, `.pipeline/test-results.md`, `.pipeline/review.md`, `.pipeline/state.json`.

## Required interfaces

### HTTP

- `GET /health`: unauthenticated, no Kuma details, only service liveness/readiness class.
- `/mcp`: FastMCP Streamable HTTP, bearer JWT required.

### CLI

- `uptime-kuma-mcp`: run the server.
- `uptime-kuma-mcp issue-token`: issue a bounded HMAC JWT without echoing signing secrets.

### MCP tools

- `kuma_get_instance_info`
- `kuma_get_monitor_summary`
- `kuma_list_monitors`
- `kuma_get_monitor`
- `kuma_get_heartbeats`
- `kuma_get_chart_data`
- `kuma_list_tags`
- `kuma_list_maintenance`
- `kuma_list_status_pages`
- `kuma_list_notifications`

All operational tools except `kuma_get_instance_info` must fail closed when Kuma is disconnected, authentication fails, or version is not exactly 2.5.0.

## Contract patterns to follow

- Kuma login events: `loginByToken` or `login`; treat callback `ok` as application-level success.
- Login triggers authoritative `info`, `monitorList`, `heartbeatList`, `maintenanceList`, `notificationList`, and `statusPageList` events.
- Direct reads use callback-bearing events where available: `getMonitor`, `getMonitorBeats`, `getMonitorChartData`, `getTags`, and `getMaintenanceList`.
- Bound every list by validated `offset`/`limit`; preserve deterministic ordering.
- At the adapter boundary recursively redact secrets and reduce notifications to an explicit name/type/status allowlist.
- Do not expose arbitrary Socket.IO passthrough.

## Edge and failure cases

- Missing or conflicting Kuma credentials.
- 2FA challenge when password auth is used.
- Socket disconnect/reconnect while a tool call is active.
- Callback timeout or `ok: false` application response.
- Initial events arriving before/after login callback.
- Unsupported Kuma version.
- Integer-like Socket.IO map keys and missing monitor IDs.
- Empty monitor/heartbeat/status/maintenance lists.
- Secret-shaped keys nested inside monitor, notification, header, auth, database, Docker, or proxy objects.
- Pagination bounds, negative values, and excessive heartbeat periods.
- Invalid or expired MCP bearer JWT, issuer mismatch, and audience mismatch.

## Verification plan

1. Unit tests for config, compatibility, redaction, event synchronization, pagination, summaries, and failure paths.
2. FastMCP in-memory/client protocol tests for initialization, discovery, authentication, valid calls, and schema rejection.
3. Integration contract test against the exact digest-pinned Kuma 2.5.0 image, using disposable credentials and no live infrastructure.
4. `ruff`, `mypy`, `pytest`, secret scan, quiet Compose validation, container build, and clean Compose smoke.
5. Fresh independent read-only reviewer verdict against the final exact checkout.

## Out of scope

- All Kuma writes, including pause/resume.
- Notification testing or outbound messages.
- User, password, 2FA, API-key, backup, restore, or settings management.
- Multi-instance support, stdio transport, subscriptions, public exposure, or live deployment.
- Supporting any Kuma version other than exactly 2.5.0.
