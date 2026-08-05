# AGENTS.md

Entry point for AI agents and automations working in this repository. It routes; the guides
answer. Read the row that matches your task, follow the one link, and stop.

**CodeMie MCP Connect Service** — a production FastAPI bridge translating HTTP/HTTPS requests
into MCP stdio, Streamable HTTP, and SSE communication, so cloud AI platforms can drive locally
running MCP servers. Python 3.12, Poetry, deployed as a container.

<!-- START managed: sdlc-factory guide-imports -->
## AI Development Guides

| Guide | Purpose |
|---|---|
| [Guide index](.ai-run/guides/README.md) | Which guide answers which question |
| [Project Context](.ai-run/guides/project.md) | Project identity, ticket/MR adapters, source control |
| [Architecture](.ai-run/guides/architecture/architecture.md) | System design, components, transports, data flow |
| [Setup](.ai-run/guides/setup.md) | Development environment, dependencies, commands |
| [Quality Gates](.ai-run/guides/quality-gates.md) | Lint, format, type-check, test, secret scan |
| [Security](.ai-run/guides/security/README.md) | CVE and vulnerability remediation process |
| [Build & Images](.ai-run/guides/build/README.md) | Container images, build stages, scanning |
| [Dependencies](.ai-run/guides/build/dependencies.md) | Which manifest owns a package, how to move it |
| [Git Workflow](.ai-run/guides/standards/git-workflow.md) | Branch naming, commits, MR creation |
| [Testing](.ai-run/guides/testing/testing-patterns.md) | Test organization, coverage, running tests |
| [Development Practices](.ai-run/guides/development/development-practices.md) | Type hints, async patterns, error handling, API docs |
<!-- END managed: sdlc-factory guide-imports -->

<!-- START managed: sdlc-factory task-classifier -->
## Task Routing

When working on this repository:
- **New feature/refactor/bug with ticket** → use sdlc-factory:sdlc-standard skill
- **Security/CVE remediation** → use security-lead skill
- **Commit + MR creation** → use gitlab-mr skill
- **Code review** → use gitlab-mr-code-review or sdlc-factory:code-review skill
- **Quick fixes without ticket** → proceed with standard workflow, reference guides above
<!-- END managed: sdlc-factory task-classifier -->

## Route by task

| Your task | Read |
|---|---|
| Bump a package version to fix a CVE | [security/README.md](.ai-run/guides/security/README.md), then [build/dependencies.md](.ai-run/guides/build/dependencies.md) |
| Build or scan a container image | [build/README.md](.ai-run/guides/build/README.md) |
| Find the current gates, images, or pins rather than trusting a document | [security/README.md](.ai-run/guides/security/README.md) § Where to find the current values |
| Write or change application code | [development-practices.md](.ai-run/guides/development/development-practices.md) |
| Write or fix a test | [testing-patterns.md](.ai-run/guides/testing/testing-patterns.md) |
| Decide where a change belongs | [architecture.md](.ai-run/guides/architecture/architecture.md) |
| Prove a change is green | [quality-gates.md](.ai-run/guides/quality-gates.md) |
| Branch, commit, open an MR | [git-workflow.md](.ai-run/guides/standards/git-workflow.md) |
| Get a working environment | [setup.md](.ai-run/guides/setup.md) |
| Use the API, run the service, read env vars | `README.md` |
| Contribute as a human, commit message types | `CONTRIBUTING.md` |

## Stack

Python 3.12+ · FastAPI · Uvicorn with uvloop · Pydantic 2 · the official `mcp` Python SDK ·
python-json-logger · Poetry. Dev: pytest with pytest-asyncio, mypy strict, black, ruff.

Exact versions and constraints live in `pyproject.toml`. Read them there rather than from a
document. Several are load-bearing security pins; the grep in § Orient lists which.

## Architecture at a glance

Enough to decide where a change belongs. The full picture, including request flow and timeouts,
is in [architecture.md](.ai-run/guides/architecture/architecture.md).

| Area | Holds |
|---|---|
| `server/` | FastAPI routes `/health` and `/bridge`, bearer-token auth, logging, error handling |
| `client/` | Client creation, transport selection, caching, MCP method execution |
| `models/` | Pydantic request and response schemas — the API contract |
| `utils/` | Structured logging, request context, masking, env and header substitution, process capture |

