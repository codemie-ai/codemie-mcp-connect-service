# Technical Research

**Task**: mcp integration markitdown conversion routing
**Generated**: 2026-07-27T00:00:00Z
**Research path**: filesystem

---

## 1. Original Context

Integrate the markitdown-mcp package into the codemie-mcp-connect-service. The markitdown-mcp package provides a lightweight STDIO, Streamable HTTP, and SSE MCP server for calling MarkItDown with the exposed tool: convert_to_markdown(uri) (where uri can be any http:, https:, file:, or data: URI). This integration will enable the codemie-mcp-connect-service to leverage MarkItDown conversion capabilities as a service, thus enhancing markdown processing functionality and broadening supported data formats for end users.

---

## 2. Codebase Findings

### Existing Implementations

**MCP Server Integration Pattern:**
- `mcp-servers/github-mcp-server/` - Example GitHub MCP server integration (TypeScript)
- `mcp-servers/fetch-mcp/` - Example fetch MCP server integration (TypeScript)
- `mcp-servers/postgres-typescript/` - Example PostgreSQL MCP server integration (TypeScript)
- `mcp-servers/puppeteer-typescript/` - Example Puppeteer MCP server integration (TypeScript)
- `Dockerfile` lines 92-125 - Stage 3 installs MCP servers via npm global install

