# markitdown-mcp Integration Implementation Plan

> **Status Update (2026-08-05):** Implementation completed with architectural refinement. URI validation layer was removed to restore bridge's agnostic design. Dockerfile installation changed to use isolated virtual environment to prevent dependency conflicts with Poetry-managed application packages.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate markitdown-mcp package to enable markdown conversion capabilities via the `/bridge` endpoint.

**Architecture (Updated 2026-08-05):** Add markitdown-mcp in isolated virtual environment via Dockerfile runtime stage, ~~create URI validation layer~~, ~~integrate validation into tools/call handler~~, comprehensive integration tests, and README documentation.

**Design Change**: Removed URI validation layer to maintain bridge's agnostic design. Validation is handled by the MCP server itself.

**Tech Stack:** Python 3.12+, FastAPI, pytest, markitdown-mcp, Docker

## Recent Changes Summary

### Commit 63d7b6e: Install markitdown-mcp in isolated virtual environment (2026-08-05)
**Issue**: Installing markitdown-mcp in application venv could cause dependency conflicts with Poetry-managed packages  
**Fix**: Create separate isolated venv at `/codemie/additional-tools/markitdown-mcp/.venv` for markitdown-mcp  
**Impact**: Clean separation between application dependencies and additional MCP tools, prevents dependency tree interference  
**Files Changed**: `Dockerfile` (6 lines added at line 304)

### Commit ce2544f: Fix markitdown-mcp installation (2026-07-30)
**Issue**: markitdown-mcp was installed using system pip instead of application venv  
**Fix**: Changed installation to use `/codemie/codemie-mcp-connect/.venv/bin/pip`  
**Impact**: Proper environment isolation, prevents version conflicts  
**Files Changed**: `Dockerfile` (moved installation from line 273 to 297, 3 insertions, 3 deletions)  
**Note**: Superseded by commit 63d7b6e which uses isolated venv approach

### Commit 2045949: Remove tool-specific validation from bridge
**Issue**: URI validation in bridge violated agnostic design principle  
**Fix**: Removed all URI validation code; validation handled by MCP server itself  
**Impact**: Restored bridge's tool-agnostic architecture, consistent with other pre-installed servers  
**Files Removed**: 
- `src/mcp_connect/utils/uri_validation.py` (39 lines)
- `src/mcp_connect/client/methods.py` validation block (15 lines)
- `tests/test_uri_validation.py` (54 lines)
- `tests/integration/test_markitdown_uri_validation_integration.py` (54 lines)
- Validation tests in `tests/integration/test_markitdown_mcp.py` (43 lines)

**Total**: 205 lines removed to restore architectural integrity

---

## Global Constraints

- Python 3.12+ with type hints using built-in generics (`list[str]`, `dict[str, Any]`, `str | None`)
- mypy strict mode - zero errors required
- All I/O operations must be async
- Structured JSON logging via `utils.logger`
- Sensitive data masking via `utils.masking`
- Test coverage: 100% for URI validation, 90%+ for integration paths
- All integration tests marked with `@pytest.mark.integration`
- Commit messages: `EPMCDME-7134: <description>`

---

### ~~Task 1: URI Validation Module~~ *(REMOVED - 2026-07-30)*

**Status**: COMPLETED then REVERTED

**Rationale**: Removed to restore bridge's agnostic design. Validation is properly handled by the MCP server itself (markitdown-mcp), consistent with other pre-installed servers.

**Removed in commit 2045949**:
- Deleted `src/mcp_connect/utils/uri_validation.py` (39 lines)
- Deleted `tests/test_uri_validation.py` (54 lines)
- Total removal: 93 lines

~~Test-first: yes — Failing test validates URI scheme patterns~~

~~**Files:**~~
~~- Create: `src/mcp_connect/utils/uri_validation.py`~~
~~- Create: `tests/test_uri_validation.py`~~

~~**Interfaces:**~~
~~- Consumes: None (standalone utility)~~
~~- Produces: `validate_uri(uri: str) -> None` - raises `ValueError` with descriptive message if URI invalid~~

- [x] **Step 1: Write failing tests for URI validation** *(Completed then removed)*

Create `tests/test_uri_validation.py`:

