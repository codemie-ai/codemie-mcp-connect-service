# Setup

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Runtime language |
| Poetry | 2.1.3 | Dependency management |
| Virtual environment | — | Isolated Python environment (MANDATORY) |

**Evidence**: `pyproject.toml`:14, `AGENTS.md`:42-54

---

## Critical: Virtual Environment Activation

**⚠️ MANDATORY: Always activate the virtual environment BEFORE running ANY Python or Poetry commands!**

```bash
# Activate virtual environment (REQUIRED for all Python/Poetry commands)
source .venv/bin/activate
```

**Why**: Ensures correct Python version, isolated dependencies, prevents system Python conflicts

**Verify activation**:
```bash
which python   # Should point to .venv/bin/python
which poetry   # Should point to .venv/bin/poetry
```

**NEVER run Poetry or Python commands without activating .venv first!**

**Evidence**: `AGENTS.md`:42-54, `CLAUDE.md`:18-22, `GEMINI.md`:23-30

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

**Evidence**: `AGENTS.md`:63, `README.md`:147-149

---

## Development Environment

### Directory Structure

```
/
├── src/mcp_connect/          # Main Python package
├── tests/                    # pytest test suite
├── docs/                     # Project documentation
├── scripts/                  # Helper scripts
├── deploy-templates/         # Deployment configs
├── pyproject.toml            # Poetry config + tool settings
├── poetry.lock               # Dependency lockfile
├── Dockerfile                # Container image
├── .env.example              # Environment template
└── README.md                 # User documentation
```

**Evidence**: `AGENTS.md`:128-178

### Configuration Files

| File | Purpose |
|---|---|
| `pyproject.toml` | Poetry dependencies, tool configs (pytest, mypy, black, ruff) |
| `poetry.lock` | Pinned dependency versions (54 packages) |
| `.env.example` | Environment variable template |
| `Makefile` | Gitleaks security scan |

**Evidence**: `AGENTS.md`:171-177

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

**Evidence**: `AGENTS.md`:66, `CONTRIBUTING.md`:57-62

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

**Evidence**: `CLAUDE.md`:86-103

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

**Evidence**: `AGENTS.md`:84-87

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

**Evidence**: `AGENTS.md`:116-124

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

# Integration tests only
poetry run pytest -m integration

# All tests
poetry run pytest -m ""

# With coverage report
poetry run pytest --cov=src --cov-report=term-missing
```

**Evidence**: `AGENTS.md`:69-71, `AGENTS.md`:322-336

### Type Checking

```bash
source .venv/bin/activate
poetry run mypy src/
```

**Must have zero errors** (strict mode enabled)

**Evidence**: `AGENTS.md`:73-74

### Code Formatting

```bash
source .venv/bin/activate

# Auto-format with black
poetry run black src/ tests/

# Auto-format with ruff
poetry run ruff format
```

**Evidence**: `AGENTS.md`:76-81

### Linting

```bash
source .venv/bin/activate

# Check for issues
poetry run ruff check src/ tests/

# Auto-fix issues
poetry run ruff check --fix src/ tests/
```

**Evidence**: `AGENTS.md`:79-81

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

**Evidence**: `AGENTS.md`:240-256, `CLAUDE.md`:86-103

---

## Troubleshooting

### Virtual Environment Issues

| Issue | Solution |
|---|---|
| `poetry: command not found` | Activate venv: `source .venv/bin/activate` |
| `ModuleNotFoundError` | Activate venv, then `poetry install` |
| Poetry installs to wrong location | Verify: `which poetry` should point to `.venv/bin/poetry` |
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

**Evidence**: `AGENTS.md`:42-54 (venv activation), `AGENTS.md`:63 (poetry install)

---

## Next Steps

After setup:
1. Review [Architecture](.ai-run/guides/architecture/architecture.md) to understand system design
2. Review [Quality Gates](.ai-run/guides/quality-gates.md) before making changes
3. Review [Git Workflow](.ai-run/guides/standards/git-workflow.md) before committing
4. Review [Testing](.ai-run/guides/testing/testing-patterns.md) before writing tests
