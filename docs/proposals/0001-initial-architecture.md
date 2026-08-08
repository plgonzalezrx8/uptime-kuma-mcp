# Proposal 0001: Initial architecture and feature scope

- **Status:** Proposed — FastMCP selected by project owner; remaining architecture not yet approved for implementation
- **Date:** 2026-08-08
- **Repository:** `plgonzalezrx8/uptime-kuma-mcp`
- **License:** MIT

## 1. Decision requested

Choose whether to build a new safety-first Uptime Kuma MCP, fork an existing implementation, or contribute upstream instead. If a new implementation is approved, also approve the bounded v1 architecture and tool scope below.

No implementation should begin until this proposal is explicitly approved. The canonical Obsidian ADR registry was unreachable while this draft was prepared, so accepted ADR conflict-checking remains a prerequisite before implementation.

## 2. Evidence and constraints

Uptime Kuma exposes two different integration surfaces:

1. Public-purpose HTTP endpoints for push heartbeats, status pages, badges, entry-page data, and Prometheus metrics.
2. An internal authenticated Socket.IO interface used by the web UI for monitor, maintenance, notification, tag, status-page, and settings operations.

Uptime Kuma explicitly warns that the Socket.IO interface is internal, unsupported for third-party compatibility guarantees, and may change without notice. It works, but adapters must be version-aware.

Concrete compatibility evidence:

- Kuma 2.3.2 introduced a required `conditions` field that broke clients omitting it.
- A current third-party MCP had to add missing write fields, secret redaction, session recovery, and read-after-write verification.
- Bulk pause/resume traffic has exhausted a Kuma MariaDB pool in the field.
- As of this proposal, Uptime Kuma's latest release is 2.5.0.
- A live read-only check on 2026-08-08 confirmed the project owner's infrastructure is running healthy Uptime Kuma 2.5.0. The private host/address is intentionally omitted from this public document.

There are already multiple MIT-licensed MCPs. `DavidFuchs/mcp-uptime-kuma` is active, supports Kuma v2, Docker, stdio and Streamable HTTP, and has a real contributor base. A generic clone would add little value.

## 3. Product options

### Option A — New clean-room safety-first FastMCP server

Build a narrow Python FastMCP server with a direct asynchronous adapter against Kuma's Socket.IO contract. FastMCP is a project-owner requirement.

**Benefits**
- Full control over safety defaults and compatibility policy.
- No inherited credential-exposure behavior or broad tool surface.
- Clear identity as an operations-safe MCP rather than a full-control demo.

**Costs**
- Highest maintenance burden.
- Duplicates mature upstream work.
- Requires ongoing testing for every supported Kuma release.

### Option B — Fork the active `DavidFuchs/mcp-uptime-kuma` project

Retain MIT attribution, then add stricter defaults, policy gates, Compose hardening, and compatibility certification.

**Benefits**
- Fastest path to broad working functionality.
- Starts from an active v2 implementation with integration tests.

**Costs**
- Ongoing upstream merge burden.
- Repository identity becomes derivative.
- Existing architecture may constrain stronger safety boundaries.
- Converting the current independent repository into a true GitHub fork would require deleting/recreating it, which is not authorized by this proposal.

### Option C — Contribute upstream and keep no competing implementation

Contribute safety, verification, and compatibility improvements to the active project.

**Benefits**
- Least duplication and strongest community impact.
- Lowest long-term maintenance burden.

**Costs**
- Less product control and no independent tool under this account.
- Upstream may reject opinionated defaults.

### Recommendation

**FastMCP selects the new Python implementation direction, but Option A is still worthwhile only if the safety policy itself is the product.** Building another broad, undifferentiated Kuma MCP would be wasted effort.

The remainder of this proposal describes Option A.

## 4. Proposed v1 architecture

```mermaid
flowchart LR
    Client[MCP client] -->|Bearer-authenticated Streamable HTTP| Server[MCP server]
    Server --> Policy[Tool policy and confirmation gate]
    Policy --> Redact[Schema validation and secret redaction]
    Redact --> Adapter[Kuma compatibility adapter]
    Adapter <-->|Persistent Socket.IO session| Kuma[Uptime Kuma]
    Adapter --> Verify[Direct post-write read-back]
    Verify --> Redact
    Server --> Logs[Sanitized structured stdout logs]
```

### Runtime

