# Contributing to CodeMie MCP Connect Service

Thank you for your interest in contributing to CodeMie MCP Connect Service! We welcome contributions from the community.

## How to Contribute

1. Fork the repository
2. Clone your fork locally
3. Create a feature branch from `main`: `git checkout -b <TICKET-ID>_short-description`
4. Make your changes following the guidelines below
5. Commit your changes using [Conventional Commits](#commit-message-format)
6. Push to your fork
7. Open a pull request against `main`

## Commit Message Format

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`

**Scopes:** `api`, `bridge`, `cache`, `auth`, `transport`, `docker`, `config`, `docs`

**Rules:**
- Use imperative mood (`add` not `added` or `adds`)
- Keep the first line under 72 characters
- Reference issues in the footer: `Closes #123`

**Examples:**
```
feat(bridge): add support for streamable-http transport
fix(cache): handle TTL expiry race condition
docs(readme): update ngrok tunnel configuration
```

## Pull Request Requirements

- PR title must follow the Conventional Commits format
- At least 1 approval required
- CI pipeline must pass
- Describe what changed, why, and how it was tested
- Note any breaking changes clearly

## Development Setup

```bash
# Activate virtual environment (MANDATORY)
source .venv/bin/activate

# Install dependencies
poetry install

# Run development server
poetry run uvicorn mcp_connect.main:app --reload --port 3000
```

## Pre-commit Quality Check (required before every PR)

```bash
source .venv/bin/activate && \
  poetry run ruff format && \
  poetry run ruff check && \
  poetry run mypy src/ && \
  poetry run black --check src/ tests/ && \
  poetry run pytest tests/ --cov=src --cov-report=term-missing
```

All checks must pass (exit code 0).

## Code Standards

- Python 3.12+ with strict type annotations
- Async/await for all I/O operations
- Apache 2.0 license headers required on all source files
- Follow existing architecture: FastAPI routes → bridge layer → MCP transport

## Reporting Issues

Please use the [GitHub issue tracker](../../issues) to report bugs or request features. Include:
- A clear description of the issue or request
- Steps to reproduce (for bugs)
- Expected vs. actual behavior
- Environment details (OS, Python version, Docker version)

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).
