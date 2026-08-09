# uptime-kuma-mcp

A safety-first, open-source MCP server for observing **Uptime Kuma 2.5.0**.

[![CI](https://github.com/plgonzalezrx8/uptime-kuma-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/plgonzalezrx8/uptime-kuma-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> [!IMPORTANT]
> Uptime Kuma's authenticated Socket.IO interface is internal and may change between releases. This adapter supports **exactly 2.5.0**, verifies the reported version, and blocks operational tools for every other version. Version diagnostics remain available so failures are explainable rather than mysterious.

## What it does

The server exposes curated, read-only MCP tools over Streamable HTTP at `/mcp`. It authenticates MCP clients with scoped HS256 bearer tokens, opens one authenticated Socket.IO session to Kuma, sanitizes data as it enters the adapter, and returns consistent result envelopes.

```text
MCP client
   │  Authorization: Bearer <signed JWT>
   ▼
uptime-kuma-mcp  ── authenticated Socket.IO ──►  Uptime Kuma 2.5.0
   │
   ├─ exact-version gate
   ├─ ownership check for monitor-specific reads
   ├─ bounded parameters and pagination
   └─ field projection + recursive redaction
```

This release has **no create, update, pause, resume, or delete tools**.

## Tools

| Tool | Purpose |
|---|---|
| `kuma_get_instance_info` | Connectivity, Kuma version, compatibility, timezone, and capabilities |
| `kuma_get_monitor_summary` | Counts by active state and latest heartbeat state |
| `kuma_list_monitors` | Filtered, paginated sanitized monitor inventory |
| `kuma_get_monitor` | One sanitized monitor owned by the authenticated Kuma user |
| `kuma_get_heartbeats` | Newest-first heartbeat history, bounded by monitor interval and a 10,000-row safety budget |
| `kuma_get_chart_data` | Kuma's bounded aggregate chart data |
| `kuma_list_tags` | Paginated tag inventory |
| `kuma_list_maintenance` | Paginated maintenance-window metadata |
| `kuma_list_status_pages` | Paginated status-page metadata |
| `kuma_list_notifications` | Notification name and provider type only; configuration is withheld |

Successful tools return:

```json
{
  "ok": true,
  "data": [],
  "meta": {
    "pagination": {
      "offset": 0,
      "limit": 50,
      "returned": 0,
      "total": 0,
      "has_more": false
    }
  }
}
```

## Quick start with Docker Compose

### 1. Configure

```bash
git clone https://github.com/plgonzalezrx8/uptime-kuma-mcp.git
cd uptime-kuma-mcp
cp .env.example .env
openssl rand -hex 32
```

Put the generated value in `MCP_JWT_SECRET`, then set `KUMA_URL` and one Kuma authentication mode in `.env`:

- `KUMA_USERNAME` plus `KUMA_PASSWORD`; or
- `KUMA_JWT` from a Kuma "Remember Me" login.

Do not configure both modes. If the Kuma account uses 2FA with password login, set `KUMA_2FA_TOKEN` for startup.

### 2. Build and start

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/health
```

The default Compose deployment:

- binds only to `127.0.0.1`;
- runs as an unprivileged user;
- drops Linux capabilities;
- uses a read-only root filesystem;
- enables `no-new-privileges`;
- applies memory, CPU, and PID limits.

The health response intentionally contains no Kuma URL, username, token, or provider details:

```json
{"status":"ok","ready":true}
```

`status: ok` means the MCP process is alive. `ready: true` additionally means the Kuma session is authenticated and reports version 2.5.0.

### 3. Issue an MCP client token

```bash
docker compose run --rm --no-deps uptime-kuma-mcp \
  issue-token --subject my-mcp-client --ttl-seconds 86400
```

The command prints the bearer token once. It is signed with `MCP_JWT_SECRET`, bound to the configured issuer and audience, and carries only the `read:kuma` scope. Treat it as a secret.

### 4. Connect an MCP client

The exact client configuration format varies, but the endpoint and header are:

```text
URL: http://127.0.0.1:8000/mcp
Authorization: Bearer <issued-token>
```

A representative remote-server entry looks like:

```json
{
  "mcpServers": {
    "uptime-kuma": {
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "Authorization": "Bearer <issued-token>"
      }
    }
  }
}
```

Consult your MCP client's documentation before copying that shape verbatim.

## Local development

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen --all-groups
cp .env.example .env
# edit .env, then export it through your preferred shell tooling
uv run uptime-kuma-mcp run
```

Quality gates:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest --cov=uptime_kuma_mcp --cov-report=term-missing
uv build
```

## Configuration

| Variable | Required | Default | Notes |
|---|---:|---|---|
| `KUMA_URL` | yes | — | Absolute `http`/`https` URL without embedded credentials, query, or fragment |
| `KUMA_USERNAME` | conditional | — | Required with `KUMA_PASSWORD` unless `KUMA_JWT` is used |
| `KUMA_PASSWORD` | conditional | — | Required with `KUMA_USERNAME`; never returned or logged |
| `KUMA_JWT` | conditional | — | Alternative Kuma auth mode; cannot be combined with password mode |
| `KUMA_2FA_TOKEN` | no | — | Current 2FA token for initial password login; Kuma's issued session JWT is then reused in memory for reconnects |
| `KUMA_TLS_VERIFY` | no | `true` | Keep enabled except in a deliberately isolated test environment |
| `KUMA_CONNECT_TIMEOUT` | no | `10` | Seconds, bounded to 1–120 |
| `KUMA_REQUEST_TIMEOUT` | no | `15` | Seconds, bounded to 1–120 |
| `MCP_JWT_SECRET` | yes | — | HS256 key, minimum 32 bytes |
| `MCP_JWT_ISSUER` | yes | — | Required token issuer claim |
| `MCP_JWT_AUDIENCE` | yes | — | Required token audience claim |
| `MCP_HOST` | no | `127.0.0.1` | Compose overrides this to `0.0.0.0` inside the container |
| `MCP_PORT` | no | `8000` | Listener port; Compose uses it as the host port |
| `MCP_BIND_ADDRESS` | Compose only | `127.0.0.1` | Host-side Compose bind address |
| `MCP_ALLOWED_HOSTS` | no | localhost values | Comma-separated request-guard hosts; add the reverse-proxy hostname when needed |

Environment variables remain directly declared in `compose.yaml`; secret values come from the local `.env` or deployment environment and are not committed.

## Security model

The threat model assumes the MCP client may ask broad questions and that Kuma records may contain credential material.

Defenses include:

- mandatory bearer authentication with issuer, audience, signature, expiry, and `read:kuma` scope checks;
- no write tools in the server registry;
- unsupported Kuma versions blocked before operational calls;
- explicit safe-field projections for monitors, heartbeats, maintenance, and status pages;
- notification provider configuration discarded at event ingress;
- recursive key and string redaction for passwords, tokens, authorization headers, JWTs, URL userinfo, and secret query parameters;
- sanitized errors with raw exception chains suppressed;
- monitor ownership checked against the authenticated session's monitor list before heartbeat and chart calls;
- request timeouts, bounded lookbacks, pagination limits, and a monitor-aware hard heartbeat row budget;
- no Kuma URL, username, or secret fields in health/version results.

See [SECURITY.md](SECURITY.md) for private vulnerability reporting and deployment guidance.

## Compatibility and upgrades

The tested target is:

```text
Uptime Kuma: 2.5.0
Image: louislam/uptime-kuma:2.5.0
Digest: sha256:a8610b3b4c38077922ba51b036691e06887d7cefd91fe620fd3d6d23d03dc240
Upstream source commit: d9a60dfc73140d15111752e4e8910ed4b54bd9a3
```

Before upgrading Kuma:

1. Run the disposable contract harness against the candidate exact image digest.
2. Inspect upstream event names, inputs, callback envelopes, auth flow, and pushed list schemas.
3. Update the compatibility constant and tests in one focused change.
4. Perform a fresh security and redaction review.
5. Upgrade the adapter before the production Kuma instance.

Do not bypass the version gate just to make an upgrade appear green. That turns a controlled incompatibility into silent data errors—the worst kind of "working."

## Architecture and project policy

- [ADR 0001: FastMCP adapter for Uptime Kuma 2.5.0](docs/adr/0001-fastmcp-uptime-kuma-2-5-0.md)
- [Approved architecture proposal](docs/proposals/0001-initial-architecture.md)
- [Contributing](CONTRIBUTING.md)

## License

[MIT](LICENSE)