**Transports:** stdio (the primary case), Streamable HTTP, and SSE (deprecated, kept for
backward compatibility). WebSocket is absent by decision — not in the MCP spec, not in the
Python SDK.

**Client modes:** cached by default — clients are reused for an identical configuration, ping-
validated before reuse, with a five-minute TTL. `single_usage: true` takes a fresh client per
request and cleans up immediately, for one-off and batch work.

**Auth is off when `ACCESS_TOKEN` is unset.** The token check is a no-op in that case, so an
endpoint is not protected merely because the code path exists. Check the variable before
assuming otherwise.

## Where a package lives

The most-missed fact when fixing a vulnerability: much of what ships in the service image is
fetched *during* the build and appears in no manifest at all. Editing the wrong surface produces
a diff that changes nothing in the scanned image. Full table and commands:
[build/dependencies.md](.ai-run/guides/build/dependencies.md).

| Installed | Surface |
|---|---|
| Into the service's Python environment | `pyproject.toml` + `poetry.lock` |
| Into the separate Python scripting image | `images/python/requirements.txt` (exact pins) |
| By an MCP server tracked here | `mcp-servers/*/package.json` `overrides` |
| By `uvx` when a tool starts inside the running container | `uv-constraints.txt` (exact pins) |
| By something the build fetches — Go modules, upstream npm, npm's own bundled deps, OS packages | the relevant `Dockerfile` |

**"The Dockerfile" means the repo-root one** — the main image, and the only one the Helm chart in
`deploy-templates/` deploys. `images/python/Dockerfile` is a separate additional image, older
than the current layout and still built and scanned, reached only by a ticket naming
`codemie-python` or `codemie-mcp-connect-service-python`. The two under `mcp-servers/` are built
by nothing here. Full table: [build/README.md](.ai-run/guides/build/README.md).

## Workflows

**Adding a feature**

1. Confirm the library API against current documentation rather than memory.
2. Write the failing test first.
3. Implement with full type hints.
4. Run the blocking gates.
5. Update `README.md` only if the change is user-facing.

**Fixing a bug**

1. Write a test that reproduces it and fails.
2. Fix the cause, not the symptom, with the error handling the surrounding code uses.
3. Confirm the test passes and the rest of the suite still does.

**Fixing a vulnerability**

1. Map the ticket's component name — including the alias `codemie-mcp-connect-service-python` —
   via the component table in [security/README.md](.ai-run/guides/security/README.md).
2. Find the surface the package actually lives on, per the table above.
3. Apply the minimal change with a `# Security (EPMCDME-...)` comment.
4. Run that component's gates, then rebuild and rescan the image.

Full process: [security/README.md](.ai-run/guides/security/README.md).

## Orient — derive structure, do not memorize it

Run the command. A structure written into a document goes stale silently, and a wrong map costs
more than no map.

| Question | Command |
|---|---|
| What are the top-level areas | `git ls-files \| awk -F/ 'NF>1{print $1"/"}' \| sort -u` |
| What is in the Python package | `git ls-files 'src/**/*.py'` |
| Where is a symbol defined | `grep -rn "def <name>\|class <name>" src/` |
| What tests exist for an area | `git ls-files 'tests/**' \| grep <area>` |
| Which pins are load-bearing security fixes | `grep -rn "Security (EPMCDME" Dockerfile pyproject.toml images/ mcp-servers/` |
| What changed in a file and why | `git log --oneline -- <path>` |
| What runtime config exists | `grep -rn "os.environ\|os.getenv" src/` |

## Commands

`poetry run <tool>` resolves the in-project `.venv` on its own — activation is not required for
it. Activate only when invoking a tool binary directly (`pytest`, `mypy`, `ruff` with no
`poetry run` prefix).

```bash
poetry install                                   # dependencies from poetry.lock
poetry run uvicorn mcp_connect.main:app --reload  # dev server
poetry run pytest tests/                          # full suite, ~90s
poetry run pytest tests/ --cov=src --cov-report=term-missing
poetry run mypy src/
poetry run ruff check
poetry run black --check src/ tests/
make gitleaks                                     # needs a container runtime with registry access
```

**Before every commit,** run the blocking gates. They are listed one per line, with observed exit
codes and what each proves, in [quality-gates.md](.ai-run/guides/quality-gates.md). Which gates a
given security fix actually requires is in
[security/README.md](.ai-run/guides/security/README.md) § After the fix.

