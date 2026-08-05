# Setup

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Runtime language |
| Poetry | 2.1.3 | Dependency management |
| Virtual environment | — | Isolated Python environment (MANDATORY) |

**Evidence**: `pyproject.toml`:14, `AGENTS.md`

---

## Virtual Environment

Poetry is configured to keep the environment in-project at `.venv/`, and **`poetry run <tool>`
resolves it without activation.** Verified 2026-07-31: `poetry run ruff check` from a clean shell
with no activation → exit 0, and `poetry env info --path` reports the in-project `.venv`.

```bash
# Works from a clean shell — no activation needed
poetry run pytest tests/
poetry run mypy src/

# Activation is needed only to invoke a tool binary directly, with no `poetry run` prefix
source .venv/bin/activate
pytest tests/
```

`source .venv/bin/activate && <cmd>` is shell syntax, not a command, so anything that runs
commands without a shell cannot execute it. Prefer the `poetry run` form everywhere.

**Verify the environment**:
```bash
poetry env info --path        # should end in /.venv inside this repository
poetry run python --version   # Python 3.12.x
```

**Evidence**: executed in this repository on 2026-07-31; `poetry install` created `.venv/` and
`poetry run` located it with no activation.

---

## Initial Setup

### 1. Clone Repository

```bash
git clone https://gitbud.epam.com/epm-cdme/codemie-mcp-connect-service
cd codemie-mcp-connect-service
```

### 2. Create Virtual Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
# With venv activated
poetry install
```

**What it does**: Installs all production and development dependencies from `poetry.lock`

**Evidence**: `AGENTS.md`, `README.md`:147-149

---

## Development Environment

### Directory Structure

Derive it; do not read it from a document.

```bash
# Top-level areas
git ls-files | awk -F/ 'NF>1{print $1"/"}' | sort -u

# The Python package
git ls-files 'src/**/*.py'
```

**Evidence**: both commands run against the tracked file list, so they cannot go stale.

### Configuration Files

| File | Purpose |
|---|---|
| `pyproject.toml` | Poetry dependencies, tool configs (pytest, mypy, black, ruff) |
| `poetry.lock` | Pinned dependency versions (54 packages) |
| `.env.example` | Environment variable template |
| `Makefile` | Gitleaks security scan |

**Evidence**: `AGENTS.md`

---

## Running the Application

### Development Server

```bash
# Activate venv first
source .venv/bin/activate

# Start dev server with auto-reload
poetry run uvicorn mcp_connect.main:app --reload
```

**Default**: http://localhost:8000 (or port from `PORT` env var)

**Evidence**: `AGENTS.md`, `CONTRIBUTING.md`:57-62

### With Environment Variables

Create `.env` file from template:

```bash
cp .env.example .env
# Edit .env with your values
```

Required variables:
```bash
ACCESS_TOKEN=<your-secret-token>    # Bearer auth token
PORT=3000                           # Server port
LOG_LEVEL=INFO                      # debug|info|warning|error|critical
LOG_FORMAT=json                     # json|text
```

**Evidence**: `CLAUDE.md`

---

## Helper Scripts

**Available via Poetry** (after activating venv):

| Command | What it does | Equivalent |
|---|---|---|
| `poetry run format` | Runs black formatter | `poetry run black src/ tests/` |
| `poetry run lint` | Runs ruff linter | `poetry run ruff check src/ tests/` |
| `poetry run typecheck` | Runs mypy type checker | `poetry run mypy src/` |
| `poetry run test` | Runs pytest | `poetry run pytest` |

**Source**: `pyproject.toml`:40-44

**Evidence**: `AGENTS.md`

---

## Installing Pre-commit Hooks

**One-time setup** (per development environment):

```bash
source .venv/bin/activate
poetry run pre-commit install
```

**What it does**: Installs git hooks that automatically run format/lint checks on commit

**Run manually** (all files):
```bash
poetry run pre-commit run --all-files
```

**Evidence**: `AGENTS.md`

---

## Common Commands

### Install/Update Dependencies

```bash
source .venv/bin/activate

