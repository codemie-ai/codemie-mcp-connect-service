# Agent guide index

Entry point is [`../../AGENTS.md`](../../AGENTS.md). It routes; these files answer.

Read the one row that matches your task. Do not read the tree.

| Read this | When |
|---|---|
| [`project.md`](project.md) | You need the ticket tracker, the MR adapter, or the remote |
| [`setup.md`](setup.md) | You need a working environment, or a command failed on tooling |
| [`quality-gates.md`](quality-gates.md) | Before claiming a change is green, or after any edit to `src/` |
| [`security/README.md`](security/README.md) | A scanner flagged this repo, you are bumping a version to fix a CVE, or you need the command that derives a current value |
| [`build/README.md`](build/README.md) | You must build or scan a container image |
| [`build/dependencies.md`](build/dependencies.md) | You must change a package version in any manifest |
| [`testing/testing-patterns.md`](testing/testing-patterns.md) | You are writing a test, or a test failed |
| [`development/development-practices.md`](development/development-practices.md) | You are writing application code |
| [`standards/git-workflow.md`](standards/git-workflow.md) | You are branching, committing, or opening an MR |
| [`architecture/architecture.md`](architecture/architecture.md) | You need to know where a change belongs |

## What is not here

- **Repository structure.** Derived on demand — see `AGENTS.md` § Orient. A checked-in tree
  goes stale silently; the last one omitted four modules and listed a directory that does not exist.
- **Anything `README.md`, `CONTRIBUTING.md`, or `pyproject.toml` already states correctly.**
  These guides link to those files rather than copying them.
- **Tool rules that a config already enforces.** Line length, lint rule selection, and mypy
  strictness live in `pyproject.toml` and are not restated.

## Conventions these files follow

- A command appears only if it was executed and its exit code observed.
- A claim carries the file it came from, without a line number. Line numbers drift; paths do not.
- Each file states what it owns and what is owned elsewhere, so one fact has one home.
- **A value that routine maintenance changes is published as the command that finds it, not as
  the value.** Version tags, build-arg defaults, package counts, and test counts move on every
  bump; a reader who trusts a stale one is worse off than a reader who runs a grep. Write down
  what does not move: which file, which mechanism, which decision.
- Only current behaviour is described. What a command or file used to do is in `git log`.
