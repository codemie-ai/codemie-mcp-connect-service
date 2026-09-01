# markitdown-mcp Integration Design

**Task**: EPMCDME-7134 - Add support for markitdown-mcp to codemie-mcp-connect-service  
**Date**: 2026-07-27  
**Status**: Approved

## Overview

Integrate the markitdown-mcp package into codemie-mcp-connect-service to enable markdown conversion capabilities. The markitdown-mcp package provides a lightweight STDIO, Streamable HTTP, and SSE MCP server that exposes the `convert_to_markdown(uri)` tool, supporting http:, https:, file:, and data: URI schemes.

This integration enhances the service's markdown processing functionality and broadens supported data formats for end users.

## Architecture

### Design Principles

**Zero Service Code Changes**: The codemie-mcp-connect-service is architecturally MCP-server-agnostic. All required infrastructure exists:
- Transport layer auto-detects stdio/HTTP/SSE based on `serverPath` format
- Client manager handles caching and lifecycle automatically
- Bridge endpoint routes MCP protocol methods generically
- Generic error handling and logging apply to all MCP servers

**No Bridge-Level Validation** *(Updated 2026-07-30)*: Initial design included URI validation layer in the bridge, but this was removed to restore the bridge's agnostic design. Validation is now handled by the MCP server itself, consistent with other pre-installed servers.

### Layers Affected

1. **Deployment Layer** (Dockerfile): Add pip install in runtime stage using application venv
2. ~~**Validation Layer** (new): Minimal URI validation before tool invocation~~ *(REMOVED - validation handled by MCP server)*
3. **Testing Layer** (tests/integration/): Comprehensive integration tests
4. **Documentation Layer** (README.md): Usage examples and capabilities

### Installation Approach

The base Python image already includes `markitdown[all]==0.1.2` from `images/python/requirements.txt`. The markitdown-mcp package is a Python MCP server wrapper around this library.

**Updated Approach (2026-08-05)**: Install markitdown-mcp into an isolated virtual environment:
```dockerfile
# Install markitdown-mcp MCP server into a separate isolated virtual environment
# This keeps the Poetry-managed mcp-connect environment clean
RUN python3 -m venv /codemie/additional-tools/markitdown-mcp/.venv && \
    /codemie/additional-tools/markitdown-mcp/.venv/bin/pip install --no-cache-dir --upgrade pip && \
    /codemie/additional-tools/markitdown-mcp/.venv/bin/pip install --no-cache-dir markitdown-mcp==0.0.1a4
```

**Rationale**: 
- Isolates markitdown-mcp dependencies from Poetry-managed application dependencies
- Prevents potential version conflicts and dependency tree interference
- Maintains clean separation between application code and additional MCP tools
- Consistent with best practices for managing external tools in containers

This approach treats markitdown-mcp as a separate tool with its own isolated environment, rather than mixing it with application dependencies.

Server invocation: `/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp` or the venv-specific entry point.

## Implementation Details

### 1. Dockerfile Modification

**Location**: Stage 5 (Runtime), after application files are copied (around line 301)

**Final Implementation (2026-08-05)**:
```dockerfile
# Install markitdown-mcp MCP server into a separate isolated virtual environment
# This keeps the Poetry-managed mcp-connect environment clean
RUN python3 -m venv /codemie/additional-tools/markitdown-mcp/.venv && \
    /codemie/additional-tools/markitdown-mcp/.venv/bin/pip install --no-cache-dir --upgrade pip && \
    /codemie/additional-tools/markitdown-mcp/.venv/bin/pip install --no-cache-dir markitdown-mcp==0.0.1a4
```

**Rationale**: 
- Creates isolated venv specifically for markitdown-mcp at `/codemie/additional-tools/markitdown-mcp/.venv`
- Prevents dependency tree interference with Poetry-managed application dependencies
- No Poetry lock file changes required
- Maintains clean separation between application and additional MCP tools
- Installed after application files are in place

### 2. URI Validation Layer *(REMOVED - 2026-07-30)*

