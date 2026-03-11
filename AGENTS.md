# AGENTS.md

This file provides guidance to AI agents (OpenAI GPT, Anthropic Claude, and others) when working with code in this repository.

## 🚀 Project Overview

**CodeMie MCP Connect Service** - Production FastAPI-based bridge service that enables cloud-based AI platforms to interact with local MCP servers through HTTP/HTTPS to stdio protocol translation.

### Technology Stack

**Core:**
- **Language**: Python 3.12+
- **Web Framework**: FastAPI 0.121.0+
- **ASGI Server**: Uvicorn with uvloop
- **Validation**: Pydantic 2.12.0+
- **MCP SDK**: Official `mcp` Python SDK (v1.21.0+)
- **Logging**: python-json-logger (structured JSON logging)
- **Dependency Management**: Poetry 2.1.3

**Development Tools:**
- pytest + pytest-asyncio (testing)
- mypy (strict type checking)
- black (code formatting)
- ruff (linting)
- pre-commit (git hooks)

### Key Features

- **HTTP to stdio Protocol Translation**: Converts HTTP/HTTPS requests to MCP stdio communication
- **Client Caching**: 5-minute TTL with ping-based validation for optimal performance
- **Single-Usage Mode**: Immediate cleanup for one-time operations
- **Multi-Transport Support**: stdio, Streamable HTTP, SSE (WebSocket intentionally NOT supported)
- **Process Output Capture**: Both stdout and stderr
- **Structured Logging**: JSON logging with context propagation and sensitive data masking
- **Environment/Header Substitution**: Dynamic variable substitution in requests

---

## Essential Commands

### CRITICAL: Virtual Environment Activation

**⚠️ MANDATORY: Always activate the virtual environment BEFORE running any Python or Poetry commands!**

```bash
# Activate virtual environment (REQUIRED for all Python/Poetry commands)
source .venv/bin/activate

# Then run Poetry commands
poetry install
poetry run pytest
```

**NEVER run Poetry or Python commands without activating .venv first!**

### Python Development Commands

```bash
# ALWAYS activate venv first
source .venv/bin/activate

# Install dependencies
poetry install

# Run the application
poetry run uvicorn mcp_connect.main:app --reload

# Run tests
poetry run pytest                    # Unit tests only
poetry run pytest -m integration     # Integration tests only
poetry run pytest --cov=src          # With coverage report

# Run type checking
poetry run mypy src/

# Format code
poetry run black src/ tests/

# Lint code
poetry run ruff check src/ tests/
ruff format                          # Auto-fix formatting

# Helper scripts (after activating venv)
poetry run format      # Runs black
poetry run lint        # Runs ruff check
poetry run typecheck   # Runs mypy
poetry run test        # Runs pytest
```

### ⚠️ MANDATORY: Pre-Commit Quality Check

**CRITICAL: Run this comprehensive check before committing ANY code changes!**

All checks MUST pass (exit code 0) before committing, marking code as ready for review, or creating pull requests.

```bash
# Comprehensive quality check (MUST pass before commit)
source .venv/bin/activate && \
poetry run ruff format && \
poetry run ruff check && \
poetry run mypy src/ && \
poetry run black --check src/ tests/ && \
poetry run pytest tests/ --cov=src --cov-report=term-missing && \
poetry run pytest tests/ -m integration --cov=src --cov-report=term-missing
```

**What each step does:**
1. `ruff format` - Auto-formats code (fixes formatting issues)
2. `ruff check` - Lints code for style and error issues
3. `mypy src/` - Type checks with strict mode (must have zero errors)
4. `black --check src/ tests/` - Verifies black formatting compliance
5. `pytest` - Runs all unit tests with coverage
6. `pytest -m integration` - Runs integration tests with coverage

### Pre-commit Hooks

```bash
# Install pre-commit hooks (once per development environment)
source .venv/bin/activate
poetry run pre-commit install

# Run all hooks manually
poetry run pre-commit run --all-files
```

---

## Project Structure

