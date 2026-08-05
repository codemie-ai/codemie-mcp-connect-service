# GEMINI.md

Read [AGENTS.md](./AGENTS.md). It is the entry point for every AI agent working in this
repository and routes to the guides under `.ai-run/guides/`.

Nothing repository-specific lives in this file. A second copy of the same guidance drifts from
the first, and neither reader can tell which one is current.

## Gemini-specific notes

- `poetry run <tool>` resolves the in-project `.venv` on its own; activation is needed only when
  invoking a tool binary directly.
- Run quality gates one at a time, not as one chained string — see
  [.ai-run/guides/quality-gates.md](.ai-run/guides/quality-gates.md).
- Some commands in this repository look like gates but are not. Check the traps table in that
  same guide before reading an exit code as a verdict.
