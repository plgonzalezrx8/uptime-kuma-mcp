"""Command-line entry point for serving the MCP and issuing client tokens."""

from __future__ import annotations

import argparse
import os
import sys

from uptime_kuma_mcp.config import ConfigError, Settings
from uptime_kuma_mcp.server import build_mcp
from uptime_kuma_mcp.tokens import issue_token


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uptime-kuma-mcp")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="run the Streamable HTTP MCP server")
    token_parser = subparsers.add_parser("issue-token", help="issue a scoped MCP client JWT")
    token_parser.add_argument("--subject", default="uptime-kuma-mcp-client")
    token_parser.add_argument("--ttl-seconds", type=int, default=86_400)
    return parser


def _auth_environment() -> tuple[str, str, str]:
    secret = os.environ.get("MCP_JWT_SECRET", "")
    issuer = os.environ.get("MCP_JWT_ISSUER", "")
    audience = os.environ.get("MCP_JWT_AUDIENCE", "")
    if len(secret.encode()) < 32:
        raise ConfigError("MCP_JWT_SECRET must be at least 32 bytes")
    if not issuer.strip():
        raise ConfigError("MCP_JWT_ISSUER is required")
    if not audience.strip():
        raise ConfigError("MCP_JWT_AUDIENCE is required")
    return secret, issuer, audience


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    command = args.command or "run"
    try:
        if command == "issue-token":
            secret, issuer, audience = _auth_environment()
            print(
                issue_token(
                    secret=secret,
                    issuer=issuer,
                    audience=audience,
                    subject=args.subject,
                    ttl_seconds=args.ttl_seconds,
                )
            )
            return

        settings = Settings.from_env()
        mcp = build_mcp(settings)
        mcp.run(
            transport="http",
            host=settings.mcp_host,
            port=settings.mcp_port,
            path="/mcp",
            host_origin_protection=True,
            allowed_hosts=list(settings.mcp_allowed_hosts),
            show_banner=False,
        )
    except (ConfigError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
