# Implementation changes

## Scope

Implemented the approved read-only FastMCP MVP for exactly Uptime Kuma 2.5.0.
No live infrastructure was deployed.

## Runtime

- Added environment-backed, fail-closed configuration validation.
- Added an asynchronous Socket.IO adapter for Kuma's authenticated read contract.
- Added exact-version compatibility gating for Uptime Kuma 2.5.0.
- Added complete initial-state synchronization for info, monitors, maintenance,
  notifications, status pages, and every monitor's authoritative initial
  `heartbeatList`; zero-monitor instances complete heartbeat readiness immediately.
- Kept the session unauthenticated until all required initial state is present and
  cleared stale heartbeat cache/readiness state before every reauthentication.
- Added bounded live heartbeat caching so monitor status advances after login.
- Added recursive secret redaction and explicit safe output projections, including
  credential-bearing URL substrings, normalized secret query-key variants,
  normalized, auth/credential compound, quoted, whitespace-bearing, and escaped
  secret assignments in arbitrary text, complete line-bounded Authorization and
  Proxy-Authorization header values, recursively decoded URL fragments, malformed
  URL fail-closed handling, bounded nested and multiply percent-encoded query-value
  redaction, and known push/webhook secret paths.
- Reused Kuma's issued session JWT in memory after password/2FA login so reconnects
  do not attempt to reuse a one-time TOTP.
- Made login commit and every operational read fail closed when transport or client
  connection/authentication state is lost, preventing stale-cache reads across a
  disconnect while preserving session-token reauthentication on reconnect.
- Reset the observed Kuma version before every authentication cycle so a reconnect
  cannot reuse stale compatibility state when a new `info` payload omits `version`.
- Added monitor-ownership checks before monitor-specific read calls.
- Added deterministic bounded pagination and read-only summary services.
- Serialized complete monitor/maintenance refresh transactions to prevent shared-event
  races under concurrent reads.
- Added a monitor-interval-aware 10,000-row heartbeat budget, enforced before the
  upstream read and again before projecting the response.
- Reported read capabilities only while the Kuma session is authenticated and compatible.

## MCP and authentication

- Added a FastMCP Streamable HTTP server at `/mcp`.
- Added HS256 bearer JWT verification with issuer, audience, expiry, and
  `read:kuma` scope enforcement.
- Added an unauthenticated `/health` route that exposes only liveness/readiness class.
- Added a bounded token-issuer CLI.
- Exposed exactly the ten approved read-only tools; no arbitrary Socket.IO passthrough
  or mutation tool is present.

## Delivery

- Added a locked Python 3.12 package and build metadata.
- Added a hardened non-root Docker image and Compose service.
- Added digest-pinned Kuma 2.5.0 contract testing.
- Digest-pinned both Docker build stages and updated the runtime to the current
  Python 3.12.13 slim-bookworm patch image after vulnerability scanning rejected
  the stale 3.12.3 base.
- Added SHA-pinned GitHub Actions CI and release workflows; tag releases now depend
  on the complete reusable CI workflow for the tagged commit.
- Added locked dependency auditing, Bandit analysis, repository/artifact secret
  scanning, a SHA-pinned Trivy gate for fixable HIGH/CRITICAL image
  vulnerabilities, and authenticated hardened-container smoke verification to CI.
- Added README, security policy, contribution guide, environment example, and ADR.
