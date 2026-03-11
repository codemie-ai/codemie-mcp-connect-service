# CLAUDE.md

Guidance for Claude Code when working with this repository.

## Project Overview

**CodeMie MCP Connect Service** - FastAPI bridge enabling cloud AI platforms to interact with local MCP servers via HTTP/HTTPS to stdio protocol translation.

**Stack:** Python 3.12+ | FastAPI 0.121.0+ | Uvicorn | Pydantic 2.12.0+ | MCP Python SDK v1.21.0+ | python-json-logger | Poetry 2.1.3
**Dev Tools:** pytest + pytest-asyncio | mypy (strict) | black | ruff | pre-commit

**Features:** HTTP-to-stdio translation | Client caching (5min TTL, ping validation) | Single-usage mode | Multi-transport (stdio, HTTP, SSE) | Structured JSON logging | Sensitive data masking | Env/header substitution

---

## Essential Commands

### Virtual Environment (MANDATORY)
```bash
# ALWAYS activate before ANY Python/Poetry command
source .venv/bin/activate
```

### Development
```bash
source .venv/bin/activate

poetry install                               # Install dependencies
poetry run uvicorn mcp_connect.main:app --reload  # Dev server
poetry run pytest                            # Unit tests
poetry run pytest -m integration             # Integration tests
poetry run pytest --cov=src                  # With coverage
poetry run mypy src/                         # Type check
poetry run black src/ tests/                 # Format
poetry run ruff check src/ tests/            # Lint
```

### Pre-Commit Quality Check (REQUIRED before commit/PR)
```bash
source .venv/bin/activate && \
poetry run ruff format && \
poetry run ruff check && \
poetry run mypy src/ && \
poetry run black --check src/ tests/ && \
poetry run pytest tests/ --cov=src --cov-report=term-missing && \
poetry run pytest tests/ -m integration --cov=src --cov-report=term-missing
```

All checks MUST pass (exit code 0).

---

## Project Structure

```
src/mcp_connect/
├── main.py              # FastAPI app entry point
├── server/              # HTTP server (routes, middleware, auth)
├── client/              # MCP client management (manager, cache, methods, types)
│   ├── managed.py       # Cached clients with ping validation
│   └── single_usage.py  # One-time use, immediate cleanup
├── models/              # Pydantic schemas
└── utils/               # Logger, context, masking, substitution, process, errors

tests/                   # pytest suite (conftest.py, test_*.py, integration/)
```

---

## Architecture

**HTTP Server:** FastAPI `/health` + `/bridge` endpoints | Bearer auth | Structured logging | Global error handling
**Client Manager:** Creates/caches MCP clients | Handles stdio/HTTP/SSE transports | TTL + ping validation
**Client Modes:**
- Default (cached): Reused for same config, 5min TTL, ping-validated
- Single-usage (`single_usage: true`): Fresh per request, immediate cleanup

**Transports:** stdio ✅ | Streamable HTTP ✅ | SSE ✅ | WebSocket ❌

---

## Environment Variables

```bash
# Core
ACCESS_TOKEN=<token>                         # Bearer auth (disabled if unset)
PORT=3000                                    # Server port
LOG_LEVEL=INFO                               # debug|info|warning|error|critical
LOG_FORMAT=json                              # json|text
DEBUG_LOG_BRIDGE_PAYLOAD=false               # Log complete payload at debug level

# MCP Client
MCP_CONNECT_INIT_TIMEOUT=30000               # Initialization timeout (ms)
MCP_CONNECT_DEFAULT_TIMEOUT=120000           # Method timeout (ms)
MCP_CONNECT_CLIENT_CACHE_TTL=300000          # Cache TTL (ms)
MCP_CONNECT_HTTP_TIMEOUT=30000               # HTTP timeout (ms)
MCP_CONNECT_SSE_READ_TIMEOUT=300000          # SSE timeout (ms)

# Optional
NGROK_AUTHTOKEN=<token>                      # Ngrok tunnel
```

---

## Development Guidelines

### Code Conventions
- **Type hints:** `list[...]`, `dict[...]`, `str | None` (NOT typing.List/Optional)
- **Async:** All I/O async | `async with` for context managers | `asyncio.create_task()` for concurrency
- **Errors:** Custom exceptions from `utils.errors` | Always include context | Log with severity
- **Logging:** Structured JSON via `utils.logger` | Context from `utils.context` | Mask sensitive via `utils.masking`
- **Docs:** Write docstrings for public functions | Update README.md for user-facing changes | NO summary/validation docs

### API Documentation (MANDATORY)
Before implementing library features (FastAPI, Pydantic, MCP SDK, pytest):
1. `mcp__context7__resolve-library-id` to find library ID
2. `mcp__context7__get-library-docs` with topic for current docs
3. Review latest API patterns and best practices

### Testing
- Unit tests: `tests/test_*.py`
- Integration: `tests/integration/test_*.py` with `@pytest.mark.integration`
- Fixtures: `tests/conftest.py`
- Coverage: All new code tested | Critical paths 100%
- Run: `pytest --cov=src --cov-report=term-missing`

### Type Checking
- Mypy strict mode | Zero errors required | MCP SDK imports ignored

---

## Key Principles

1. **API Parity:** Maintain exact API contract compatibility
2. **Performance:** Latency ≤ 100ms for cached clients
3. **Reliability:** Comprehensive error handling + logging
4. **Type Safety:** Strict mypy compliance
5. **Test Coverage:** All critical paths tested
6. **Clean Code:** Pass all quality checks

### When Adding Features
1. Use context7 for latest library docs
2. Write tests first (TDD)
3. Implement with type hints
4. Run quality checks
5. Update docs if user-facing
6. Verify with integration tests

### When Fixing Bugs
1. Write failing test reproducing bug
2. Fix with proper error handling
3. Verify test passes
4. Run full quality checks
5. Check for regressions

---

## Critical Reminders

- **Virtual env:** ALWAYS activate `.venv` before Python/Poetry commands
- **Quality gates:** All checks MUST pass before commit/PR
- **API docs:** ALWAYS use context7 MCP tool for library implementation
- **Production service:** Stability and reliability are critical
- **Token efficiency:** Maximum information density, minimum verbosity