Do not treat a single `&&`-chained string as the gate. Run the gates individually: a chain
reports only the first failure, and a chained string is shell syntax rather than a command, so
anything that runs commands directly cannot execute it.

## Traps

Commands here that look like gates and are not. Full list with observed exit codes:
[quality-gates.md](.ai-run/guides/quality-gates.md) § Traps.

- **`poetry run pytest tests/ -m integration`** collects nothing and exits 5. `tests/integration/`
  holds only `__init__.py`, and no test carries the marker. Integration coverage is absent, not
  passing. `README.md` carries it inside the pre-merge chain — that chain cannot pass as written.
- **`poetry run pip-licenses --allow-only=...`** across the whole environment exits 1 on a dev
  dependency (`filelock`, Unlicense). The allow list governs shipped dependencies.
- **`pre-commit`** is installed as a dev dependency, but no `.pre-commit-config.yaml` exists.
  Installing and running the hooks executes nothing.
- **A gate that could not run is not a gate that passed.** A build failing on registry access, a
  scanner with a stale database — report unverified and stop.

## Boundaries

**Always**

- Put a `EPMCDME-NNNNN:` prefix on every branch and commit. Every commit in this repository has one.
- Commit a manifest and its lock file in the same commit.
- Give any security pin a `# Security (EPMCDME-NNNNN): ... to fix CVE-...` comment naming the reason.
- Keep `mypy --strict` clean. There is no CI to catch it later.

**Ask first**

- Bumping a base image tag in any `FROM` line — it changes the runtime for every consumer.
- Adding a brand-new dependency, as opposed to moving an existing one. It needs review on
  licence, maintenance, and transitive footprint, and the allow list in `pyproject.toml`
  `[tool.pip-licenses]` is binding.
- Changing the `/bridge` request or response schema. Deployed clients depend on it.

**Never**

- **Regenerate or hand-edit `poetry.lock`.** Change the one package with a targeted update, so
  the security fix stays distinguishable from unrelated churn — see
  [build/dependencies.md](.ai-run/guides/build/dependencies.md).
- **Relax or delete a pin carrying a `# Security (EPMCDME-...)` comment** as cleanup. Remove it
  in its own commit only when upstream ships the fix, as the `# TODO: Remove once ...` lines
  above the Go pins in `Dockerfile` describe.
- **Fix a language-package CVE with a Dockerfile override** when the package has a manifest.
  The override patches the image and leaves the lock file vulnerable for every other consumer.
- **Write a summary or validation-report document.** Report in the response instead.
- **Add WebSocket transport.** It is absent by decision, not omission — it is not in the MCP
  spec and not in the Python SDK.

## Working agreements

- **Verify library APIs before writing them.** Use the context7 MCP tool
  (`resolve-library-id`, then `get-library-docs`) for FastAPI, Pydantic, the MCP SDK, and
  pytest rather than writing a signature from memory. Details:
  [development-practices.md](.ai-run/guides/development/development-practices.md).
- **This is a production service.** A change that is merely plausible is not good enough, and
  nothing re-checks it after merge — there is no CI pipeline in this repository.
- **Async for all I/O.** Blocking calls stall the event loop.
- **Log through `utils/logger.py`, with context from `utils/context.py`, masked by
  `utils/masking.py`.** Tokens and credentials flow through this service.
- **Tests come with the change**, and critical paths — authentication, client lifecycle, MCP
  protocol calls — carry full coverage.
- **Be brief.** Maximum information density, minimum verbosity, in code and in output.

## Conventions this file follows

Every command above was executed and its exit code observed. Claims cite a file, not a line
number, because line numbers drift and a wrong anchor is worse than none. Structure is derived,
never stored. Anything `README.md`, `CONTRIBUTING.md`, or `pyproject.toml` already states
correctly is linked, not copied.

**Values that routine maintenance moves — version tags, build-arg defaults, pin counts, test
counts — are not written here.** The command that finds them is. That is why § Orient is a table
of commands and why the stack section sends you to `pyproject.toml`. Adding a version number to
this file schedules it to go wrong.

When a fact here stops being true, fix it here and nowhere else. `CLAUDE.md` and `GEMINI.md`
point at this file rather than repeating it.