- Python 3.12.
- FastMCP stable 3.x, initially pinned exactly to `fastmcp==3.4.6`; FastMCP 4 prereleases are excluded.
- `python-socketio[asyncio-client]==5.16.3` with `AsyncClient` for Kuma's internal management interface.
- Direct Kuma adapter code rather than a dependency on the currently v1-only `uptime-kuma-api` wrapper.
- `uv` lockfile for reproducible dependency resolution.
- One persistent Socket.IO connection to one Kuma instance in v1, managed through FastMCP's async lifespan.
- FastMCP direct Streamable HTTP server at `/mcp`, plus a minimal custom `/health` route with no Kuma details.
- One server process in v1 so the persistent Kuma session and in-memory event cache have one owner.
- Stateless service: no application database and no credential persistence.
- Stdio may be added later, but Docker Compose plus Streamable HTTP is the default and first release gate.
- FastMCP and Socket.IO upgrades receive the same contract-test gate as Kuma upgrades; compatible minor versions are not assumed.

### Authentication

- Kuma: JWT or username/password; API keys are insufficient for Socket.IO management.
- MCP endpoint: bearer authentication required by default using FastMCP token verification. The proposed v1 path is an HMAC-signed JWT with explicit issuer/audience and a small offline token-issuance command; FastMCP static tokens are excluded from production because its documentation limits them to development/testing.
- Compose publishes only to `127.0.0.1` by default. Remote exposure requires an explicitly configured trusted reverse proxy and TLS.
- Configuration uses environment variables declared in Compose and a committed `.env.example`; no Infisical integration.

### Docker posture

- Multi-stage Python build with dependencies installed from the committed `uv.lock`.
- Non-root runtime user.
- Read-only root filesystem, `cap_drop: [ALL]`, `no-new-privileges`, and `tmpfs` for temporary files.
- Healthcheck, graceful shutdown, bounded reconnect backoff, and pinned image versions.
- GHCR publishing after release automation is approved.

## 5. Safety model

### Defaults

- Read-only mode is the default.
- Writes require `ENABLE_WRITES=true`.
- Destructive tools require both `ENABLE_DESTRUCTIVE=true` and `confirm: true` in the tool call.
- Unknown tool fields fail loudly; they are never silently dropped.
- Mutations are serialized per Kuma instance and rate-limited.

### Mandatory redaction

Never return or log:

- `basic_auth_pass`, bearer tokens, push tokens, custom authorization headers;
- database connection strings or credentials;
- Docker host credentials or certificates;
- notification provider configuration secrets;
- Kuma password, JWT, MCP bearer token, or session material.

Sensitive fields are removed at the adapter boundary before they can enter MCP results, errors, or logs. There is no `include_sensitive` escape hatch.

### Mutation verification

Every write follows this sequence:

1. Validate input against the supported Kuma-version schema.
2. Read and sanitize the current object when one exists.
3. Emit the Socket.IO mutation and inspect the application callback.
4. Read directly from Kuma again rather than trusting a possibly stale event cache.
5. Compare safety-relevant requested fields with persisted fields.
6. Return a sanitized before/after diff and verification result.

A callback containing `ok: true` is not considered proof that all fields persisted.

## 6. Proposed feature roadmap

### Phase 0 — Contract and security harness

No public write tools yet.

- Detect Kuma version and authentication mode.
- Capture sanitized schemas for initial Socket.IO events.
- Build disposable-fixture contract tests against pinned Kuma containers.
- Define the redaction corpus and leak tests.
- Document the supported-version matrix.

### Phase 1 — Read-only MVP

Proposed tools:

| Tool | Purpose |
|---|---|
| `kuma_get_instance_info` | Version, connection state, server timezone, and supported capability flags |
| `kuma_get_monitor_summary` | Context-efficient counts and current states, including heartbeat age |
| `kuma_list_monitors` | Filtered, paginated, redacted monitor inventory |
| `kuma_get_monitor` | Redacted monitor configuration and current state |
| `kuma_get_heartbeats` | Bounded heartbeat history with explicit ordering and freshness |
| `kuma_get_chart_data` | Bounded aggregate uptime/ping data |
| `kuma_list_tags` | Tag inventory |
| `kuma_list_maintenance` | Maintenance windows |
| `kuma_list_status_pages` | Status-page metadata |
| `kuma_list_notifications` | Provider names/types only; secret configuration withheld |

