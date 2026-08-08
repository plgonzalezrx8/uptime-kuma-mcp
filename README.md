# Uptime Kuma MCP

> **Status: planning.** This repository does not contain a working MCP server yet.

A proposed MIT-licensed, FastMCP-based, Docker Compose-first MCP server for safely observing and managing Uptime Kuma.

The intended differentiator is not "more Socket.IO events." Existing projects already provide broad Uptime Kuma control. This proposal instead emphasizes:

- strict secret redaction before data reaches an LLM;
- read-only operation by default;
- explicit confirmation and policy gates for destructive actions;
- database-backed read-after-write verification rather than trusting `{"ok": true}`;
- bounded mutation concurrency to avoid overwhelming Uptime Kuma;
- exact dependency pinning plus an explicit Uptime Kuma compatibility matrix and live contract tests;
- hardened Streamable HTTP deployment through Docker Compose.

## Before implementation

Architecture and scope are still **Proposed**. Read [the initial architecture and feature proposal](docs/proposals/0001-initial-architecture.md), then approve or revise it before implementation begins.

## License

[MIT](LICENSE)
