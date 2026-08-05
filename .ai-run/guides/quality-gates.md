# Quality Gates

**Read first:** [`README.md`](README.md) — the guide index.
**This file owns:** what each gate proves, how to read its failure, and how to fix it.
**Owned elsewhere:** which gates a given security fix requires → [`security/README.md`](security/README.md) ·
tool configuration → `pyproject.toml` · the human contribution checklist → `CONTRIBUTING.md`.

Every command below was executed on 2026-07-31 in this repository and its exit code observed.
Nothing here is inferred from configuration.

## Run them one at a time

Run each gate as its own command. A single `&&`-chained string hides which gate failed, and it is
shell syntax rather than a command, so anything that runs commands directly cannot execute it.
The chained form is usable only by a human at a prompt.

`poetry run <tool>` finds the in-project `.venv` by itself. `source .venv/bin/activate` is
needed only to invoke a tool binary directly, without the `poetry run` prefix.

| # | Gate | Command | Blocking | Observed |
|---|---|---|---|---|
| 1 | Lock consistency | `poetry check --lock` | yes | exit 0 |
| 2 | Format | `poetry run ruff format` | no — it mutates | exit 0, all files already formatted |
| 3 | Lint | `poetry run ruff check` | yes | exit 0 |
| 4 | Type check | `poetry run mypy src/` | yes | exit 0, no issues |
| 5 | Format verify | `poetry run black --check src/ tests/` | yes | exit 0, all files unchanged |
| 6 | Unit tests | `poetry run pytest tests/ --cov=src --cov-report=term-missing` | yes | exit 0, whole suite green, roughly 90s |
| 7 | Secret scan | `make gitleaks` | yes | see § Secret scan |

**Pass** is exit 0 on every blocking gate. **Fail** is any non-zero exit — fix and re-run the
gate that failed, then re-run the rest.

---

## 1. Lock consistency — `poetry check --lock`

Proves `poetry.lock` still matches `pyproject.toml`. Run it after any dependency change, before
anything else — a stale lock makes every later gate test the wrong dependency set.

It prints deprecation warnings about `[tool.poetry.readme]`, `[tool.poetry.authors]`, and
`[tool.poetry.scripts]`. These are warnings on stdout with exit 0. They are not failures and are
not yours to fix inside an unrelated change.

**Fail** → re-run the targeted update for the package you changed. Never `rm poetry.lock`, never
a full relock. See [`build/dependencies.md`](build/dependencies.md).

## 2–3. Format and lint — `ruff`

`poetry run ruff format` rewrites files, so it proves nothing on its own; it is a fix, not a
check. To assert formatting without mutating, use `poetry run ruff format --check`.

`poetry run ruff check` lints under the `E`, `F`, `I` rule set at line length 120. Rule selection
lives in `pyproject.toml` `[tool.ruff]` and is not restated here.

**Fail** → `poetry run ruff check --fix` handles the auto-fixable subset. Read the rest.

## 4. Type check — `poetry run mypy src/`

Strict mode. Every function needs annotations; `warn_return_any` and `disallow_untyped_defs` are
on. `mcp`, `mcp.*`, and `botocore.*` are exempt from import checking because they ship no stubs —
that override is in `pyproject.toml` and is the only sanctioned exemption.

**Never skip this one.** There is no CI pipeline in this repository, so a type error that leaves
your machine is a type error that reaches `main`.

**Fail** → add or correct the annotation. Do not silence it with `# type: ignore` unless you can
name why the checker is wrong.

## 5. Format verify — `poetry run black --check src/ tests/`

Both `black` and `ruff format` are configured at line length 120 and run against this repository
without conflict. `--check` reports without writing; `poetry run black src/ tests/` applies.

## 6. Unit tests — `pytest`

Roughly 90 seconds. `addopts = "-m 'not integration'"` in `pyproject.toml` means the
plain invocation already excludes the integration marker; you do not need to pass `-m` yourself.

**Fail** → fix the code or the test. A test deleted or weakened to make the gate pass has failed
the gate.

Coverage: all new code carries tests, and critical paths — authentication, client lifecycle, MCP
protocol calls — carry full coverage. Patterns are in
[`testing/testing-patterns.md`](testing/testing-patterns.md).

## 7. Secret scan — `make gitleaks`

The `Makefile` target runs gitleaks in a container against the repository root, so it needs a
container runtime that can reach Docker Hub. The image and tag are in the `Makefile`.

Without one, the locally installed binary scans the same tree: `gitleaks dir --no-banner .` →
exit 0, no leaks found, verified 2026-07-31. A scan that could not run at all is reported as
unverified, never as a pass.

**Fail** → a real hit is a compromised credential. Remove it, and have a human rotate it. Deleting
the line without rotating leaves a live secret in the git history.

---

## Traps — commands that look like gates

Never read a verdict from an exit code produced by one of these. Each was executed to confirm the
trap is real; the observed value is in the table.

| Command | What actually happens |
|---|---|
| `poetry run pytest tests/ -m integration` | **exit 5** — every test deselected, none selected. `tests/integration/` holds only `__init__.py` and no test carries `@pytest.mark.integration`. Integration coverage is absent, not passing. |
| `poetry run pip-licenses --allow-only=...` | **exit 1** on `filelock` (Unlicense), a dev dependency. The allow list in `pyproject.toml` `[tool.pip-licenses]` governs shipped dependencies; scope the run before treating a failure as real. |
| `poetry run pre-commit run --all-files` | No `.pre-commit-config.yaml` exists in the repository. The framework is installed and has nothing to execute. |

The first sits inside the pre-merge chain in `README.md`. That chain cannot pass as written.

---

## Human convenience form

For a single paste at an interactive prompt, chained so it stops at the first failure. This is
not the gate definition; the table above is:

```bash
poetry check --lock && \
poetry run ruff format && \
poetry run ruff check && \
poetry run mypy src/ && \
poetry run black --check src/ tests/ && \
poetry run pytest tests/ --cov=src --cov-report=term-missing && \
make gitleaks
```

---

## When to run what

| Situation | Gates |
|---|---|
| Changed `src/` | 2–6 |
| Changed a dependency version | 1–6, then rebuild and rescan the image — [`security/README.md`](security/README.md) |
| Changed only `images/python/`, `uv-constraints.txt`, or a `Dockerfile` | None apply. Rebuild and rescan is the only evidence — [`build/README.md`](build/README.md) |
| About to commit anything | All blocking gates |

Nothing re-checks this after merge. There is no `.gitlab-ci.yml` and no GitHub workflow in this
repository; what you run locally is the only verification that happens.