Success gate: no known secret reaches any tool result; all schemas pass against the supported Kuma matrix.

### Phase 2 — Guarded monitor writes

- `kuma_create_monitor`
- `kuma_update_monitor`
- `kuma_pause_monitor`
- `kuma_resume_monitor`

Initial monitor types: HTTP(S), keyword, JSON query, ping, TCP port, DNS, and push. Other types wait for explicit schemas and fixtures.

Success gate: every supported field has a persistence test and every mutation returns read-back evidence.

### Phase 3 — Maintenance and status operations

- Create, update, pause/resume, and delete maintenance windows.
- Post/update/unpin status-page incidents.
- Create/update status pages only after full read-back tests exist.

Prefer maintenance windows over bulk monitor pausing.

### Phase 4 — Optional expansion

- Multiple Kuma instances.
- Additional monitor types.
- Stdio transport.
- MCP resources/subscriptions for live status changes.
- Notification creation/testing only after provider-specific secret schemas and outbound-message safeguards exist.

## 7. Explicit v1 non-goals

- User, password, 2FA, or authentication-setting management.
- API-key management.
- Database migration, backup, restore, or administrative repair.
- Arbitrary Socket.IO event passthrough.
- Returning full notification configurations.
- Bulk unbounded mutations.
- Automatic Kuma upgrades.
- Compatibility claims for untested Kuma versions.

## 8. Compatibility policy

- The v1 supported target is **exactly Uptime Kuma 2.5.0**, matching the project owner's live infrastructure.
- The integration fixture is pinned to `louislam/uptime-kuma:2.5.0@sha256:a8610b3b4c38077922ba51b036691e06887d7cefd91fe620fd3d6d23d03dc240` so a mutable tag cannot silently change CI behavior.
- Startup reads Kuma's self-reported version and compares it with the compiled compatibility manifest.
- If Kuma is not 2.5.0, the server fails closed: `/health` and `kuma_get_instance_info` remain available for diagnosis, but operational read and write tools are disabled with a clear unsupported-version result.
- A new Kuma version becomes supported only through an explicit proposal update and a passing full contract suite; semver proximity is not treated as compatibility proof.
- Every MCP release publishes an exact MCP-to-Kuma compatibility matrix.

## 9. Verification and release gates

- Unit tests for schemas, redaction, policies, rate limits, and reconnect behavior.
- Integration tests against the exact digest-pinned Uptime Kuma 2.5.0 disposable container.
- Controlled create/read/update/read/delete fixture lifecycle with cleanup verification.
- Tests proving known secrets cannot appear in results, logs, snapshots, or thrown errors.
- MCP protocol tests for initialize, tools/list, valid calls, invalid calls, and session shutdown.
- Docker Compose smoke test from a clean checkout.
- Dependency, container, and secret scanning in CI.
- No `latest` tag until a versioned release passes all gates.

## 10. Approval questions

1. Choose Option A (new), B (fork), or C (upstream contribution).
2. Approve Python 3.12 + FastMCP 3.x + direct `python-socketio` adapter, with exact dependency pins?
3. Approve single-instance, read-only-first v1 rather than broad full control?
4. Approve bearer-authenticated Streamable HTTP bound to localhost by default?
5. Approve exact Uptime Kuma 2.5.0-only compatibility, failing closed on every other version?
6. Approve destructive tools being disabled until a later phase?
7. Approve FastMCP HMAC-JWT verification for the default HTTP deployment, rather than a plaintext static token?

## Sources

- [Uptime Kuma Internal API](https://github.com/louislam/uptime-kuma/wiki/Internal-API)
- [Uptime Kuma 2.5.0 release](https://github.com/louislam/uptime-kuma/releases/tag/2.5.0)
- [Kuma conditions compatibility regression](https://github.com/louislam/uptime-kuma/pull/7484)
- [Bulk Socket.IO mutation database-pool issue](https://github.com/louislam/uptime-kuma/issues/6855)
- [Active existing MCP](https://github.com/DavidFuchs/mcp-uptime-kuma)
- [Existing MCP v0.11.0 security and hardening release](https://github.com/DavidFuchs/mcp-uptime-kuma/releases/tag/v0.11.0)
- [FastMCP documentation](https://gofastmcp.com/)
- [FastMCP HTTP deployment](https://gofastmcp.com/deployment/http)
- [FastMCP token verification](https://gofastmcp.com/servers/auth/token-verification)