**Core MCP Client Infrastructure:**
- `src/mcp_connect/main.py` - FastAPI application entry point with lifespan management
- `src/mcp_connect/server/routes.py` - `/bridge` endpoint for MCP method routing
- `src/mcp_connect/client/manager.py` - Client factory with transport detection and caching
- `src/mcp_connect/client/transports.py` - Transport context managers (stdio, streamable-http, SSE)
- `src/mcp_connect/client/managed.py` - Cached MCP client with 5-min TTL and ping validation
- `src/mcp_connect/client/single_usage.py` - Single-use client with immediate cleanup
- `src/mcp_connect/client/methods.py` - MCP protocol method dispatcher (tools/list, tools/call, resources/*, prompts/*)

**Request Models:**
- `src/mcp_connect/models/request.py` - BridgeRequestBody with serverPath, method, params, args, env, single_usage

**Base Python Image:**
- `images/python/requirements.txt` line 9 - `markitdown[all]==0.1.2` already included in base image

### Architecture and Layers Affected

**1. Dockerfile Layer (Stage 3: MCP Servers)**
- Need to add npm package installation for `@nomyx-io/markitdown-mcp`
- Follow existing pattern: `RUN npm install -g @nomyx-io/markitdown-mcp`
- Installed to `/usr/local/lib/node_modules/@nomyx-io/markitdown-mcp`

**2. Transport Layer**
- No changes required - markitdown-mcp supports stdio, streamable-http, and SSE (all already implemented)
- `src/mcp_connect/client/transports.py` already handles all required transports

**3. Client Management Layer**
- No changes required - existing client manager automatically handles transport detection
- Cache behavior will work automatically (5-min TTL, ping validation)
- Single-usage mode will work automatically

**4. Bridge Layer**
- No changes required - `/bridge` endpoint already routes `tools/call` method
- markitdown-mcp exposes standard MCP tool: `convert_to_markdown(uri)`

**5. Testing Layer**
- New integration test required to verify markitdown-mcp connectivity
- New unit test for markitdown tool call flow

### Integration Points

**Internal Dependencies:**
- No new internal module dependencies required
- Uses existing MCP client infrastructure end-to-end

**External Service Connections:**
- markitdown-mcp package will be installed as npm global package
- Executable path: `/usr/local/lib/node_modules/@nomyx-io/markitdown-mcp/bin/markitdown-mcp`
- Runs as stdio subprocess managed by existing client manager

**MCP Protocol Flow:**
1. Client sends POST to `/bridge` with `serverPath: "npx @nomyx-io/markitdown-mcp"` (or full path)
2. Transport layer detects stdio transport (command pattern)
3. Client manager creates StdioServerParameters with command and args
4. Managed/SingleUsage client initializes stdio session
5. Client calls `tools/call` method with `name: "convert_to_markdown"`, `arguments: {"uri": "..."}`
6. markitdown-mcp processes conversion and returns markdown content
7. Response proxied back to client

### Patterns and Conventions

**MCP Server Installation Pattern (from existing servers):**
- Install via `npm install -g <package>` in Dockerfile stage 3
- No explicit configuration or registration required
- Client specifies full command path in `serverPath` field
- Transport layer auto-detects stdio vs HTTP based on serverPath format

**Testing Pattern:**
- Unit tests: Mock MCP session, verify method calls and parameter passing
- Integration tests: Spawn real MCP server process, verify end-to-end flow
- Use `@pytest.mark.integration` for tests requiring npm packages
- Example: `tests/integration/test_mcp_server_integration.py`

**Error Handling Pattern:**
- Transport errors caught in `client/transports.py`
- Method errors caught in `client/methods.py`
- All errors logged with structured context via `utils/logger.py`
- Sensitive data (tokens, credentials) masked via `utils/masking.py`

**Environment Substitution Pattern:**
- `BridgeRequestBody.env` field allows per-request environment variables
- `utils/substitution.py` performs variable substitution in serverPath and args
- Example: `serverPath: "${MCP_SERVER_PATH}/markitdown-mcp"`

---

## 3. Documentation Findings

### Guides and Architecture Docs

- `.ai-run/guides/architecture/architecture.md` - Comprehensive system design covering transport layer, client management, bridge layer, and protocol flow
- `.ai-run/guides/setup.md` - Development environment setup (Poetry, virtual environment, Docker build)
- `.ai-run/guides/quality-gates.md` - Pre-commit quality checks (ruff, mypy, black, pytest)
- `.ai-run/guides/testing/testing-patterns.md` - Test organization (unit vs integration), coverage requirements, fixtures
- `.ai-run/guides/standards/git-workflow.md` - Branch naming (EPMCDME-xxxx), commit conventions, MR creation via gitlab-mr skill
- `.ai-run/guides/development/development-practices.md` - Type hints (use built-in generics), async patterns, error handling, API documentation via context7
- `AGENTS.md` - AI agent routing (sdlc-factory for ticketed work, gitlab-mr for commit/MR, security-lead for CVE)
- `CLAUDE.md` - Claude-specific notes (virtual environment activation mandatory, pre-commit check required)

### Architectural Decisions

**ADR-001: Transport Auto-Detection (from architecture guide)**
- serverPath format determines transport type
- `http://` or `https://` → Streamable HTTP or SSE
- Command string → stdio
- No explicit transport parameter required

**ADR-002: Client Caching Strategy (from architecture guide)**
- Default: 5-min TTL cache with ping validation
- Config hash used as cache key (serverPath + args + env)
- Single-usage mode bypasses cache for immediate cleanup
- Cache cleanup via asyncio.create_task (non-blocking)

**ADR-003: MCP Protocol Method Routing (from client/methods.py)**
- Standard MCP methods: `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`
- Custom methods raise MCPMethodError
- Method validation at protocol layer, not transport layer

**ADR-004: No WebSocket Support (from architecture guide)**
- WebSocket not in MCP specification
- Python MCP SDK does not provide WebSocket transport
- Only stdio, Streamable HTTP, and SSE supported

### Derived Conventions

**Convention: MCP Server Command Format**
- npm global packages invoked via `npx <package-name>` or full path `/usr/local/lib/node_modules/<package>/bin/<binary>`
- stdio transport expects array of command + args: `["npx", "@nomyx-io/markitdown-mcp"]`
- Environment variables passed via `BridgeRequestBody.env` field

**Convention: Test Organization**
- Unit tests: Fast, mock external dependencies, test single components
- Integration tests: Slower, spawn real processes, test end-to-end flows
- Integration tests excluded from default pytest run (must explicitly use `-m integration`)
- Fixtures in `tests/conftest.py` for shared setup

**Convention: Type Safety**
- Use built-in generics: `list[str]`, `dict[str, Any]` (NOT `typing.List`, `typing.Dict`)
- Use union syntax: `str | None` (NOT `typing.Optional[str]`)
- mypy strict mode enabled - zero errors required for commit

**Convention: Logging**
- Structured JSON logging via `python-json-logger`
- Context propagation via `utils/context.py` (request_id, method, serverPath)
- Sensitive data masking via `utils/masking.py` (tokens, credentials, secrets)

---

## 4. Testing Landscape

### Existing Coverage

**MCP Client Infrastructure:**
- `tests/test_mcp_methods.py` - MCP method routing, parameter validation, error handling (130 lines)
- `tests/test_transports.py` - Transport selection, StdioServerParameters, StreamableHttpServerParameters, SSEServerParameters (95 lines)
- `tests/test_cache.py` - Client caching, TTL expiration, cache key generation, cleanup (180 lines)
- `tests/test_single_usage.py` - Single-usage mode, immediate cleanup, no caching (65 lines)
- `tests/test_auth.py` - Bearer token authentication, missing token, invalid token (55 lines)

**Integration Tests:**
- `tests/integration/test_mcp_server_integration.py` - Real MCP server process spawning (likely covers github-mcp-server or fetch-mcp based on existing patterns)

### Testing Framework and Patterns

**Framework:**
- pytest 8.4.2 with pytest-asyncio 1.2.0 (auto mode)
- pytest-cov 7.0.0 for coverage reporting
- `asyncio_mode = "auto"` in `pyproject.toml` (async test auto-detection)

**Fixture Patterns:**
- `tests/conftest.py` contains shared fixtures
- Mock MCP sessions for unit tests (no real subprocess)
- Real subprocess spawning for integration tests (marked with `@pytest.mark.integration`)
- FastAPI TestClient for endpoint testing

**Mock Strategies:**
- Mock `mcp.Client` and `mcp.ClientSession` for unit tests
- Mock `asyncio.create_subprocess_exec` for stdio transport tests
- Mock HTTP clients (httpx) for streamable-http transport tests

### Coverage Gaps

**Areas the task will touch that have no existing tests:**
- No tests for markitdown-mcp server integration (expected - new feature)
- No tests for npm package availability verification
- No tests for markitdown-specific tool call (`convert_to_markdown`)
- No tests for URI format validation (http:, https:, file:, data:)

**Required New Tests:**
1. Unit test: markitdown tool call parameter validation (uri required, format validation)
2. Unit test: markitdown tool call response structure validation
3. Integration test: spawn markitdown-mcp stdio server, call convert_to_markdown, verify markdown output
4. Integration test: verify markitdown-mcp caching behavior (same uri should return cached client)
5. Integration test: verify markitdown-mcp single-usage mode (immediate cleanup)

---

## 5. Configuration and Environment

### Environment Variables

**Existing (relevant to integration):**
- `ACCESS_TOKEN` - Bearer token for authentication (optional, auth disabled if unset)
- `PORT` - Server port (default: 3000)
- `LOG_LEVEL` - Logging verbosity (info, debug, warning, error, critical)
- `LOG_FORMAT` - text or json
- `MCP_CONNECT_DEFAULT_TIMEOUT` - Method timeout in milliseconds (default: 120000)
- `MCP_CONNECT_CLIENT_CACHE_TTL` - Cache TTL in milliseconds (default: 300000 = 5 minutes)
- `MCP_CONNECT_HTTP_TIMEOUT` - HTTP transport timeout (default: 30000ms)
- `MCP_CONNECT_SSE_READ_TIMEOUT` - SSE transport timeout (default: 300000ms)

**New (if needed):**
- None required - markitdown-mcp will use existing timeout and cache TTL settings
- Optional: Could add `MARKITDOWN_MCP_PATH` for custom installation path, but not necessary (npx auto-resolves)

### Configuration Files

**Dockerfile:**
- Stage 1: Base Python image with markitdown[all]==0.1.2 already installed
- Stage 3: MCP servers (need to add `RUN npm install -g @nomyx-io/markitdown-mcp`)
- Lines 92-125 show existing MCP server installation pattern

**pyproject.toml:**
- Poetry dependency management (Python packages only, no npm)
- Tool configuration: mypy, pytest, black, ruff
- No changes required

**.env.example:**
- Template for environment variables
- No changes required (existing timeout/cache settings apply)

**package.json (in mcp-servers/):**
- NOT used - MCP servers installed globally via Dockerfile
- npm packages managed at Docker build time, not runtime

### Feature Flags and Deployment Concerns

**Feature Flags:**
- None present in codebase
- No feature flag system implemented
- All features enabled by default

**Deployment Concerns:**
1. **Docker Build Time:** npm install will download markitdown-mcp during Docker build (adds ~10-20s to build time)
2. **Image Size:** markitdown-mcp package size (need to verify, likely 10-50MB with dependencies)
3. **Runtime Dependencies:** markitdown-mcp requires Node.js runtime (already present in alpine base image)
4. **Network Access:** If markitdown-mcp converts remote URIs (http://, https://), container needs egress network access
5. **File System Access:** If markitdown-mcp converts local files (file:// URIs), need to consider volume mounts and file permissions
6. **Security:** data: URIs may allow arbitrary data injection - need input validation

**Backward Compatibility:**
- Zero breaking changes - purely additive
- Existing MCP server integrations unaffected
- Existing API contract unchanged
- Existing clients will not be impacted

---

## 6. Risk Indicators

- **No existing markitdown integration** - Fresh integration, no existing patterns to follow (must infer from github-mcp-server, fetch-mcp patterns)
- **No tests for markitdown** - Comprehensive test coverage required (unit + integration tests for tool call, URI validation, caching, single-usage mode)
- **No documentation for adding MCP servers** - Must infer installation pattern from existing Dockerfile stage 3 (lines 92-125) and mcp-servers/ directory structure
- **markitdown package already in base image but not exposed** - `images/python/requirements.txt` includes `markitdown[all]==0.1.2`, but no MCP server installed - need to verify if markitdown-mcp depends on this or bundles its own version
- **URI format validation gap** - No existing validation for http:, https:, file:, data: URI formats - need to add validation in tool call handler or rely on markitdown-mcp's validation
- **File system security concern** - file:// URIs may allow arbitrary file access - need to consider container file system isolation and volume mount security
- **data: URI injection risk** - Arbitrary data:// URIs may allow malicious content injection - need input validation or content type restrictions
- **Unknown markitdown-mcp package size** - May significantly increase Docker image size (need to measure post-installation)
- **No error handling for unsupported URI schemes** - Need to handle edge cases (ftp://, ssh://, etc.) gracefully
- **Branch collision risk** - Branch `EPMCDME-7134-add-markitdown-mcp-support` already exists in repository, may contain conflicting or incomplete work
- **codegraph unavailable** - Codegraph MCP tools not found (CLI not available), relied on filesystem exploration only - may have missed non-obvious code relationships or call graphs
- **Cross-module dependency analysis incomplete** - Without codegraph callers/callees analysis, may have missed indirect dependencies or usage patterns

---

## 7. Summary for Complexity Assessment

This task involves integrating the markitdown-mcp package into the existing codemie-mcp-connect-service by adding it to the Dockerfile's MCP server installation stage. The integration is architecturally straightforward because the service already implements a complete MCP client infrastructure with stdio, streamable-http, and SSE transport support. The task touches only the **Deployment Layer** (Dockerfile modification) and the **Testing Layer** (new test coverage).

**File Change Surface:** 2-3 files expected
- `Dockerfile` (1 line addition in stage 3: `RUN npm install -g @nomyx-io/markitdown-mcp`)
- `tests/integration/test_markitdown_integration.py` (new file, ~80-120 lines for comprehensive integration test)
- `tests/test_markitdown_unit.py` (optional unit test for tool call parameter validation, ~40-60 lines)

**Technical Novelty and Risk:** Low to Medium
- **Low novelty:** Follows established MCP server installation pattern (identical to github-mcp-server, fetch-mcp, postgres-typescript, puppeteer-typescript installations)
- **Zero code changes** to core service logic - purely additive
- **Existing transport layer** handles stdio automatically via command pattern detection
- **Existing client manager** handles caching and lifecycle automatically
- **Medium risk factors:**
  - No existing documentation for MCP server addition workflow (must infer from existing patterns)
  - Security considerations for file:// and data: URI schemes (file system access, content injection)
  - Unknown package size impact on Docker image
  - Potential branch conflict with existing `EPMCDME-7134-add-markitdown-mcp-support` branch

**Test Coverage Posture:** Well-Tested Foundation, New Coverage Required
- **Existing coverage:** MCP client infrastructure is comprehensively tested (transport selection, caching, single-usage mode, method routing, authentication)
- **Coverage gaps:** No tests for markitdown-mcp specifically (expected for new feature)
- **Required test additions:**
  1. Integration test: spawn markitdown-mcp server, call convert_to_markdown with various URI schemes (http:, https:, file:, data:), verify markdown output
  2. Integration test: verify caching behavior (same config should reuse client)
  3. Integration test: verify single-usage mode (immediate cleanup)
  4. Unit test (optional): tool call parameter validation (uri required, format validation)

**Key Risk Factors for Complexity Scoring:**
1. **Minimal code surface** - Only Dockerfile and tests touched, zero service code changes
2. **Established pattern** - Identical to 4 existing MCP server installations
3. **No architectural changes** - Uses existing transport/client/bridge infrastructure
4. **Security validation required** - URI scheme validation and file system access controls need consideration
5. **Branch collision** - Existing branch may require rebase or merge conflict resolution
6. **Testing requirement** - Comprehensive integration tests needed despite small code change surface
