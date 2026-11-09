# QA gates — EPMCDME-14217 (codemie-mcp-connect-service)

Branch `EPMCDME-14217_expose-server-instructions`, base `main`.
This repository has no CI: every gate below was run by hand, as
`.ai-run/guides/quality-gates.md` requires.

| # | Gate | Command | Result |
|---|------|---------|--------|
| 1 | Lock consistency | `poetry check --lock` | PASS (only the pre-existing `[tool.poetry.authors]` deprecation warnings) |
| 2 | Format | `poetry run ruff format` | PASS — all files already formatted |
| 3 | Lint | `poetry run ruff check` | PASS — all checks passed |
| 4 | Type check | `poetry run mypy src/` | PASS — no issues in 26 source files, `--strict` |
| 5 | Format verify | `poetry run black --check src/ tests/` | PASS — 58 files unchanged |
| 6 | Unit tests | `poetry run pytest tests/ --cov=src --cov-report=term-missing` | PASS — 382 passed, 1 deselected, coverage 92% |
| 7 | Secret scan | `make gitleaks` | PASS — no leaks found |
| 8 | Integration tests | `poetry run pytest tests/ -m integration` | PASS — 1 passed (real FastMCP server over stdio) |

Gate 8 is new. It was added in this change because the only test that exercises
real MCP SDK types is excluded from the default run by
`addopts = "-m 'not integration'"`, and no CI runs it either — so without an
explicit gate that coverage would never run again after the author's local pass.

## Test-first evidence

Every task was driven RED before GREEN in the session transcript. Two RED states
are worth naming because they prove the assertions have teeth rather than
merely passing:

- The integration test was re-run with `attach_server_instructions` neutralized:
  `KeyError: 'instructions'`. It fails against a real handshake when the feature
  is absent.
- The three-transport parametrization was verified by reverting each of the six
  transport bodies one at a time. Each revert failed exactly one parametrization
  — so no body is covered only incidentally by another.

## Not covered

- No end-to-end run against the CodeMie backend: `MCP_CONNECT_URL` is not set in
  the local compose stack, so the paired backend MR is the first place the full
  chain can be exercised.
- The managed (pooled) path has no real-handshake test; it is covered by fakes
  plus the mutation proof above. The integration test drives the single-usage
  stdio path only.
