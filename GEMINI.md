# GEMINI.md

This file provides guidance to Gemini Code when working with code in this repository.

## 🚀 Project Status: Production Python Service

**CodeMie MCP Connect Service** - FastAPI bridge enabling cloud AI platforms to interact with local MCP servers via HTTP/HTTPS to stdio protocol translation.

**Tech Stack**: Python 3.12+ | FastAPI 0.121.0+ | Uvicorn | Pydantic 2.12.0+ | MCP Python SDK v1.21.0+
**Dev Tools**: Poetry 2.1.3 | pytest + pytest-asyncio | mypy (strict) | black | ruff

### Development Focus

1. **Code Quality**: 100% test coverage for critical paths, strict type checking, comprehensive error handling
2. **Performance**: Latency ≤ 100ms for cached clients, efficient client caching with TTL validation
3. **Reliability**: Structured JSON logging, sensitive data masking, robust error handling
4. **Testing**: Unit tests + integration tests validating all transports (stdio, HTTP, SSE)

---

## Essential Commands

### CRITICAL: Virtual Environment Activation

**⚠️ MANDATORY: Always activate the virtual environment BEFORE running any Python or Poetry commands!**

```bash
# Activate virtual environment (REQUIRED for all Python/Poetry commands)
source .venv/bin/activate
```

**NEVER run Poetry or Python commands without activating .venv first!**

### Python Development Commands

```bash
# ALWAYS activate venv first
source .venv/bin/activate

# Install dependencies
poetry install

# Run the application
poetry run uvicorn src.mcp_connect.main:app --reload

# Run tests
poetry run pytest

# Run type checking
poetry run mypy src/

# Format code
poetry run black src/ tests/

# Lint code
poetry run ruff check src/ tests/

# Check Python version
poetry run python --version

# List installed packages
poetry show
```

---

## Architecture Overview

### Architecture Context

**Platform**: Python 3.12+ with FastAPI, structured JSON logging, MCP Python SDK

**Key Features**:
1. HTTP-to-stdio protocol translation for MCP servers
2. Client caching with TTL validation and ping checks
3. Enhanced observability (stdout + stderr capture)

### Technology Stack (Approved)

**Core Stack:**
- **Language**: Python 3.12+ (native async/await, enhanced type hints)
- **Web Framework**: FastAPI 0.115.0+ (async, Express.js-like patterns)
- **ASGI Server**: Uvicorn with uvloop (high-performance async)
- **Validation**: Pydantic 2.7.0+ (type-safe request/response models)
- **MCP SDK**: Official `mcp` Python SDK (stdio, Streamable HTTP, SSE)
- **Logging**: python-json-logger (structured JSON with sensitive data masking)
- **Testing**: pytest + pytest-asyncio
- **Type Checking**: mypy (strict mode)
- **Dependency Management**: Poetry 2.1.3 (CodeMie standard)

### Key Components

1. **HTTP Server** - FastAPI with `/health` and `/bridge` endpoints
2. **MCP Client Manager** - Creates and manages MCP clients with caching
3. **Client Cache** - Custom async cache with TTL (5-minute default)
4. **Logging & Observability** - Structured JSON, context propagation, masking
5. **Models** - Pydantic models for request/response validation

### Transport Support

- ✅ **stdio** - Local command execution (primary use case)
- ✅ **Streamable HTTP** - Remote MCP servers over HTTP/HTTPS
- ✅ **SSE** - Deprecated but supported for backward compatibility
- ❌ **WebSocket** - NOT supported (intentionally removed, not in MCP spec)

### Key Environment Variables

```bash
ACCESS_TOKEN=<bearer-token>         # Required for authentication
PORT=3000                           # Server port
LOG_LEVEL=debug                     # debug, info, warn, error
LOG_FORMAT=json                     # json or text
MCP_CONNECT_DEFAULT_TIMEOUT=60000   # milliseconds
MCP_CONNECT_CLIENT_CACHE_TTL=300000 # 5 minutes
```

### Project Structure