**Status**: Initially implemented but removed to restore bridge's agnostic design.

~~**Location**: New file `src/mcp_connect/utils/uri_validation.py`~~

**Removal Rationale**:
- Bridge service should remain tool-agnostic
- Validation is properly handled by the MCP server itself (markitdown-mcp)
- Consistent with treatment of other pre-installed MCP servers
- Eliminates 205 lines of validation-specific code and tests

**Removed Files**:
- `src/mcp_connect/utils/uri_validation.py` (39 lines)
- `tests/test_uri_validation.py` (54 lines)
- `tests/integration/test_markitdown_uri_validation_integration.py` (54 lines)
- Validation integration in `tests/integration/test_markitdown_mcp.py` (43 lines)
- Validation block in `src/mcp_connect/client/methods.py` (15 lines)

### 3. Conversion Error Handling

**Strategy**:
- Rely on markitdown-mcp server's built-in error handling
- Bridge service forwards MCP protocol errors generically
- No tool-specific error handling in bridge layer
- Log all errors with full context via existing structured logger

**Error Types** *(handled by markitdown-mcp, not bridge)*:
- ~~`INVALID_URI`: Validation failure (caught before calling tool)~~ *Removed*
- `CONVERSION_FAILED`: markitdown-mcp returned error
- `TIMEOUT`: Conversion exceeded timeout limit
- `UNSUPPORTED_FORMAT`: File type not supported by markitdown

### 4. Integration Tests

**File**: `tests/integration/test_markitdown_mcp.py`

**Test Coverage**:

**End-to-End Client Tests**:
1. Full HTTP cycle - POST to `/bridge` with isolated venv serverPath, verify MCP protocol response structure
2. Verify response contains `content` field with markdown text
3. Validate markdown output format (headers, lists, formatting present)
4. Verify HTTP 200 status and proper response headers

**URI Scheme Coverage**:
5. `http://` URI conversion - verify markdown output
6. `https://` URI conversion - verify markdown output
7. `file://` URI conversion - verify markdown output (test file in container)
8. `data:` URI conversion - verify markdown output

**Infrastructure Tests**:
9. Client caching - same config reuses cached client
10. Single-usage mode - immediate cleanup after single call

**Error Handling Tests** *(Updated - removed bridge-level validation tests)*:
11. ~~Invalid URI format - returns INVALID_URI error~~ *Removed*
12. ~~Empty URI - returns validation error~~ *Removed*
13. Unsupported conversion - returns CONVERSION_FAILED error
14. Network timeout - returns TIMEOUT error

**Test Markers**: All tests marked with `@pytest.mark.integration` (require markitdown-mcp installed)

**Implementation Note**: The actual integration tests in `tests/integration/test_markitdown_mcp.py` use a dynamic approach:
- `serverPath`: `sys.executable` (Python from current environment)
- `args`: `["-m", "markitdown_mcp"]`

This allows tests to run both:
- In development environments (markitdown-mcp installed via `pip install markitdown-mcp`)
- In container environments (markitdown-mcp in isolated venv)

For API usage examples and documentation, use the explicit container path: `/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp`

### 5. Documentation Updates

**File**: README.md

**Changes**:

1. **Pre-installed MCP Servers section** - Add to list:
   ```
   - markitdown-mcp - Document conversion to markdown (supports http:, https:, file:, data: URIs)
   ```

2. **New "Using markitdown-mcp" subsection** with example (updated for isolated venv):
   ```bash
   # Example: Convert a web page to markdown
   curl -X POST http://localhost:3000/bridge \
     -H "Authorization: Bearer <ACCESS_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{
       "serverPath": "/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp",
       "method": "tools/call",
       "params": {
         "name": "convert_to_markdown",
         "arguments": {
           "uri": "https://example.com/document.pdf"
         }
       }
     }'
   ```

3. **Supported URI Schemes documentation**:
   - `http://` and `https://` - Remote resources
   - `file://` - Local files (requires volume mount for access)
   - `data:` - Inline data URIs

