# GEMINI.md

This file provides guidance to Gemini Code when working with code in this repository.

## Primary Reference

See [AGENTS.md](./AGENTS.md) for comprehensive guidance on:
- AI Development Guides (project context, architecture, setup, quality gates, git workflow, testing, development practices)
- Task Routing (feature/refactor/bug workflows, security remediation, code review, etc.)
- Project Overview and Technology Stack
- Essential Commands (virtual environment activation, Python development commands, pre-commit quality checks)
- Project Structure
- Architecture Overview
- Environment Variables
- Development Guidelines (code style, testing requirements, type checking)
- Important Notes for AI Agents

---

## Gemini-Specific Notes

### Essential Commands Quick Reference

**⚠️ MANDATORY: Always activate the virtual environment BEFORE running any Python or Poetry commands!**

```bash
# Activate virtual environment (REQUIRED for all Python/Poetry commands)
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

### Gemini Code Workflow

**Development Process:**
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

### API Documentation & Best Practices (MANDATORY)

**⚠️ ALWAYS use the `resolve_library_id` and `get_library_docs` tools when implementing stories** to get latest API documentation and best practices.

**Before implementing any library feature** (FastAPI, Pydantic, MCP SDK, pytest, etc.):

1. Use `resolve_library_id` to find the library ID
2. Use `get_library_docs` with relevant topic to get current documentation
3. Review latest API patterns, best practices, and examples from the docs

**The tools provide**:
- Latest stable API documentation (more current than training data)
- Code examples and usage patterns
- Best practices and common pitfalls
- Version-specific guidance

**Examples**:
- Implementing FastAPI endpoint → Get FastAPI docs for "routing", "dependencies", "responses"
- Using Pydantic models → Get Pydantic docs for "models", "validation", "configuration"
- Writing async tests → Get pytest-asyncio docs for "fixtures", "markers"
- MCP protocol → Get MCP Python SDK docs for "clients", "transports", "protocol"

**Why this matters**: Ensures implementation uses latest stable APIs, follows current best practices, and avoids deprecated patterns.

### General Notes

- **Pay attention**: You can send only one brave-search request per second. Send requests one by one with 1-second delay.
- **Code Quality**: Maintain strict type checking, 100% test coverage for critical paths, comprehensive error handling
- **Testing**: All changes must pass unit tests, integration tests, and type checking before commit
- **Virtual Environment**: CRITICAL - always activate `.venv` before running any Python/Poetry commands
- **Quality Gates**: See [AGENTS.md](./AGENTS.md) for comprehensive pre-commit quality check requirements