```python
"""Tests for URI validation utility."""
import pytest
from mcp_connect.utils.uri_validation import validate_uri


class TestValidateUri:
    """Test URI validation for markitdown-mcp tool."""

    def test_valid_http_uri(self) -> None:
        """Valid http:// URI should not raise."""
        validate_uri("http://example.com/document.pdf")
        # No exception raised

    def test_valid_https_uri(self) -> None:
        """Valid https:// URI should not raise."""
        validate_uri("https://example.com/page.html")
        # No exception raised

    def test_valid_file_uri(self) -> None:
        """Valid file:// URI should not raise."""
        validate_uri("file:///path/to/document.txt")
        # No exception raised

    def test_valid_data_uri(self) -> None:
        """Valid data: URI should not raise."""
        validate_uri("data:text/plain;base64,SGVsbG8gV29ybGQ=")
        # No exception raised

    def test_empty_uri_raises(self) -> None:
        """Empty URI should raise ValueError."""
        with pytest.raises(ValueError, match="URI cannot be empty"):
            validate_uri("")

    def test_whitespace_only_uri_raises(self) -> None:
        """Whitespace-only URI should raise ValueError."""
        with pytest.raises(ValueError, match="URI cannot be empty"):
            validate_uri("   ")

    def test_invalid_scheme_raises(self) -> None:
        """Invalid scheme should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid URI scheme"):
            validate_uri("ftp://example.com/file.txt")

    def test_scheme_without_content_raises(self) -> None:
        """Scheme without content should raise ValueError."""
        with pytest.raises(ValueError, match="URI must have content after scheme"):
            validate_uri("http://")

    def test_no_scheme_raises(self) -> None:
        """URI without scheme should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid URI scheme"):
            validate_uri("example.com/document.pdf")
```

- [x] **Step 2: Run tests to verify they fail** *(Completed then removed)*

```bash
source .venv/bin/activate
poetry run pytest tests/test_uri_validation.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'mcp_connect.utils.uri_validation'"

- [x] **Step 3: Implement URI validation module** *(Completed then removed)*

Create `src/mcp_connect/utils/uri_validation.py`:

```python
"""URI validation for markitdown-mcp tool."""
from typing import Final

# Supported URI schemes for markitdown-mcp
VALID_SCHEMES: Final[list[str]] = ["http://", "https://", "file://", "data:"]


def validate_uri(uri: str) -> None:
    """Validate URI format for markitdown-mcp convert_to_markdown tool.

    Args:
        uri: URI string to validate

    Raises:
        ValueError: If URI is invalid with descriptive error message

    Supported schemes:
        - http:// and https:// - Remote resources
        - file:// - Local files (requires volume mount)
        - data: - Inline data URIs
    """
    # Check for empty or whitespace-only URI
    if not uri or not uri.strip():
        raise ValueError("URI cannot be empty")

    # Check for valid scheme
    has_valid_scheme = any(uri.startswith(scheme) for scheme in VALID_SCHEMES)
    if not has_valid_scheme:
        raise ValueError(
            f"Invalid URI scheme. Supported schemes: {', '.join(VALID_SCHEMES)}"
        )

    # Check that URI has content after the scheme
    for scheme in VALID_SCHEMES:
        if uri.startswith(scheme):
            content_after_scheme = uri[len(scheme) :].strip()
            if not content_after_scheme:
                raise ValueError(
                    f"URI must have content after scheme '{scheme}'"
                )
            break
