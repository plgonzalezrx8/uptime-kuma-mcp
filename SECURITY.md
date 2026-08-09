# Security Policy

## Supported versions

Security fixes are provided for the latest tagged release. The current adapter supports **Uptime Kuma 2.5.0 only** and intentionally fails closed for other Kuma versions.

## Reporting a vulnerability

Do **not** open a public issue for a suspected vulnerability or secret exposure.

Use GitHub's private vulnerability reporting for this repository:

1. Open the repository's **Security** tab.
2. Select **Report a vulnerability**.
3. Include the affected release, impact, reproduction steps, and any proposed mitigation.

Please allow a reasonable remediation window before public disclosure. Maintainers will acknowledge a complete report, assess severity, and coordinate a fix and disclosure timeline.

## Security boundaries

- The MCP endpoint requires a signed HS256 bearer token with the `read:kuma` scope.
- This release exposes no state-changing MCP tools.
- Uptime Kuma credentials are accepted only through environment variables and must never be committed.
- Notification provider configuration and secret-shaped monitor fields are removed at Socket.IO ingress.
- Arbitrary errors and credential-shaped strings are redacted before MCP results are produced.
- Monitor-specific read calls are restricted to IDs in the authenticated user's monitor list.
- `/health` is intentionally unauthenticated and returns only process/readiness state.

## Deployment guidance

Bind the Compose port to localhost unless a reverse proxy provides TLS and an additional access boundary. Keep Kuma and this MCP server on a trusted network. Rotate both Kuma credentials and `MCP_JWT_SECRET` after suspected disclosure.