4. **Error Handling section**: ~~Document validation errors and~~ Document conversion failures (validation handled by MCP server)

## Security Considerations

**URI Validation**: Basic format validation prevents obviously malformed inputs but trusts markitdown-mcp's built-in security for actual processing.

**file:// URI Access**: Limited to container filesystem. Users must explicitly mount volumes to access host files. No additional restrictions beyond container isolation.

**data: URI Processing**: No content restrictions. markitdown-mcp handles data URI parsing and validation.

**Rationale**: Container isolation provides primary security boundary. Adding service-level restrictions would duplicate markitdown-mcp's built-in handling without meaningful security benefit.

## Deployment Impact

**Docker Image Size**: +10-30MB (markitdown-mcp + dependencies)

**Build Time**: +10-20 seconds (pip install markitdown-mcp)

**Runtime Performance**: No impact on existing MCP servers. markitdown-mcp uses standard client caching (5-min TTL) and lifecycle management.

**Backward Compatibility**: Purely additive. Zero breaking changes to existing API or behavior.

## Testing Strategy

**Unit Tests**: ~~URI validation logic (`tests/test_uri_validation.py`)~~ *Removed - no bridge-level validation*
- ~~Valid URI schemes pass validation~~
- ~~Invalid schemes fail with clear messages~~
- ~~Empty/whitespace URIs fail validation~~
- ~~Edge cases (malformed schemes, special characters)~~

**Integration Tests**: End-to-end markitdown-mcp functionality (`tests/integration/test_markitdown_mcp.py`)
- All URI schemes work correctly (validation by MCP server)
- Conversion output validated and returned to client
- Caching and single-usage modes work
- ~~Error handling covers acceptance criteria~~ *Bridge forwards MCP server errors generically*

**Coverage Target**: ~~100% for URI validation logic,~~ 90%+ for integration test coverage of markitdown-mcp paths

## Acceptance Criteria Mapping

| Criterion | Implementation |
|-----------|----------------|
| `markitdown-mcp` installed and configured | Dockerfile creates isolated venv and installs markitdown-mcp (2026-08-05: isolated venv approach) |
| Service invokes `convert_to_markdown(uri)` for all URI schemes | Integration tests verify http:, https:, file:, data: |
| Conversion output validated and returned to client | Integration tests verify response structure, content field, markdown format |
| Error handling for invalid URIs or conversion failures | ~~URI validation layer + error handling wrapper + error response tests~~ *Updated 2026-07-30: MCP server handles validation, bridge forwards errors generically* |
| Unit/integration tests with passing results | ~~Comprehensive test suite~~ Integration test suite in `tests/integration/test_markitdown_mcp.py` (validation tests removed) |
| Documentation updated | README.md additions with examples and capabilities |

## File Changes Summary

**Modified Files**:
- `Dockerfile` - Create isolated venv and install markitdown-mcp (6 lines at line 304)
- `README.md` - Add markitdown-mcp documentation and examples (~30 lines)

**New Files** *(Updated 2026-07-30)*:
- ~~`src/mcp_connect/utils/uri_validation.py` - URI validation logic (~50 lines)~~ *Removed*
- ~~`tests/test_uri_validation.py` - Unit tests for validation (~80 lines)~~ *Removed*
- ~~`tests/integration/test_markitdown_mcp.py` - Integration tests (~150 lines)~~ *Integration tests remain but validation tests removed (107 lines final)*

**Removed Files** *(2026-07-30 - restore agnostic design)*:
- `src/mcp_connect/utils/uri_validation.py` (39 lines removed)
- `tests/test_uri_validation.py` (54 lines removed)
- `tests/integration/test_markitdown_uri_validation_integration.py` (54 lines removed)
- Validation integration in `src/mcp_connect/client/methods.py` (15 lines removed)
- Validation tests in `tests/integration/test_markitdown_mcp.py` (43 lines removed)

**Net Changes**: 
- Initial implementation: ~310 lines added
- Validation removal: -205 lines
- Final: ~105 lines net addition (Dockerfile + basic integration tests + README)