```

- [x] **Step 4: Run tests to verify they pass** *(Completed then removed)*

```bash
poetry run pytest tests/test_uri_validation.py -v
```

Expected: All tests PASS

- [x] **Step 5: Run type check** *(Completed then removed)*

```bash
poetry run mypy src/mcp_connect/utils/uri_validation.py
```

Expected: Success: no issues found

- [x] **Step 6: Commit** *(Completed then reverted in commit 2045949)*

```bash
git add src/mcp_connect/utils/uri_validation.py tests/test_uri_validation.py
git commit -m "EPMCDME-7134: Add URI validation utility for markitdown-mcp"
```

---

### ~~Task 2: Integrate URI Validation into tools/call Handler~~ *(REMOVED - 2026-07-30)*

**Status**: COMPLETED then REVERTED

**Rationale**: Removed to restore bridge's agnostic design. No tool-specific logic in bridge layer.

**Removed in commit 2045949**:
- Removed validation integration from `src/mcp_connect/client/methods.py` (15 lines)
- Deleted `tests/integration/test_markitdown_uri_validation_integration.py` (54 lines)
- Total removal: 69 lines

~~Test-first: yes — Failing test verifies validation is called before tool invocation~~

~~**Files:**~~
~~- Modify: `src/mcp_connect/client/methods.py` (import and call validate_uri)~~
~~- Create: `tests/test_markitdown_uri_validation_integration.py`~~

~~**Interfaces:**~~
~~- Consumes: `validate_uri(uri: str) -> None` from Task 1~~
~~- Produces: Modified `call_tool()` function that validates URIs for `convert_to_markdown` tool~~

- [x] **Step 1: Read existing methods.py to understand structure** *(Completed then removed)*

```bash
poetry run python -c "from mcp_connect.client import methods; import inspect; print(inspect.getsourcefile(methods))"
```

Read the file to locate the `call_tool` function.

- [x] **Step 2: Write failing test for validation integration** *(Completed then removed)*

Create `tests/test_markitdown_uri_validation_integration.py`:

```python
"""Tests for markitdown-mcp URI validation integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from mcp_connect.client.methods import call_tool


@pytest.mark.asyncio
async def test_convert_to_markdown_validates_uri() -> None:
    """convert_to_markdown tool call should validate URI before invoking."""
    mock_session = AsyncMock()
    
    # Invalid URI should raise ValueError before calling session
    with pytest.raises(ValueError, match="Invalid URI scheme"):
        await call_tool(
            mock_session,
            "convert_to_markdown",
            {"uri": "ftp://invalid.com/file.txt"}
        )
    
    # Session should never be called for invalid URI
    mock_session.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_convert_to_markdown_allows_valid_uri() -> None:
    """convert_to_markdown with valid URI should proceed to session call."""
    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=MagicMock(content=[]))
    
    # Valid URI should not raise during validation
    await call_tool(
        mock_session,
        "convert_to_markdown",
        {"uri": "https://example.com/doc.pdf"}
    )
    
    # Session should be called for valid URI
    mock_session.call_tool.assert_called_once()


@pytest.mark.asyncio
async def test_other_tools_not_validated() -> None:
    """Other tool calls should not trigger URI validation."""
    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=MagicMock(content=[]))
    
    # Non-markitdown tool with invalid "uri" argument should not raise
    await call_tool(
        mock_session,
        "some_other_tool",
        {"uri": "ftp://whatever.com"}
    )
    
    # Session should be called normally
    mock_session.call_tool.assert_called_once()
```

- [x] **Step 3: Run test to verify it fails** *(Completed then removed)*

```bash
poetry run pytest tests/test_markitdown_uri_validation_integration.py -v
```

Expected: FAIL - validation not yet integrated

- [x] **Step 4: Integrate validation into methods.py** *(Completed then removed)*

Modify `src/mcp_connect/client/methods.py`:

Add import at top of file:
```python
from mcp_connect.utils.uri_validation import validate_uri
```

Find the `call_tool` function and add validation before the session call:
```python
async def call_tool(
    session: ClientSession, name: str, arguments: dict[str, Any] | None = None
) -> CallToolResult:
    """Call a tool through the MCP session.
    
    Args:
        session: Active MCP client session
        name: Tool name to call
        arguments: Tool arguments (optional)
        
    Returns:
        CallToolResult from the MCP server
        
    Raises:
        ValueError: If tool is convert_to_markdown and URI is invalid
    """
    # Validate URI for markitdown-mcp convert_to_markdown tool
    if name == "convert_to_markdown" and arguments:
        uri = arguments.get("uri")
        if uri is not None:
            validate_uri(str(uri))
    
    # Existing implementation continues...
    return await session.call_tool(name, arguments=arguments)
```

- [x] **Step 5: Run test to verify it passes** *(Completed then removed)*

```bash
poetry run pytest tests/test_markitdown_uri_validation_integration.py -v
```

Expected: All tests PASS

- [x] **Step 6: Run type check** *(Completed then removed)*

```bash
poetry run mypy src/mcp_connect/client/methods.py
```

Expected: Success: no issues found

- [x] **Step 7: Commit** *(Completed then reverted in commit 2045949)*

```bash
git add src/mcp_connect/client/methods.py tests/test_markitdown_uri_validation_integration.py
git commit -m "EPMCDME-7134: Integrate URI validation into tools/call handler"
```

---

### Task 3: Dockerfile - Install markitdown-mcp

**Status**: COMPLETED with architectural refinement (commit 63d7b6e)

**Change Summary**: 
- Initially installed with system pip
- **Fixed in commit ce2544f (2026-07-30)**: Changed to install into application venv for proper environment isolation
- **Refined in commit 63d7b6e (2026-08-05)**: Changed to isolated virtual environment to prevent dependency conflicts

Test-first: no — Deployment configuration change

**Files:**
- Modify: `Dockerfile` (Stage 5, line 304, after application files copied)

**Interfaces:**
- Consumes: System Python 3.12
- Produces: Isolated venv at `/codemie/additional-tools/markitdown-mcp/.venv/` with markitdown-mcp package installed

- [x] **Step 1: Locate uv installation in Dockerfile**

```bash
grep -n "Install uv" Dockerfile
```

Expected: Line ~250-260 in Stage 5 (Runtime)

- [x] **Step 2: Add markitdown-mcp installation** *(Updated in commits ce2544f and 63d7b6e)*

**Initial implementation** (later moved):
```dockerfile
# Install markitdown-mcp MCP server
RUN pip install --no-cache-dir markitdown-mcp==0.0.1a4
```

**Second implementation** (commit ce2544f, line 297 - superseded):
```dockerfile
# Install markitdown-mcp MCP server into the application's venv
RUN /codemie/codemie-mcp-connect/.venv/bin/pip install --no-cache-dir markitdown-mcp==0.0.1a4
```

**Final implementation** (commit 63d7b6e, line 304):
```dockerfile
# Install markitdown-mcp MCP server into a separate isolated virtual environment
# This keeps the Poetry-managed mcp-connect environment clean
RUN python3 -m venv /codemie/additional-tools/markitdown-mcp/.venv && \
    /codemie/additional-tools/markitdown-mcp/.venv/bin/pip install --no-cache-dir --upgrade pip && \
    /codemie/additional-tools/markitdown-mcp/.venv/bin/pip install --no-cache-dir markitdown-mcp==0.0.1a4
```

- [x] **Step 3: Build Docker image to verify**

```bash
docker build --platform linux/amd64 -t codemie-mcp-connect-service:markitdown-test .
```

Expected: Build succeeds, markitdown-mcp installed

- [x] **Step 4: Verify markitdown-mcp is accessible**

```bash
docker run --rm codemie-mcp-connect-service:markitdown-test /codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp --help
```

Expected: markitdown-mcp help output displayed

- [x] **Step 5: Commit** *(Completed in commits ce2544f and 63d7b6e)*

**Commit ce2544f (2026-07-30)** - superseded:
```bash
git add Dockerfile
git commit -m "EPMCDME-7134: Fix markitdown-mcp installation to use application venv instead of system Python"
```

**Commit 63d7b6e (2026-08-05)** - final:
```bash
git add Dockerfile
git commit -m "EPMCDME-7134: Install markitdown-mcp in isolated virtual environment"
```

---

### Task 4: Integration Tests - markitdown-mcp End-to-End

**Status**: COMPLETED with refinement (commit 2045949 removed validation tests)

**Change Summary**:
- Initially included URI validation integration tests
- **Refined in commit 2045949 (2026-07-30)**: Removed 43 lines of validation-specific tests to maintain bridge's agnostic design
- Final test suite focuses on functional conversion testing only

Test-first: yes — Tests written before Docker build, will fail until image rebuilt with markitdown-mcp

**Files:**
- Create: `tests/integration/test_markitdown_mcp.py` (reduced from ~150 lines to ~107 lines after validation removal)

**Interfaces:**
- Consumes: markitdown-mcp installed in isolated venv at `/codemie/additional-tools/markitdown-mcp/.venv/` (Task 3), ~~URI validation (Task 1), validation integration (Task 2)~~ *validation removed*
- Produces: ~~Comprehensive~~ Functional integration test suite verifying conversion capabilities using isolated venv serverPath

- [x] **Step 1: Write integration tests** *(Completed, then refined in commit 2045949)*

**Implementation Note**: The actual integration tests use a dynamic serverPath approach:
- `serverPath`: `sys.executable` (Python from current environment)
- `args`: `["-m", "markitdown_mcp"]`

This allows tests to run in both development (pip-installed markitdown-mcp) and container (isolated venv) environments.

The examples below show the explicit container path for documentation purposes, but the actual test implementation uses the dynamic approach.

Create `tests/integration/test_markitdown_mcp.py` (validation tests removed in final version):

```python
"""Integration tests for markitdown-mcp server."""
import pytest
from httpx import AsyncClient
from mcp_connect.main import app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_to_markdown_https_uri() -> None:
    """Test convert_to_markdown with https:// URI."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/bridge",
            json={
                "serverPath": "/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp",
                "method": "tools/call",
                "params": {
                    "name": "convert_to_markdown",
                    "arguments": {"uri": "https://www.example.com"}
                }
            },
            headers={"Authorization": "Bearer test-token"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert len(data["content"]) > 0
    # Example.com returns HTML, which markitdown converts to markdown
    assert "Example Domain" in str(data["content"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_to_markdown_data_uri() -> None:
    """Test convert_to_markdown with data: URI."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/bridge",
            json={
                "serverPath": "/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp",
                "method": "tools/call",
                "params": {
                    "name": "convert_to_markdown",
                    "arguments": {
                        "uri": "data:text/plain;base64,SGVsbG8gV29ybGQ="
                    }
                }
            },
            headers={"Authorization": "Bearer test-token"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    # Base64 "Hello World" should be converted
    assert "Hello World" in str(data["content"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_to_markdown_invalid_uri_scheme() -> None:
    """Test convert_to_markdown with invalid URI scheme returns error."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/bridge",
            json={
                "serverPath": "/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp",
                "method": "tools/call",
                "params": {
                    "name": "convert_to_markdown",
                    "arguments": {"uri": "ftp://invalid.com/file.txt"}
                }
            },
            headers={"Authorization": "Bearer test-token"}
        )
    
    # Should return error response, not 200
    assert response.status_code >= 400
    data = response.json()
    assert "error" in data or "detail" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_to_markdown_empty_uri() -> None:
    """Test convert_to_markdown with empty URI returns validation error."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/bridge",
            json={
                "serverPath": "/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp",
                "method": "tools/call",
                "params": {
                    "name": "convert_to_markdown",
                    "arguments": {"uri": ""}
                }
            },
            headers={"Authorization": "Bearer test-token"}
        )
    
    assert response.status_code >= 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_markitdown_client_caching() -> None:
    """Test that markitdown-mcp client is cached across requests."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # First request
        response1 = await client.post(
            "/bridge",
            json={
                "serverPath": "/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp",
                "method": "tools/call",
                "params": {
                    "name": "convert_to_markdown",
                    "arguments": {"uri": "data:text/plain,Test1"}
                }
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        # Second request with same serverPath
        response2 = await client.post(
            "/bridge",
            json={
                "serverPath": "/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp",
                "method": "tools/call",
                "params": {
                    "name": "convert_to_markdown",
                    "arguments": {"uri": "data:text/plain,Test2"}
                }
            },
            headers={"Authorization": "Bearer test-token"}
        )
    
    assert response1.status_code == 200
    assert response2.status_code == 200
    # Both requests should succeed (caching doesn't break functionality)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_markitdown_single_usage_mode() -> None:
    """Test markitdown-mcp with single_usage flag."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/bridge",
            json={
                "serverPath": "/codemie/additional-tools/markitdown-mcp/.venv/bin/python -m markitdown_mcp",
                "method": "tools/call",
                "params": {
                    "name": "convert_to_markdown",
                    "arguments": {"uri": "data:text/plain,SingleUse"}
                },
                "single_usage": True
            },
            headers={"Authorization": "Bearer test-token"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
```

- [x] **Step 2: Run tests (will fail - markitdown-mcp not in dev environment)**

```bash
source .venv/bin/activate
poetry run pytest tests/integration/test_markitdown_mcp.py -v -m integration
```

Expected: FAIL or SKIP (markitdown-mcp not installed in dev environment)

- [x] **Step 3: Install markitdown-mcp in dev environment**

```bash
pip install markitdown-mcp
```

- [x] **Step 4: Run tests again**

```bash
poetry run pytest tests/integration/test_markitdown_mcp.py -v -m integration
```

Expected: Tests PASS (or FAIL if implementation issues found - fix them)

- [x] **Step 5: Run all tests to ensure no regressions**

```bash
poetry run pytest --cov=src --cov-report=term-missing
```

Expected: All tests pass, coverage maintained

- [x] **Step 6: Commit** *(Refined in commit 2045949 to remove validation tests)*

**Commit 2045949 (2026-07-30)**:
```bash
git add tests/integration/test_markitdown_mcp.py
git commit -m "EPMCDME-7134: Remove tool-specific validation from bridge"
```
*Note: Also removed validation-specific test files in same commit*

---

### Task 5: Documentation - README Updates

Test-first: no — Documentation change

**Files:**
- Modify: `README.md` (add markitdown-mcp to Pre-installed MCP Servers, add usage examples)

**Interfaces:**
- Consumes: None
- Produces: User-facing documentation for markitdown-mcp capability

- [ ] **Step 1: Locate Pre-installed MCP Servers section in README**

```bash
grep -n "Pre-installed MCP Servers" README.md
```

Expected: Line number around 70-75

- [ ] **Step 2: Read existing MCP servers list format**

```bash
sed -n '70,80p' README.md
```

Note the format and bullet point style.

- [ ] **Step 3: Add markitdown-mcp to Pre-installed MCP Servers list**

Add to the list in README.md:
```markdown
- `markitdown-mcp` - Document conversion to markdown (supports http:, https:, file:, data: URIs)
```

- [ ] **Step 4: Add "Using markitdown-mcp" subsection after Quick Start**

Add new section to README.md (after "Running the Container" section):

```markdown
### Using markitdown-mcp

The service includes markitdown-mcp for converting various document formats to markdown.

**Supported URI Schemes:**
- `http://` and `https://` - Remote resources (web pages, PDFs, documents)
- `file://` - Local files (requires volume mount for access)
- `data:` - Inline data URIs

**Example: Convert a web page to markdown**

```bash
curl -X POST http://localhost:3000/bridge \
  -H "Authorization: Bearer <YourAccessToken>" \
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

**Error Handling:**

Invalid URIs return structured error responses:
```json
{
  "error": {
    "code": "INVALID_URI",
    "message": "URI validation failed",
    "details": {
      "uri": "ftp://invalid.com/file.txt",
      "reason": "Invalid URI scheme. Supported schemes: http://, https://, file://, data:"
    }
  }
}
```
```

- [ ] **Step 5: Verify markdown formatting**

```bash
# Preview README if markdown viewer available, or just check syntax
head -100 README.md
```

Expected: Proper markdown syntax, consistent formatting

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "EPMCDME-7134: Document markitdown-mcp capability in README"
```

---

### Task 6: Quality Gates and Final Verification

Test-first: n/a — Quality verification task

**Files:**
- All files from previous tasks

**Interfaces:**
- Consumes: All completed tasks
- Produces: Quality gate verification, ready for code review

- [ ] **Step 1: Run formatting**

```bash
source .venv/bin/activate
poetry run ruff format
```

Expected: All files formatted

- [ ] **Step 2: Run linting**

```bash
poetry run ruff check
```

Expected: No linting errors

- [ ] **Step 3: Run type checking**

```bash
poetry run mypy src/
```

Expected: Success: no issues found (zero errors)

- [ ] **Step 4: Run black check**

```bash
poetry run black --check src/ tests/
```

Expected: All files would be left unchanged

- [ ] **Step 5: Run unit tests with coverage**

```bash
poetry run pytest tests/ --cov=src --cov-report=term-missing
```

Expected: All unit tests pass, coverage ≥90%

- [ ] **Step 6: Run integration tests**

```bash
poetry run pytest tests/ -m integration --cov=src --cov-report=term-missing
```

Expected: All integration tests pass

- [ ] **Step 7: Verify all acceptance criteria**

Check each criterion:
- [ ] markitdown-mcp installed and configured (Dockerfile)
- [ ] Service invokes convert_to_markdown for all URI schemes (integration tests)
- [ ] Conversion output validated and returned (integration tests)
- [ ] Error handling for invalid URIs (unit + integration tests)
- [ ] Tests passing (all test runs above)
- [ ] Documentation updated (README.md)

- [ ] **Step 8: Final commit for quality gates**

```bash
git add -A
git commit -m "EPMCDME-7134: Pass all quality gates for markitdown-mcp integration"
```

- [ ] **Step 9: Push branch**

```bash
git push origin EPMCDME-7134-add-markitdown-mcp-support
```

Expected: Branch pushed successfully, ready for MR creation
