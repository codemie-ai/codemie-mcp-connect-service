# Quality Gates

All quality checks MUST pass (exit code 0) before committing code or creating merge requests.

## Comprehensive Pre-Commit Check

**Run**: 
```bash
source .venv/bin/activate && \
poetry run ruff format && \
poetry run ruff check && \
poetry run mypy src/ && \
poetry run black --check src/ tests/ && \
poetry run pytest tests/ --cov=src --cov-report=term-missing && \
poetry run pytest tests/ -m integration --cov=src --cov-report=term-missing && \
make gitleaks
```

**Pass**: All commands exit 0
**Fail**: Any command exits non-zero — fix issues and re-run
**Source**: `AGENTS.md`:97-105, `CONTRIBUTING.md`:67-74

---

## Format (ruff format)

**Run**: `source .venv/bin/activate && poetry run ruff format`

**Pass**: Files auto-formatted, exits 0
**Fail**: Should not fail — ruff format auto-fixes
**Auto-fix**: Command itself is the fix

**What it does**: Auto-formats Python code per ruff configuration (line length 120, Python 3.12 target)
**Config**: `pyproject.toml`:77-79

---

## Lint (ruff check)

**Run**: `source .venv/bin/activate && poetry run ruff check src/ tests/`

**Pass**: No lint errors, exits 0
**Fail**: Outputs error list with file:line, exits non-zero
**Auto-fix**: `poetry run ruff check --fix src/ tests/` (fixes auto-fixable issues)

**What it does**: Lints code for style issues, unused imports, undefined variables, complexity
**Config**: `pyproject.toml`:77-79 (line length 120, target py312)
**Evidence**: `AGENTS.md`:79-81, `pyproject.toml`:77-79

---

## Type Check (mypy)

**Run**: `source .venv/bin/activate && poetry run mypy src/`

**Pass**: Zero type errors, exits 0
**Fail**: Outputs type error list, exits non-zero
**Auto-fix**: Manual — add type hints, fix type mismatches per error messages

**What it does**: Strict type checking — verifies all functions have type hints, all types are consistent
**Config**: `pyproject.toml`:61-70 (strict mode enabled, zero errors required)
**Skip if**: Never skip — strict mypy is a hard requirement

**Evidence**: `AGENTS.md`:73-74, `pyproject.toml`:61-70

---

## Format Verification (black --check)

**Run**: `source .venv/bin/activate && poetry run black --check src/ tests/`

**Pass**: All files comply with black formatting, exits 0
**Fail**: Lists files that would be reformatted, exits non-zero
**Auto-fix**: `poetry run black src/ tests/` (applies black formatting)

**What it does**: Verifies code matches black's formatting standard (line length 120)
**Config**: `pyproject.toml`:72-75
**Evidence**: `AGENTS.md`:76-77, `pyproject.toml`:72-75

---

## Unit Tests (pytest)

**Run**: `source .venv/bin/activate && poetry run pytest tests/ --cov=src --cov-report=term-missing`

**Pass**: All unit tests pass, coverage meets requirements, exits 0
**Fail**: Test failures or coverage below threshold — outputs failure details
**Auto-fix**: Fix failing tests, add tests for uncovered code

**What it does**: Runs unit tests (excludes integration marker), reports coverage with missing lines
**Config**: `pyproject.toml`:50-59 (asyncio auto mode, integration tests excluded by default)
**Coverage**: Critical paths require 100% coverage, all new code must be tested

**Evidence**: `AGENTS.md`:69-71, `pyproject.toml`:50-59

---

## Integration Tests (pytest -m integration)

**Run**: `source .venv/bin/activate && poetry run pytest tests/ -m integration --cov=src --cov-report=term-missing`

**Pass**: All integration tests pass, exits 0
**Fail**: Test failures — outputs failure details
**Auto-fix**: Fix failing tests

**What it does**: Runs tests marked with `@pytest.mark.integration` — tests with external dependencies, network I/O, subprocess execution
**Config**: `pyproject.toml`:56 (integration marker definition)
**Organization**: Integration tests in `tests/integration/test_*.py`

**Evidence**: `AGENTS.md`:70, `pyproject.toml`:56-57

---

## Secret Scan (gitleaks)

**Run**: `make gitleaks`

**Pass**: No secrets detected, exits 0
**Fail**: Outputs detected secrets with file:line, exits non-zero
**Auto-fix**: Remove secrets from code, use environment variables or secret management

**What it does**: Scans repository for accidentally committed secrets (tokens, passwords, API keys)
**Implementation**: `Makefile`:1-4 (Docker-based gitleaks v8.30.0)
**Skip if**: Never skip for commits — prevents secret leaks

**Evidence**: `Makefile`:1-4, `AGENTS.md`:104

---

## Additional Quality Commands

### Pre-commit Hooks

**Install** (once per environment):
```bash
source .venv/bin/activate
poetry run pre-commit install
```

**Run manually**:
```bash
poetry run pre-commit run --all-files
```

**What it does**: Runs configured git hooks (format, lint checks) automatically on commit
**Evidence**: `AGENTS.md`:116-124

### Helper Scripts

**Available via Poetry** (after activating venv):
- `poetry run format` → runs black
- `poetry run lint` → runs ruff check  
- `poetry run typecheck` → runs mypy
- `poetry run test` → runs pytest

**Source**: `pyproject.toml`:40-44
**Evidence**: `AGENTS.md`:84-87

---

## Validation Workflow

**Before every commit:**
1. Activate virtual environment: `source .venv/bin/activate`
2. Run comprehensive pre-commit check (all gates above)
3. Verify all commands exit 0
4. Only commit if all checks pass

**Before every MR:**
1. All commits must have passed quality checks
2. Run full check one final time on merged main
3. Verify CI pipeline passes

**Evidence**:
- `AGENTS.md`:90-115 — comprehensive check is mandatory before commit/PR
- `CONTRIBUTING.md`:65-76 — quality check required before PR
- `pyproject.toml`:40-80 — tool configurations and commands
- `Makefile`:1-4 — gitleaks security scan
