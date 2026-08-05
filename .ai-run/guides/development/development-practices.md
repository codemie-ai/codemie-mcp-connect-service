# Development Practices

## Type Hints

### Modern Python 3.12 Syntax

| Avoid (old typing module) | Prefer (built-in generics) |
|---|---|
| `from typing import List, Dict, Optional` | `list[...]`, `dict[...]`, `str \| None` |
| `List[str]`, `Dict[str, int]`, `Optional[str]` | `list[str]`, `dict[str, int]`, `str \| None` |

**Why**: Python 3.12+ supports built-in generic syntax — cleaner, no imports needed
**Config**: `pyproject.toml`:61-70 (strict mode, `disallow_untyped_defs = true`)
**Evidence**: `AGENTS.md`

### Requirements

All functions MUST have type hints (enforced by mypy strict mode). See `AGENTS.md`, `pyproject.toml`:66

---

## Async/Await Patterns

### All I/O Must Be Async

| Avoid (blocking) | Prefer (async) |
|---|---|
| `open(file, 'r').read()` | `async with aiofiles.open(...) as f: await f.read()` |
| `requests.get(url)` | `async with httpx.AsyncClient() as client: await client.get(url)` |
| `subprocess.run(cmd)` | `await asyncio.create_subprocess_exec(...)` |

**Why**: FastAPI is async — blocking I/O blocks event loop
**Evidence**: `AGENTS.md`

### Key Patterns

- Use `async with` for async context managers — see `AGENTS.md`
- Use `asyncio.create_task()` for concurrent execution — see `AGENTS.md`

---

## Error Handling

### Custom Exceptions

Use domain-specific exceptions from `utils/errors.py`:

| Avoid | Prefer |
|---|---|
| `raise Exception("Client failed")` | `raise MCPClientError("...", context={...})` |
| `raise ValueError("Invalid input")` | `raise ValidationError("...", details=...)` |

**Why**: Typed exceptions enable specific handling, context aids debugging
**Evidence**: `AGENTS.md`, `src/mcp_connect/utils/errors.py`

### Always Include Context

Include relevant context in error messages (config, state, error details) — see `AGENTS.md`

### Log Errors

Log with appropriate severity before re-raising — see `AGENTS.md`

---

## Logging

### Structured JSON Logging

Use `utils/logger.py` for all logging — outputs parseable JSON for log aggregators
**Evidence**: `AGENTS.md`

### Request Context Propagation

Use `utils/context.py` to propagate request context through call stack — enables tracing single request
**Evidence**: `AGENTS.md`

### Sensitive Data Masking

Use `utils/masking.py` to mask secrets in logs (tokens, passwords, API keys)
**Evidence**: `AGENTS.md`

---

## API Documentation Mandate

### ALWAYS Use context7 MCP Tool

**⚠️ MANDATORY: Before implementing ANY library feature** (FastAPI, Pydantic, MCP SDK, pytest):

1. `mcp__context7__resolve-library-id` — find library ID
2. `mcp__context7__get-library-docs` — get current docs for topic
3. Review latest API patterns, best practices, examples

**Why**: Ensures latest stable APIs, avoids deprecated patterns
**Evidence**: `AGENTS.md`, `CLAUDE.md`

### Query Examples

| Task | context7 Query |
|---|---|
| FastAPI endpoint | "routing", "dependencies", "responses" |
| Pydantic models | "models", "validation", "configuration" |
| Async tests | "fixtures", "markers" |
| MCP protocol | "clients", "transports", "protocol" |

**Evidence**: `AGENTS.md`

---

## Documentation Standards

### Write Docstrings

For public functions and classes only — see `AGENTS.md`

### Prohibited

- ❌ Summary documents after implementation
- ❌ Validation report documents  
- ❌ Generic status reports

**Allowed**: Update README.md for user-facing changes, inline code docstrings
**Why**: Token efficiency — maximum information density, minimum verbosity
**Evidence**: `AGENTS.md`

---

## Code Style

| Tool | Command | Config | Evidence |
|---|---|---|---|
| **Black** | `poetry run black src/ tests/` | `pyproject.toml`:72-75 (line length 120) | `AGENTS.md` |
| **Ruff** | `poetry run ruff check src/ tests/` | `pyproject.toml`:77-79 (line length 120, py312) | `AGENTS.md` |

---

## Development Workflow

### Test-Driven Development (TDD)

**Recommended for all features and bugs:**

1. Use context7 for latest library docs
2. Write failing test specifying behavior
3. Implement with proper type hints
4. Run quality check suite
5. Update docs if user-facing
6. Verify with integration tests

**Evidence**: `AGENTS.md`

### Bug Fix Workflow

1. Write failing test reproducing bug
2. Fix with proper error handling
3. Ensure test passes
4. Run full quality check
5. Verify no regressions

**Evidence**: `AGENTS.md`

---

## Key Principles

| Principle | Description | Evidence |
|---|---|---|
| **API Parity** | Maintain exact API contract compatibility | `AGENTS.md` |
| **Performance** | Latency ≤ 100ms for cached clients | `AGENTS.md` |
| **Reliability** | Comprehensive error handling + logging | `AGENTS.md` |
| **Type Safety** | Strict mypy compliance — zero errors | `AGENTS.md` |
| **Test Coverage** | All critical paths tested | `AGENTS.md` |
| **Clean Code** | Pass all quality checks before commit | `AGENTS.md` |

---

## Production Service Context

**This is a production service** — stability and reliability are critical.

| Impact | Practice |
|---|---|
| Downtime affects cloud platforms | Comprehensive testing before deploy |
| Logs feed incident response | Structured logging with context |
| Must be backward compatible | API contract compliance |
| Performance SLA: ≤ 100ms | Profile changes, monitor cache hit rate |

**Evidence**: `AGENTS.md`

---

## Token Efficiency

**Maximum information density, minimum verbosity** in all outputs.

| Avoid | Prefer |
|---|---|
| Multi-paragraph explanations | Concise bullet points |
| Verbose commit messages | `EPMCDME-xxx: Action and description` (< 72 chars) |
| Redundant documentation | Single source of truth |

**Evidence**: `AGENTS.md`

---

## Common Implementation Patterns

Always use context7 for current best practices before implementing. Key patterns:

### Environment Variables

```python
import os
from dotenv import load_dotenv

load_dotenv()
access_token = os.getenv("ACCESS_TOKEN")
```

### Pydantic Models

```python
from pydantic import BaseModel, Field

class MCPConfig(BaseModel):
    command: str | None = None
    timeout_ms: int = Field(default=60000, ge=1000)
```

### FastAPI Routes

```python
from fastapi import APIRouter, Depends

@router.post("/bridge")
async def bridge(request: MCPRequest, client: MCPClient = Depends(get_client)):
    return await client.call_method(request.method, request.params)
```

---

## Next Steps

- [Quality Gates](../quality-gates.md) — full pre-commit checklist
- [Testing](../testing/testing-patterns.md) — TDD workflow
- [Architecture](../architecture/architecture.md) — system design
- `src/mcp_connect/` — implementation examples
