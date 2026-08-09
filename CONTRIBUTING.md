# Contributing

Contributions are welcome, but compatibility and safety come before tool count.

## Development setup

Requirements:

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose for container and contract tests

```bash
git clone https://github.com/plgonzalezrx8/uptime-kuma-mcp.git
cd uptime-kuma-mcp
uv sync --frozen --all-groups
uv run ruff check .
uv run mypy src
uv run pytest --cov=uptime_kuma_mcp
```

## Pull requests

1. Open an issue for material scope or protocol changes.
2. Keep changes focused and add tests for success, failure, and redaction behavior.
3. Update the compatibility evidence when changing the supported Kuma version.
4. Run the full unit, protocol, container, and disposable Kuma contract checks.
5. Do not add write tools without a new accepted ADR, explicit opt-in gates, serialized mutation handling, and read-after-write verification.
6. Never include live credentials, tokens, provider configuration, or production payloads in fixtures.

## Compatibility changes

The Socket.IO interface is internal to Uptime Kuma. A compatibility update must:

- pin an exact Kuma image tag and digest;
- cite the relevant upstream source event contracts;
- pass the disposable contract harness;
- preserve unsupported-version fail-closed behavior;
- document any schema or behavior changes.

## Style and commits

Use Ruff formatting and linting, strict mypy, and conventional, focused commit messages. Releases use semantic version tags (`vMAJOR.MINOR.PATCH`).

By contributing, you agree that your contribution is licensed under the MIT License.