```
/
├── src/
│   └── mcp_connect/                 # 🐍 Python implementation (ACTIVE)
│       ├── __init__.py              # ✅ Package initialization
│       ├── main.py                  # ✅ FastAPI app entry point
│       ├── server/                  # HTTP server components (Epic 2)
│       ├── client/                  # MCP client management (Epic 3)
│       ├── models/                  # Pydantic data models (Epic 2)
│       └── utils/                   # Shared utilities (Epic 4)
│
├── tests/                           # ✅ pytest test suite (initialized)
│   └── __init__.py                  # ✅ Test directory marker
│
├── docs/                            # Documentation
│   ├── PRD.md                       # ✅ Product requirements (complete)
│   ├── epics.md                     # ✅ Epic breakdown (complete)
│   ├── architecture-python-migration.md  # ✅ Python architecture (complete)
│   ├── sprint-status.yaml           # ✅ Sprint tracking (live)
│   └── stories/                     # ✅ Story files
│       ├── 1-1-*.md                 # ✅ Done
│       ├── 1-2-*.md                 # ✅ Done
│       └── 1-3-*.md                 # ✅ Done
│
├── pyproject.toml                   # ✅ Poetry config (created)
├── poetry.lock                      # ✅ Dependency lockfile (54 packages)
├── .venv/                           # ✅ Virtual environment
├── Dockerfile                       # To be created - Python container (Story 1.4)
└── GEMINI.md                        # This file
```

---

## Migration Tracking

### Current Phase Status

**See `docs/bmm-workflow-status.yaml` for live status**

**Completed:**
- ✅ Phase -1: Prerequisites (document-project)
- ✅ Phase 0: Discovery (brainstorm, research, product-brief)
- ✅ Phase 1: Planning (PRD, validate-prd)
- ✅ Phase 2: Solutioning (architecture)
- ✅ Solutioning Gate Check (PRD + Architecture validated)

**Current:**
- 🚀 **Phase 3: Implementation** - Epic 1 story execution
  - ✅ Story 1.1: Repository Restructure (done)
  - ✅ Story 1.2: Initialize Python Project with Poetry (done)
  - ✅ Story 1.3: Create FastAPI Health Check Endpoint (done)
  - 📋 Stories 1.4-1.6: Remaining Epic 1 stories

**Upcoming:**
- ⏸️ Epic 2: Core MCP Bridge Implementation
- ⏸️ Epic 3-5: Client Management, Logging, Production Validation

### Epic Overview

See `docs/epics.md` for complete breakdown:

1. **Epic 1**: Repository Restructure & Python Foundation (Weeks 1-2)
2. **Epic 2**: Core MCP Bridge Implementation (Weeks 2-3)
3. **Epic 3**: Client Management & Performance (Weeks 3-4)
4. **Epic 4**: Enhanced Logging & Observability (Weeks 5-6)
5. **Epic 5**: Production Validation & Cutover (Weeks 6-8)

### Success Criteria

- ✅ 100% CodeMie test-harness pass (validates API parity)
- ✅ Performance ≥ Node.js baseline (< 100ms cached latency)
- ✅ 24-hour logging continuity validated (resolves critical bug)
- ✅ Zero-downtime blue-green deployment
- ✅ Operations team trained and signed off

---

## Key Documentation

### Migration Planning (Essential Reading)

- **`docs/PRD.md`** - Complete product requirements, functional requirements, success criteria
- **`docs/epics.md`** - 5 epics broken into 36 implementable stories
- **`docs/architecture-python-migration.md`** - Python architecture patterns, technology decisions, implementation guidelines
- **`docs/product-brief-codemie-mcp-connect-service-2025-11-09.md`** - Strategic context and business drivers

### Technical Analysis

- **`docs/research-technical-2025-11-08.md`** - Technology stack research and ADR-001
- **`docs/DEVELOPER_GUIDELINES_SINGLE_USAGE.md`** - Single-usage mode patterns
- **`docs/MCP_CACHING_ANALYSIS.md`** - Client caching architecture

---

## Key Features

### Core Capabilities

