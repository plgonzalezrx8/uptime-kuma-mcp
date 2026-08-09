# ADR 0001: Build a safety-first FastMCP adapter for Uptime Kuma 2.5.0

- **Status:** Accepted
- **Date:** 2026-08-08
- **Decision owner:** Pedro Gonzalez
- **Canonical decision:** Obsidian Command Center `ADR-0033`

## Context

Uptime Kuma exposes supported, narrow HTTP endpoints and a broader internal Socket.IO interface used by its own web application. The internal interface works but carries no third-party compatibility guarantee. Existing open-source MCP servers already expose broad Kuma control, so this project is justified only if strict safety, redaction, compatibility, and verification are first-class product behavior.

## Decision

Build a clean-room, MIT-licensed Python MCP server with these constraints:

- Python 3.12, FastMCP 3.4.6, and `python-socketio[asyncio-client]` 5.16.3 are exact initial pins.
- Docker Compose plus bearer-authenticated Streamable HTTP is the default deployment.
- The first release supports one Uptime Kuma instance and exactly Uptime Kuma 2.5.0.
- The first implementation phase exposes read-only tools only.
- Operational tools fail closed when the connected Kuma version is not exactly 2.5.0.
- Secrets are removed at the adapter boundary and never returned by tools or logs.
- Future writes require separate runtime enablement; destructive writes additionally require an explicit per-call confirmation.
- Every future mutation must perform direct read-after-write verification.
- Environment variables remain declared in Docker Compose. No external secret manager is introduced.

## Consequences

### Benefits

- Compatibility claims are explicit and testable.
- Read-only defaults limit infrastructure risk.
- Secret redaction is enforced before data reaches an MCP client or LLM.
- Digest-pinned integration fixtures make protocol drift visible.

### Costs and risks

- The internal Socket.IO contract may change with any Kuma release.
- Supporting another Kuma version requires source review and a passing contract suite.
- Maintaining a clean-room implementation duplicates some existing open-source work.
- A single-process persistent session limits horizontal scaling in v1.

## Alternatives considered

- Fork `DavidFuchs/mcp-uptime-kuma` — rejected for v1 because the project owner approved a clean-room FastMCP implementation with stronger safety defaults.
- Contribute only upstream — rejected because it would not produce the requested independently owned project.
- Use `uptime-kuma-api` — rejected because its compatibility target does not provide the exact Kuma 2.5.0 contract needed here.
- Broad full-control v1 — rejected because it expands risk before redaction and contract tests are proven.

## Approval

Pedro Gonzalez explicitly approved the revised FastMCP proposal in the Hermes WebUI on 2026-08-08 with: “I approve, proceed.”

## Implementation constraints

- No deployment to a live host is authorized by this decision.
- No destructive tools ship in the initial read-only MVP.
- The Kuma 2.5.0 integration fixture is pinned to `louislam/uptime-kuma:2.5.0@sha256:a8610b3b4c38077922ba51b036691e06887d7cefd91fe620fd3d6d23d03dc240`.
- The MCP HTTP listener binds to localhost by default.
- Remote exposure requires a trusted TLS reverse proxy and a separate deployment decision.
- FastMCP static tokens are not used as the production authentication mechanism.

## Verification

- Unit tests prove configuration, redaction, pagination, compatibility gating, and timeout behavior.
- MCP protocol tests prove initialization, tool discovery, valid calls, invalid calls, and shutdown.
- Integration tests run against the exact digest-pinned Kuma 2.5.0 container.
- Docker Compose validates quietly and a clean-checkout smoke reaches `/health` and `/mcp`.
- A fresh read-only review must return `SHIP` against the exact final checkout before publication.

## Related records

- [Initial architecture and feature proposal](../proposals/0001-initial-architecture.md)
- Canonical Command Center ADR: `System/Architecture Decisions/ADR-0033-uptime-kuma-fastmcp-adapter.md`
