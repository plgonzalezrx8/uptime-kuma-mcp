# Verification results

Verification target: uncommitted implementation on
`feat/initial-read-only-mvp`, based on
`50276785ad73bf832d6d57e0b9214fb88cfaa969`.

## Local quality and package gates

| Gate | Command | Result |
|---|---|---|
| Formatting | `uv run ruff format --check .` | PASS — 22 files formatted |
| Lint | `uv run ruff check .` | PASS |
| Types | `uv run mypy src` | PASS — 9 source files |
| CI helper types | `MYPYPATH=src uv run mypy scripts/security_scan.py tests/integration/container_smoke.py` | PASS — 2 files |
| Unit and MCP protocol | `uv run pytest -m 'not integration' -q --cov=uptime_kuma_mcp --cov-report=term-missing` | PASS — 67 passed, 1 deselected, 90.81% coverage |
| Package build | `uv build` | PASS — sdist and wheel built |
| Compose validation | `docker compose config --quiet` with disposable validation values | PASS, zero output |
| Workflow schema | pinned `check-jsonschema==0.34.0` against SchemaStore's GitHub workflow schema | PASS |
| Diff whitespace | `git diff --check` | PASS |

## Live compatibility gate

A disposable container was started from:

`louislam/uptime-kuma:2.5.0@sha256:a8610b3b4c38077922ba51b036691e06887d7cefd91fe620fd3d6d23d03dc240`

`RUN_KUMA_CONTRACT=1 uv run pytest -m integration -q` passed with
`1 passed, 67 deselected` in 18.88 seconds. The contract includes:

- exact reported version 2.5.0;
- authenticated read calls;
- monitor ownership/safe projection;
- status-page and notification cache availability;
- initial per-monitor `heartbeatList` availability before login readiness;
- a new singular `heartbeat` event advancing the post-login cache.

## Final rebuilt-image smoke

The image was rebuilt from the final checkout as `uptime-kuma-mcp:ship` on the
digest-pinned Python 3.12.13 slim-bookworm base and run with a read-only root
filesystem, all capabilities dropped,
`no-new-privileges`, PID/memory/CPU limits, and a bounded `/tmp` tmpfs.

Results:

- `/health` reported ready;
- missing bearer authentication returned HTTP 401;
- MCP discovery returned exactly 10 tools;
- instance diagnostics reported supported Kuma version 2.5.0;
- the process ran as non-root UID 999;
- a write probe under `/app` was denied;
- the uv download cache was absent from the runtime image.

## Security and artifact checks

- `uvx --from bandit==1.8.6 bandit -q -r src`: PASS.
- Frozen runtime requirements exported from `uv.lock`, then audited with
  `pip-audit==2.9.0`: PASS — no known vulnerabilities.
- Trivy `v0.70.0` OS and library scan of the rebuilt final image: PASS — zero
  fixable HIGH/CRITICAL findings. Twenty-four Debian findings without available
  vendor fixes were reported separately and excluded from the actionable gate.
- `uv run python scripts/security_scan.py --artifacts dist`: PASS — no
  high-confidence repository or wheel/sdist findings and no forbidden `.env`
  or `.coverage` artifact files.

## Exclusions

No production Uptime Kuma instance, persistent service, public endpoint, release
tag, or package registry was changed during verification.
