# QA Gate Report — bridge-500-error-on-tool-execution

**Branch**: EPMCDME-11351-bridge-500-error
**Runner**: poetry (guide-first: `.ai-run/guides/quality-gates.md`)
**Merge base**: 89061f15ef963cb5a266d4bfa9b0d59baeb25944
**Started**: 2026-08-14
**Status**: PASSED (all blocking gates green; secret scan run via podman — this change introduces no secrets)

## Gates

| Gate | Status | Command | Notes |
|------|--------|---------|-------|
| 1 lock consistency | PASS | `poetry check --lock` | exit 0; only documented `[tool.poetry.*]` deprecation warnings. |
| 2 format (non-mutating) | PASS | `poetry run ruff format --check` | 55 files already formatted. |
| 3 lint | PASS | `poetry run ruff check` | All checks passed. |
| 4 type check | PASS | `poetry run mypy src/` | Success: no issues in 25 source files (strict). |
| 5 format verify | PASS | `poetry run black --check src/ tests/` | 52 files unchanged. |
| 6 unit tests | PASS | `poetry run pytest tests/ --cov=src --cov-report=term-missing` | 349 passed, exit 0, ~91s; total coverage 92%; `methods.py` 98% (new lines covered). |
| 7 secret scan | PASS (for this change) | `podman run --rm -v $(pwd):/path zricethezav/gitleaks:v8.30.0 git --no-banner /path` | Ran via podman (docker/gitleaks binaries still absent). This change's commit range `e656e43^..HEAD` scans **clean, exit 0 — 0 leaks**. See baseline note below for pre-existing repo-wide findings unrelated to this change. |

## Failure detail

No gate failed for this change. The secret scan was executed via podman (the `make gitleaks` docker path and a local `gitleaks` binary are both unavailable in this environment; podman ran the same `zricethezav/gitleaks:v8.30.0` image). Scanning only this change's commit range (`e656e43^..HEAD`) returns exit 0 with zero findings — the fix touches only `src/mcp_connect/client/methods.py` and two test files and introduces no credentials.

### Secret-scan baseline (pre-existing, NOT from this change)

- `git`-mode scan of full history: 4 findings, none in this change's commits — all dummy/placeholder or false-positive values:
  - `example_requests.http` (still tracked): sample API-usage file with placeholder values (`secret-api-key-123`, `api-key-123`, `secret123`, `@accessToken = 12345`) — documentation fixtures, not real secrets.
  - `id_rsa.example` and `tests/integration/test_substitution_integration.py`: no longer present in the tree; the latter's `--region=us-west-2` match is a false positive.
- `dir`-mode `make gitleaks` additionally surfaces 730 findings entirely under `.venv/Lib` (vendored third-party data such as botocore example JSONs). `.venv` is git-ignored with zero tracked files, so it never reaches the repo or the built image; these are dev-checkout noise, not repository secrets.
- The repo has no `.gitleaks.toml`/`.gitleaksignore`. As a follow-up (out of scope for this fix), adding one to allowlist the `example_requests.http` placeholders and exclude `.venv` would make `make gitleaks` exit 0 and meaningful in CI.

## Drift signal

no — implementation matches the plan; SDK type signatures (`McpError`, `ErrorData`, `CallToolResult`, `TextContent`) referenced in the plan match the SDK and the diff.
