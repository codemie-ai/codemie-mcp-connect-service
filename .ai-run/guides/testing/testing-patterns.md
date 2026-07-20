# Testing Patterns

## Test Organization

### Directory Structure

```
tests/
├── __init__.py           # Test package marker
├── conftest.py           # Shared fixtures
├── test_*.py             # Unit tests
└── integration/          # Integration tests
    └── test_*.py
```

**Evidence**: `AGENTS.md`:311-314, `tests/` directory structure

### Test Types

| Type | Location | Purpose | Dependencies |
|---|---|---|---|
| **Unit** | `tests/test_*.py` | Test individual functions/classes in isolation | None (mocked) |
| **Integration** | `tests/integration/test_*.py` | Test component interactions, external I/O | External systems (subprocess, network) |

**Evidence**: `AGENTS.md`:311-314

---

## Running Tests

### Unit Tests Only (Default)

```bash
source .venv/bin/activate
poetry run pytest
```

**What runs**: All tests WITHOUT `@pytest.mark.integration` marker

**Config**: `pyproject.toml`:59 (`addopts = "-m 'not integration'"`)

**Evidence**: `AGENTS.md`:326, `pyproject.toml`:59

### Integration Tests Only

```bash
source .venv/bin/activate
poetry run pytest -m integration
```

**What runs**: Tests marked with `@pytest.mark.integration`

**Evidence**: `AGENTS.md`:329

### All Tests

```bash
source .venv/bin/activate
poetry run pytest -m ""
```

**What runs**: Both unit and integration tests

**Evidence**: `AGENTS.md`:332

### With Coverage

```bash
source .venv/bin/activate
poetry run pytest --cov=src --cov-report=term-missing
```

**Output**: Coverage percentage + line numbers of uncovered code

**Evidence**: `AGENTS.md`:335, `pyproject.toml`:50-59

---

## Test Configuration

**pytest.ini options** (in `pyproject.toml`):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"                                    # Auto-detect async tests
testpaths = ["tests"]                                    # Test discovery directory
python_files = ["test_*.py"]                             # Test file pattern
python_classes = ["Test*"]                               # Test class pattern
python_functions = ["test_*"]                            # Test function pattern
markers = [
    "integration: marks tests as integration tests"
]
addopts = "-m 'not integration'"                         # Exclude integration by default
```

**Evidence**: `pyproject.toml`:50-59

---

## Writing Tests

### Async Test Pattern

**All I/O tests must be async** (pytest-asyncio with auto mode):

```python
import pytest

async def test_something_async():
    result = await some_async_function()
    assert result == expected
```

**No decorator needed** — `asyncio_mode = "auto"` handles async detection

**Evidence**: `pyproject.toml`:51 (`asyncio_mode = "auto"`)

### Integration Test Marker

Mark tests that require external dependencies:

```python
import pytest

@pytest.mark.integration
async def test_mcp_server_stdio():
    # Test that spawns subprocess, uses network, etc.
    pass
```

**Why**: Separates fast unit tests from slower integration tests

**Evidence**: `pyproject.toml`:56-57, `AGENTS.md`:312

### Shared Fixtures

Define fixtures in `tests/conftest.py` for reuse across tests:

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_config():
    return {"key": "value"}
```

**Evidence**: `AGENTS.md`:314, `tests/conftest.py`

---

## Coverage Requirements

### Thresholds

- **All new code** must have tests
- **Critical paths** require 100% coverage (authentication, client lifecycle, MCP protocol calls)

**Evidence**: `AGENTS.md`:316-318

### Running Coverage Reports

```bash
source .venv/bin/activate

# Terminal report with missing lines
poetry run pytest --cov=src --cov-report=term-missing

# HTML report (opens in browser)
poetry run pytest --cov=src --cov-report=html
open htmlcov/index.html
```

**Output**: Shows percentage per file + line numbers NOT covered

**Evidence**: `AGENTS.md`:319

---

## Test Patterns

### Unit Test Pattern — Mock External Dependencies

| Avoid | Prefer |
|---|---|
| Calling real MCP servers in unit tests | Mock MCP SDK calls, test logic in isolation |
| Spawning subprocesses | Mock `subprocess` or test via integration tests |
| Network I/O | Mock HTTP clients or test via integration tests |

**Why**: Unit tests should be fast (< 1ms per test), reliable (no flakiness), and focused on logic

### Integration Test Pattern — Real External Calls

| Avoid | Prefer |
|---|---|
| Mocking everything in integration tests | Use real stdio transport with test MCP servers |
| Testing implementation details | Test observable behavior (stdout, stderr, exit codes) |
| Brittle path assumptions | Use tempdir fixtures or test-specific paths |

**Why**: Integration tests validate real interactions, not mocked behavior

---

## Test-Driven Development (TDD)

**Recommended workflow** from `AGENTS.md`:

1. Write failing test that reproduces bug or specifies feature
2. Implement with proper type hints
3. Run test — verify it passes
4. Run quality check suite (see quality-gates.md)
5. Verify no regressions in related functionality

**Evidence**: `AGENTS.md`:376-381 (features), `AGENTS.md`:384-390 (bugs)

---

## Common Testing Commands

### Run Specific Test File

```bash
poetry run pytest tests/test_client.py
```

### Run Specific Test Function

```bash
poetry run pytest tests/test_client.py::test_create_client
```

### Run Tests Matching Pattern

```bash
poetry run pytest -k "test_cache"
```

### Verbose Output

```bash
poetry run pytest -v
```

### Show All Output (Including Print Statements)

```bash
poetry run pytest -s
```

### Stop on First Failure

```bash
poetry run pytest -x
```

**Evidence**: Standard pytest CLI options

---

## Testing Best Practices

| Practice | Rationale | Evidence |
|---|---|---|
| Test names describe behavior | `test_client_cache_expires_after_ttl` vs `test_cache` | Readability |
| One assertion focus per test | Multiple assertions → multiple tests | Clarity on failure |
| Arrange-Act-Assert structure | Setup → Execute → Verify pattern | Standard testing pattern |
| Use fixtures for setup | Avoids duplication, improves maintainability | `conftest.py` |
| Async tests for async code | Matches production execution model | `asyncio_mode = "auto"` |
| Mark slow tests as integration | Keeps unit test suite fast | `@pytest.mark.integration` |

**Evidence**: `AGENTS.md`:309-336 (testing requirements), software engineering best practices

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|---|---|
| `ImportError: No module named 'mcp_connect'` | Activate venv: `source .venv/bin/activate` |
| Async test doesn't run | Ensure pytest-asyncio installed: `poetry install` |
| Coverage not showing | Add `--cov=src` flag |
| Integration tests run by default | Explicit marker: `poetry run pytest -m integration` |
| Test discovery fails | Verify naming: `test_*.py`, `test_*()`, `Test*` |

### Debugging Tests

```bash
# Run with Python debugger
poetry run pytest --pdb

# Show local variables on failure
poetry run pytest -l

# Show full diff on assertion failures
poetry run pytest -vv
```

**Evidence**: Standard pytest debugging flags

---

## Next Steps

- Review [Quality Gates](.ai-run/guides/quality-gates.md) for full pre-commit check including tests
- Review [Development Practices](.ai-run/guides/development/development-practices.md) for TDD workflow
- Check `tests/` directory for existing test examples