```
/
├── src/
│   └── mcp_connect/              # Main Python package
│       ├── __init__.py           # Package initialization
│       ├── main.py               # FastAPI app entry point
│       ├── server/               # HTTP server components
│       │   ├── __init__.py
│       │   ├── routes.py         # FastAPI routes (/health, /bridge)
│       │   └── middleware.py    # Auth, logging, error handling
│       ├── client/               # MCP client management
│       │   ├── __init__.py
│       │   ├── manager.py        # Client creation and caching
│       │   ├── managed.py        # ManagedClient (cached, ping-validated)
│       │   ├── single_usage.py   # SingleUsageClient (no cache)
│       │   ├── methods.py        # MCP protocol method execution
│       │   ├── cache.py          # Async TTL cache implementation
│       │   └── types.py          # Type definitions
│       ├── models/               # Pydantic data models
│       │   ├── __init__.py
│       │   └── request.py        # Request/response schemas
│       └── utils/                # Shared utilities
│           ├── __init__.py
│           ├── logger.py         # Structured JSON logging
│           ├── context.py        # Context propagation
│           ├── masking.py        # Sensitive data masking
│           ├── substitution.py   # Env/header substitution
│           ├── process.py        # Process output capture
│           └── errors.py         # Custom exceptions
│
├── tests/                        # pytest test suite
│   ├── __init__.py
│   ├── conftest.py               # Shared fixtures
│   ├── test_*.py                 # Unit tests
│   └── integration/              # Integration tests
│       └── test_*.py
│
├── docs/                         # Project documentation
├── scripts/                      # Helper scripts
├── deploy-templates/             # Deployment configurations
│
├── pyproject.toml                # Poetry config + tool settings
├── poetry.lock                   # Dependency lockfile
├── Dockerfile                    # Container image
├── .env.example                  # Environment template
├── .dockerignore
├── .gitignore
└── README.md                     # User documentation
```

---

## Architecture Overview

### Core Components

1. **HTTP Server** (`server/`)
   - FastAPI with `/health` and `/bridge` endpoints
   - Bearer token authentication middleware
   - Structured logging middleware
   - Global error handling

2. **MCP Client Manager** (`client/manager.py`)
   - Creates and manages MCP client connections
   - Handles stdio, Streamable HTTP, and SSE transports
   - Implements client caching with TTL and ping validation

3. **Client Types**
   - **ManagedClient** (`client/managed.py`): Cached clients with ping validation
   - **SingleUsageClient** (`client/single_usage.py`): One-time use, immediate cleanup

4. **Client Cache** (`client/cache.py`)
   - Async TTL cache (default: 5 minutes)
   - Automatic cleanup of expired entries
   - Ping-based validation before reuse

5. **Request/Response Models** (`models/`)
   - Pydantic models for type-safe API contracts
   - Environment and header substitution support
   - Single-usage mode flag

6. **Utilities** (`utils/`)
   - Structured JSON logging with context propagation
   - Sensitive data masking (tokens, credentials)
   - Environment variable substitution
   - Process stdout/stderr capture

### Transport Support

- ✅ **stdio**: Local command execution (primary use case)
- ✅ **Streamable HTTP**: Remote MCP servers over HTTP/HTTPS
- ✅ **SSE**: Deprecated but supported for backward compatibility
- ❌ **WebSocket**: NOT supported (not in MCP spec, not in Python SDK)

### Client Modes

**Default Caching Mode:**
- Clients cached and reused for same configuration
- Ping validation before reuse
- 5-minute TTL (configurable via `MCP_CONNECT_CLIENT_CACHE_TTL`)
- Best for repeated operations

**Single-Usage Mode** (`single_usage: true`):
- Fresh client per request
- Immediate cleanup after completion
- No caching overhead
- Best for one-time operations, batch processing, resource-constrained environments

---

## Environment Variables

```bash
# Required
ACCESS_TOKEN=<bearer-token>              # Authentication token

# Server Configuration
PORT=3000                                # Server port (default: 3000)
LOG_LEVEL=INFO                           # debug, info, warn, error (default: INFO)

# MCP Client Configuration
MCP_CONNECT_DEFAULT_TIMEOUT=60000        # Timeout in milliseconds (default: 60000)
MCP_CONNECT_CLIENT_CACHE_TTL=300000      # Cache TTL in milliseconds (default: 300000 = 5 min)

# Optional
NGROK_AUTH_TOKEN=<token>                 # For ngrok tunneling (Docker deployment)
```

---

## Development Guidelines