1. **Process Output Capture**: Captures both stdout and stderr for comprehensive logging
2. **Structured Logging**: JSON logging with sensitive data masking
3. **Type Safety**: Python type hints with mypy strict mode
4. **Async Performance**: High-performance async/await with uvloop

### Supported Transports

- ✅ **stdio** - Local command execution (primary use case)
- ✅ **Streamable HTTP** - Remote MCP servers over HTTP/HTTPS
- ✅ **SSE** - Server-Sent Events (backward compatibility)
- ❌ **WebSocket** - Not supported (not in MCP spec)

### API Contract

- All 12 MCP protocol methods supported
- Environment variable substitution
- Header substitution
- Single-usage mode with immediate cleanup
- Client caching with TTL and ping validation

---

## BMM Workflow Integration

This project uses BMM (BMad Method) workflows for structured development.

**Current workflow phase**: Epic 1 Implementation (Story-by-story development)

**Access agents via slash commands:**
- `/bmad:bmm:agents:dev` - Developer Agent (story implementation)
- `/bmad:bmm:workflows:dev-story` - Execute dev story workflow
- `/bmad:bmm:workflows:code-review` - Perform code review on completed story
- `/bmad:bmm:workflows:story-done` - Mark story as done after review
- `/bmad:bmm:workflows:workflow-status` - Check current phase and next steps

**Workflow status**: See `docs/bmm-workflow-status.yaml`

---

## Important Notes for Gemini Code

### For Implementation Phase (CURRENT)

**CRITICAL - Virtual Environment:**
- ⚠️ **ALWAYS run `source .venv/bin/activate` before ANY Python or Poetry commands**
- ⚠️ **NEVER install Poetry globally or modify PATH** - Poetry is already in `.venv/bin/`
- Verify activation with `which python` and `which poetry` (should point to `.venv/`)
- All Python/Poetry commands MUST be run inside the activated virtual environment

**Development Workflow:**
1. **Story Selection**: Use `/bmad:bmm:agents:dev` to pick next ready-for-dev story
2. **Implementation**: Follow acceptance criteria and technical specifications exactly
3. **Testing**: Write tests for each story, validate all ACs pass
4. **Code Quality**: Run black, ruff, mypy on all code before completion
5. **Documentation**: Update story file with implementation notes, file list, change log
6. **Review**: Mark story as "review" status when complete

**Python Development Standards:**
- Use Poetry for all dependency management (`poetry add`, `poetry install`)
- Run tests with `poetry run pytest`
- Type check with `poetry run mypy src/` (strict mode enabled)
- Format with `poetry run black src/ tests/` (line length 100)
- Lint with `poetry run ruff check src/ tests/` (E, F, I rules)
- All code must pass mypy strict mode with no errors

**API Documentation & Best Practices (MANDATORY):**
- ⚠️ **ALWAYS use the `resolve_library_id` and `get_library_docs` tools when implementing stories** to get latest API documentation and best practices
- **Before implementing any library feature** (FastAPI, Pydantic, MCP SDK, pytest, etc.):
  1. Use `resolve_library_id` to find the library ID
  2. Use `get_library_docs` with relevant topic to get current documentation
  3. Review latest API patterns, best practices, and examples from the docs
- **The tools provide**:
  - Latest stable API documentation (more current than training data)
  - Code examples and usage patterns
  - Best practices and common pitfalls
  - Version-specific guidance
- **Examples**:
  - Implementing FastAPI endpoint → Get FastAPI docs for "routing", "dependencies", "responses"
  - Using Pydantic models → Get Pydantic docs for "models", "validation", "configuration"
  - Writing async tests → Get pytest-asyncio docs for "fixtures", "markers"
  - MCP protocol → Get MCP Python SDK docs for "clients", "transports", "protocol"
- **Why this matters**: Ensures implementation uses latest stable APIs, follows current best practices, and avoids deprecated patterns

### General Notes
- **Pay attention**: You can send only one brave-search request per second. Send requests one by one with 1-second delay.
- **Code Quality**: Maintain strict type checking, 100% test coverage for critical paths, comprehensive error handling
- **Testing**: All changes must pass unit tests, integration tests, and type checking before commit
