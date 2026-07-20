# Architecture

## System Overview

**CodeMie MCP Connect Service** is a production FastAPI bridge that translates HTTP/HTTPS requests to MCP (Model Context Protocol) stdio/HTTP/SSE communication, enabling cloud-based AI platforms to interact with local MCP servers.

**Key Characteristics**:
- Single-purpose service: protocol translation only
- Async/await throughout (Python 3.12+ with uvloop)
- Client caching with TTL + ping validation (5-minute default)
- Structured JSON logging with sensitive data masking
- Bearer token authentication

**Evidence**: `README.md`:31-43, `AGENTS.md`:8-36

---

## Core Components

### 1. HTTP Server (`src/mcp_connect/server/`)

**Purpose**: FastAPI application with authentication, logging middleware, and global error handling

**Structure**:
- `routes.py` — `/health` and `/bridge` endpoints
- `middleware.py` — Bearer token auth, structured logging, error handling

**Key Patterns**:
- Bearer auth via `ACCESS_TOKEN` env var (auth disabled if unset)
- Structured logging middleware on every request
- Global exception handler for MCP errors

**Evidence**: `AGENTS.md`:184-190, `src/mcp_connect/server/`

---

### 2. MCP Client Manager (`src/mcp_connect/client/manager.py`)

**Purpose**: Creates and manages MCP client connections with caching and transport abstraction

**Responsibilities**:
- Detect transport type (stdio/HTTP/SSE) from request config
- Create MCP clients for detected transport
- Cache clients by config hash (default mode)
- Return fresh clients for single-usage mode

**Transport Support**:
- ✅ stdio (local command execution)
- ✅ Streamable HTTP (remote MCP servers)
- ✅ SSE (deprecated, backward compatibility)
- ❌ WebSocket (intentionally not supported)

**Evidence**: `AGENTS.md`:192-195, `src/mcp_connect/client/manager.py`

---

### 3. Client Types

#### ManagedClient (`src/mcp_connect/client/managed.py`)

**Purpose**: Cached client with ping validation before reuse

**Lifecycle**:
1. Created on first request with given config
2. Cached for 5 minutes (configurable via `MCP_CONNECT_CLIENT_CACHE_TTL`)
3. Ping validation before reuse
4. Automatic cleanup on TTL expiry

**Best for**: Repeated operations against the same MCP server

**Evidence**: `AGENTS.md`:197-198, `src/mcp_connect/client/managed.py`

#### SingleUsageClient (`src/mcp_connect/client/single_usage.py`)

**Purpose**: One-time client with immediate cleanup

**Lifecycle**:
1. Created fresh per request
2. Used once
3. Cleaned up immediately after completion

**Best for**: One-time operations, batch processing, resource-constrained environments

**Evidence**: `AGENTS.md`:199, `src/mcp_connect/client/single_usage.py`

---

### 4. Client Cache (`src/mcp_connect/client/cache.py`)

**Purpose**: Async TTL cache with automatic expiry

**Characteristics**:
- Default TTL: 5 minutes (300,000ms)
- Config-based cache keys (hashed)
- Automatic cleanup of expired entries
- Ping validation before returning cached clients

**Evidence**: `AGENTS.md`:201-204, `src/mcp_connect/client/cache.py`

---

### 5. Request/Response Models (`src/mcp_connect/models/`)

**Purpose**: Pydantic models for type-safe API contracts

**Features**:
- Request validation via Pydantic 2.12+
- Environment variable substitution in config
- Header substitution support
- Single-usage mode flag

**Evidence**: `AGENTS.md`:206-209, `src/mcp_connect/models/request.py`

---

### 6. Utilities (`src/mcp_connect/utils/`)

**Purpose**: Shared infrastructure for logging, context, masking, substitution, process management

**Components**:

| Utility | Purpose | Evidence |
|---|---|---|
| `logger.py` | Structured JSON logging | `AGENTS.md`:211-215 |
| `context.py` | Request context propagation | `AGENTS.md`:211-215 |
| `masking.py` | Sensitive data masking (tokens, credentials) | `AGENTS.md`:211-215 |
| `substitution.py` | Environment/header variable substitution | `AGENTS.md`:211-215 |
| `process.py` | Process stdout/stderr capture | `AGENTS.md`:211-215 |
| `errors.py` | Custom exception types | `AGENTS.md`:274-276 |

**Evidence**: `src/mcp_connect/utils/`

---

## Data Flow

### Default Caching Mode

```
1. HTTP Request → FastAPI route
2. Auth middleware validates bearer token
3. Logging middleware captures request context
4. Route parses request → Pydantic models
5. Client manager checks cache for config hash
6. If cached: ping validation → reuse if alive
7. If not cached: create client → cache for 5 min
8. Execute MCP method on client
9. Return response → JSON
10. Logging middleware logs response
```