### Code Style & Conventions

**Type Hints:**
- Use built-in generics: `list[...]`, `dict[...]` (NOT `typing.List`/`typing.Dict`)
- Use union syntax: `str | None` (NOT `typing.Optional[str]`)
- All functions must have type hints (enforced by mypy strict mode)

**Async/Await:**
- All I/O operations must be async
- Use `async with` for context managers
- Use `asyncio.create_task()` for concurrent operations

**Error Handling:**
- Use custom exceptions from `utils.errors`
- Always include context in error messages
- Log errors with appropriate severity

**Logging:**
- Use structured JSON logging via `utils.logger`
- Include request context via `utils.context`
- Mask sensitive data via `utils.masking`

**Documentation Rules:**
- ❌ **DO NOT create summary documents** - Not needed in this project
- ❌ **DO NOT create validation report documents** - Not needed
- ✅ **DO write docstrings** for public functions and classes
- ✅ **DO update README.md** for user-facing changes
- ✅ **Token-efficient** - Maximum information density, minimum verbosity

### API Documentation & Best Practices (MANDATORY)

**⚠️ ALWAYS use context7 MCP tool when implementing features!**

**Before implementing any library feature** (FastAPI, Pydantic, MCP SDK, pytest, etc.):

1. Use `mcp__context7__resolve-library-id` to find the library ID
2. Use `mcp__context7__get-library-docs` with relevant topic to get current documentation
3. Review latest API patterns, best practices, and examples

**Examples:**
- Implementing FastAPI endpoint → Get FastAPI docs for "routing", "dependencies", "responses"
- Using Pydantic models → Get Pydantic docs for "models", "validation", "configuration"
- Writing async tests → Get pytest-asyncio docs for "fixtures", "markers"
- MCP protocol → Get MCP Python SDK docs for "clients", "transports", "protocol"

**Why this matters:** Ensures implementation uses latest stable APIs, follows current best practices, and avoids deprecated patterns.

### Testing Requirements

**Test Organization:**
- Unit tests: `tests/test_*.py`
- Integration tests: `tests/integration/test_*.py` (marked with `@pytest.mark.integration`)
- Shared fixtures: `tests/conftest.py`

**Coverage Requirements:**
- All new code must have tests
- Critical paths require 100% coverage
- Run coverage report: `pytest --cov=src --cov-report=term-missing`

**Running Tests:**
```bash
source .venv/bin/activate

# Unit tests only (default)
poetry run pytest

# Integration tests only
poetry run pytest -m integration

# All tests
poetry run pytest -m ""

# With coverage
poetry run pytest --cov=src --cov-report=term-missing
```

### Type Checking

**Mypy Configuration:**
- Strict mode enabled
- Zero errors required for commit
- MCP SDK imports ignored (no type stubs)

**Running Type Checks:**
```bash
source .venv/bin/activate
poetry run mypy src/
```

---

## Important Notes for AI Agents

### General Guidelines

- **Context**: This is a production service - stability and reliability are critical
- **Token efficiency**: Maximum information density, minimum verbosity in all outputs
- **Virtual environment**: ALWAYS activate `.venv` before Python/Poetry commands
- **Quality gates**: All quality checks must pass before commit/PR
- **API documentation**: ALWAYS use context7 MCP tool for library implementation
- **Testing**: Write tests for all new features and bug fixes
- **Type safety**: Maintain mypy strict mode compliance
- **Logging**: Use structured JSON logging with context propagation

### Key Principles

1. **API Parity**: Maintain exact API contract compatibility
2. **Performance**: Keep latency ≤ 100ms for cached clients
3. **Reliability**: Comprehensive error handling and logging
4. **Type Safety**: Strict type checking with mypy
5. **Test Coverage**: All critical paths must be tested
6. **Clean Code**: Follow style guide and pass all quality checks

### When Adding Features

1. Use context7 to get latest library documentation
2. Write tests first (TDD approach recommended)
3. Implement feature with proper type hints
4. Run quality check suite
5. Update documentation if user-facing
6. Verify with integration tests

### When Fixing Bugs

1. Write failing test that reproduces bug
2. Fix bug with proper error handling
3. Ensure test passes
4. Run full quality check suite
5. Verify no regressions in related functionality
