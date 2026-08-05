# QA Gate Report — user-agent-header-mcp-client-name

**Branch**: feat/user-agent-header
**Runner**: poetry
**Started**: 2026-08-05T13:40:00Z
**Status**: BLOCKED

## Gates

| Gate | Source | Status | Duration | Command | Notes |
|------|--------|--------|----------|---------|-------|
| format | guide | PASS | ~1s | `poetry run ruff format` | 166 files left unchanged |
| lint | guide | PASS | <1s | `poetry run ruff check src/ tests/` | All checks passed |
| typecheck | guide | PASS | ~3s | `poetry run mypy src/` | Success: no issues found in 25 source files |
| black | guide | PASS | ~1s | `poetry run black --check src/ tests/` | 52 files would be left unchanged |
| unit | guide | PASS | ~89s | `poetry run pytest tests/ --cov=src --cov-report=term-missing` | 346 passed, 91% coverage, no regression |
| integration | guide | FAIL | <1s | `poetry run pytest tests/ -m integration --cov=src --cov-report=term-missing` | Exit code 5 ("no tests collected") — 346 deselected, 0 selected. `tests/integration/` contains only `__init__.py`; confirmed via `git ls-tree main -- tests/integration` that **no integration test files exist on `main` either** — this is a pre-existing repo-wide gap, not introduced by this branch's diff (the diff touches only `src/mcp_connect/client/{client_info,managed,single_usage}.py` and `tests/test_user_agent_header.py`). |
| secrets | guide | PASS | ~5s | `make gitleaks` | "no leaks found" (v8.30.0, ~41.3MB scanned) |
| ui | guide | SKIPPED | — | (n/a) | no UI surface changed |

## Failure detail

```
collected 346 items / 346 deselected / 0 selected
=========================== 346 deselected in 0.28s ============================
```
Exit code: 5 (pytest's "no tests were collected"). No integration-marked test exists anywhere in the current test suite (only `tests/integration/__init__.py` is present); this predates this branch.

## Drift signal

no

## Resolution

Mechanical status is BLOCKED (integration gate exit 5). User reviewed and confirmed the integration-test gap is pre-existing and repo-wide (identical on `main`), unrelated to this diff, and out of scope for this ticket. Decision: proceed to Stage 7 with this gate accepted as a known pre-existing gap, not a regression.