**Evidence**: `AGENTS.md`:224-230

### Single-Usage Mode

```
1-4. Same as caching mode
5. Client manager skips cache (single_usage: true flag)
6. Create fresh client
7. Execute MCP method
8. Cleanup client immediately
9-10. Same as caching mode
```

**Evidence**: `AGENTS.md`:232-237

---

## Transport Abstraction

The MCP client manager detects transport type from request config and instantiates the appropriate MCP transport:

| Transport | Detection | MCP SDK Class | Use Case |
|---|---|---|---|
| stdio | `command` field present | `StdioServerParameters` | Local MCP servers (npm, Python, binaries) |
| HTTP | `url` field present | `HttpServerParameters` | Remote MCP servers over HTTP/HTTPS |
| SSE | `url` with SSE headers | `SseServerParameters` | Backward compatibility (deprecated) |

**Evidence**: `AGENTS.md`:217-222, `src/mcp_connect/client/manager.py`

---

## Error Handling Strategy

**Custom Exceptions** (`utils/errors.py`):
- All errors inherit from base custom exception
- Include context in error messages
- Log with appropriate severity

**Global Error Handler** (`server/middleware.py`):
- Catches all unhandled exceptions
- Returns structured JSON error response
- Logs full traceback

**Evidence**: `AGENTS.md`:274-276

---

## Logging Strategy

**Structured JSON Logging**:
- All logs in JSON format (parseable by log aggregators)
- Request context propagated via `utils/context.py`
- Sensitive data masked via `utils/masking.py`

**Log Levels** (configurable via `LOG_LEVEL` env var):
- `debug` — verbose, includes payload details
- `info` — standard operations
- `warning` — recoverable issues
- `error` — failures requiring attention
- `critical` — service-level failures

**Evidence**: `AGENTS.md`:279-282, `src/mcp_connect/utils/logger.py`

---

## Configuration

**Environment Variables**:

| Variable | Purpose | Default |
|---|---|---|
| `ACCESS_TOKEN` | Bearer auth token | None (auth disabled) |
| `PORT` | Server port | 3000 |
| `LOG_LEVEL` | Logging level | INFO |
| `LOG_FORMAT` | Log format | json |
| `MCP_CONNECT_INIT_TIMEOUT` | Client init timeout (ms) | 30000 |
| `MCP_CONNECT_DEFAULT_TIMEOUT` | Method timeout (ms) | 120000 |
| `MCP_CONNECT_CLIENT_CACHE_TTL` | Cache TTL (ms) | 300000 |
| `MCP_CONNECT_HTTP_TIMEOUT` | HTTP transport timeout (ms) | 30000 |
| `MCP_CONNECT_SSE_READ_TIMEOUT` | SSE transport timeout (ms) | 300000 |
| `NGROK_AUTHTOKEN` | Ngrok tunnel token | None |

**Evidence**: `AGENTS.md`:240-256, `CLAUDE.md`:86-103

---

## Module Boundaries

### Clear Responsibilities

| Module | Responsibility | Dependencies |
|---|---|---|
| `server/` | HTTP interface, auth, middleware | FastAPI, models, client |
| `client/` | MCP client lifecycle, caching | MCP SDK, utils |
| `models/` | Request/response schemas | Pydantic |
| `utils/` | Shared infrastructure | python-json-logger |

**Evidence**: Project structure at `src/mcp_connect/`

### Dependency Direction

```
server/ → client/ → models/
   ↓         ↓         ↓
         utils/
```

All modules may depend on `utils/`, but `utils/` has no internal dependencies (foundation layer).

---

## Performance Characteristics

**Latency Target**: ≤ 100ms for cached clients

**Caching Strategy**:
- Config-based cache keys (same config = same client)
- Ping validation prevents using dead clients
- TTL prevents unbounded cache growth

**Async Throughout**:
- All I/O operations are async (FastAPI, MCP SDK, file/process I/O)
- Uvloop for high-performance event loop
- `asyncio.create_task()` for concurrent operations

**Evidence**: `AGENTS.md`:368, `AGENTS.md`:269-272

---

## Testing Architecture

**Test Organization**:
- `tests/test_*.py` — unit tests (fast, no external dependencies)
- `tests/integration/test_*.py` — integration tests (marked with `@pytest.mark.integration`)
- `tests/conftest.py` — shared fixtures

**Coverage Requirements**:
- All new code must have tests
- Critical paths require 100% coverage

**Evidence**: `AGENTS.md`:310-336, `pyproject.toml`:50-59

---

## Deployment

**Containerized** (Docker):
- Python 3.12+ base image
- Includes Node.js, OpenJDK, Go runtimes (for MCP servers)
- Pre-installed MCP servers
- Optional ngrok tunneling

**Evidence**: `README.md`:75-133, `Dockerfile`