# Install new package
poetry add <package-name>

# Install new dev dependency
poetry add --group dev <package-name>

# Update dependencies
poetry update

# Show installed packages
poetry show
```

### Run Tests

```bash
source .venv/bin/activate

# Unit tests only (default)
poetry run pytest

# Integration tests: none exist — this collects nothing and exits 5.
# See testing/testing-patterns.md § Integration Tests Only.
poetry run pytest tests/ -m integration

# With coverage report
poetry run pytest --cov=src --cov-report=term-missing
```

**Evidence**: `AGENTS.md`

### Type Checking

```bash
source .venv/bin/activate
poetry run mypy src/
```

**Must have zero errors** (strict mode enabled)

**Evidence**: `AGENTS.md`

### Code Formatting

```bash
source .venv/bin/activate

# Auto-format with black
poetry run black src/ tests/

# Auto-format with ruff
poetry run ruff format
```

**Evidence**: `AGENTS.md`

### Linting

```bash
source .venv/bin/activate

# Check for issues
poetry run ruff check src/ tests/

# Auto-fix issues
poetry run ruff check --fix src/ tests/
```

**Evidence**: `AGENTS.md`

---

## Environment Variables Reference

### Core Settings

| Variable | Default | Description |
|---|---|---|
| `ACCESS_TOKEN` | None | Bearer auth token (auth disabled if unset) |
| `PORT` | 3000 | Server port |
| `LOG_LEVEL` | INFO | debug \| info \| warning \| error \| critical |
| `LOG_FORMAT` | json | json \| text |
| `DEBUG_LOG_BRIDGE_PAYLOAD` | false | Log complete request/response payloads at debug level |

### MCP Client Settings

| Variable | Default | Description |
|---|---|---|
| `MCP_CONNECT_INIT_TIMEOUT` | 30000 | Client initialization timeout (milliseconds) |
| `MCP_CONNECT_DEFAULT_TIMEOUT` | 120000 | MCP method execution timeout (milliseconds) |
| `MCP_CONNECT_CLIENT_CACHE_TTL` | 300000 | Client cache TTL (milliseconds, 5 minutes) |
| `MCP_CONNECT_HTTP_TIMEOUT` | 30000 | HTTP transport timeout (milliseconds) |
| `MCP_CONNECT_SSE_READ_TIMEOUT` | 300000 | SSE transport read timeout (milliseconds) |

### Optional Settings

| Variable | Default | Description |
|---|---|---|
| `NGROK_AUTHTOKEN` | None | Ngrok tunnel authentication token (Docker deployment) |

**Evidence**: `AGENTS.md`, `CLAUDE.md`

---

## Troubleshooting

### Virtual Environment Issues

| Issue | Solution |
|---|---|
| `poetry: command not found` | Poetry is not installed on PATH — install it, or activate `.venv` if it was installed there |
| `ModuleNotFoundError` | Activate venv, then `poetry install` |
| Poetry uses the wrong environment | `poetry env info --path` must end in `/.venv` inside this repository |
| Python version mismatch | Recreate venv with Python 3.12+: `python3.12 -m venv .venv` |

### Dependency Issues

| Issue | Solution |
|---|---|
| `poetry.lock` out of sync | `poetry lock --no-update` to sync without upgrading |
| Dependency conflict | Check `poetry show --tree` for conflict source |
| Missing package | `poetry install` to install from lockfile |

### Development Server Issues

| Issue | Solution |
|---|---|
| Port already in use | Change `PORT` env var or kill process on port: `lsof -ti:3000 \| xargs kill` |
| Auth failures | Set `ACCESS_TOKEN` env var or leave unset to disable auth |
| Import errors | Verify venv activated and `poetry install` completed |

**Evidence**: `AGENTS.md`

---

## Next Steps

After setup:
1. Review [Architecture](architecture/architecture.md) to understand system design
2. Review [Quality Gates](quality-gates.md) before making changes
3. Review [Git Workflow](standards/git-workflow.md) before committing
4. Review [Testing](testing/testing-patterns.md) before writing tests
