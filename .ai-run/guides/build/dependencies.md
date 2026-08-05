# Changing a dependency

**Read first:** [`../README.md`](../README.md) — the guide index.
**This file owns:** which of this repo's dependency surfaces holds a given package, and the safe
command to change each one.
**Owned elsewhere:** component vocabulary, security pin comments, and what to run after a fix →
[`../security/README.md`](../security/README.md) · rebuilding an image →
[`README.md`](README.md) · what each gate proves → [`../quality-gates.md`](../quality-gates.md).

The general theory — bounded constraint operators per ecosystem, when a pin is direct versus
transitive — belongs to the tool applying the fix and is not restated here. This file covers the
repo-specific part: which file, which command.

## The rule

**Edit the manifest minimally, then run the package manager's targeted update for that one
package. Never delete or wholesale-regenerate a lock file.**

A full regeneration re-resolves every dependency at once. That widens the blast radius beyond the
package you meant to change, pulls in unrelated transitive movement, and leaves a diff nobody can
review — so a reviewer cannot tell the security fix from the churn around it.

A quiet `poetry lock` is not evidence that a full relock is safe. Loose constraints such as
a caret range admit movement the moment upstream publishes. A targeted update is bounded
by construction; a relock is bounded only by luck.

## Which surface

Five. The flagged package name alone does not tell you which — match on where the package is
*installed*.

| The package is installed | Surface | Pin style |
|---|---|---|
| Into the service's Python environment | `pyproject.toml` `[tool.poetry.dependencies]` | Range |
| Into the separate Python scripting image | `images/python/requirements.txt` | Exact `==` |
| By an MCP server tracked in this repo | `mcp-servers/*/package.json` `overrides` | Range |
| By `uvx` at container run time | `uv-constraints.txt` | Exact `==` |
| By something a Dockerfile fetches during the build | the relevant `Dockerfile` | See below |

"The relevant Dockerfile" means the root one unless the ticket names the scripting image —
[`README.md`](README.md) has the mapping.

The last row is the one that gets missed. Much of what ships in the main image is cloned or
installed *inside* the build — Go modules, npm packages from upstream MCP servers, npm's own
bundled dependencies, OS packages. None appear in any manifest, so a finding against them has no
manifest line to edit until you go into the Dockerfile.

Locate each site with its grep; the line numbers move.

| What | Where | Find it | Mechanism |
|---|---|---|---|
| npm dep of a server cloned during the build | root `Dockerfile` | `grep -n 'npm pkg set' Dockerfile` | `npm pkg set 'overrides.<pkg>'='>=<ver>'` before its `npm install` |
| npm's own bundled dep | root `Dockerfile` | `grep -n 'npm pack' Dockerfile` | `npm pack` then `tar` extract over `/usr/lib/node_modules/npm/node_modules/` |
| Go transitive of `github-mcp-server` | root `Dockerfile` | `grep -n 'go get' Dockerfile` | `go get <module>@<version>` then `go mod tidy` |
| OS package | the relevant `Dockerfile` | `grep -n 'apt-get install' Dockerfile` | Version-pinned `apt-get install`, or `apt-get purge` |
| The base image | the `FROM` line | `grep -n '^FROM' Dockerfile` | Bump the tag — needs sign-off, see `AGENTS.md` |

## Python service dependency — targeted

```bash
# Direct dependency already in pyproject.toml: bump the constraint and relock that package only.
poetry update <package>

# Transitive dependency not listed in pyproject.toml: add the explicit constraint, which
# forces the resolver onto a safe version and updates the lock in one step.
poetry add '<package>@<constraint>'

# Then confirm what you actually got — never assume the constraint resolved where you expected.
poetry show <package>

# And confirm the lock still matches the manifest.
poetry check --lock
```

Commit `pyproject.toml` and `poetry.lock` together. They are one change; splitting them leaves
the repo in a state where the lock disagrees with the manifest.

**Never** `rm poetry.lock`, and never open it in an editor — not even for one line. It is
generated output. If a package is not in `pyproject.toml`, it is transitive, and the fix is a
constraint in the manifest that forces the resolver, not a hand-edit of the resolved version.

Then run the `python-service-dependency` gates: `lock-consistency`, `lint`, `typecheck`,
`unit-tests`.

## Scripting image dependency

`images/python/requirements.txt` uses exact `==` pins for reproducibility. Edit the version in
place and keep the section comment structure. There is no lock file and no test suite for this
image, so a rebuild plus rescan is the only evidence available — see [`README.md`](README.md).

## `uvx` run-time dependency

`uv-constraints.txt` at the repo root is copied to `/etc/uv-constraints.txt` and exported as
`UV_CONSTRAINT` in the main image's runtime stage. It constrains every package `uvx` resolves
when a tool is launched inside the running container — a surface that exists at run time only.

```bash
grep -n 'uv-constraints\|UV_CONSTRAINT' Dockerfile
cat uv-constraints.txt
```

It pins `mcp` because `mcp-server-fetch` imports `McpError`, which `mcp>=2.0.0` removed. Two
things to know before touching either file:

- A `uvx`-launched tool ignores `poetry.lock` entirely. Bumping `pyproject.toml` does not move it.
- `uv-constraints.txt` and the `mcp` pin in `pyproject.toml` name the same version. Moving one
  alone leaves the image running two different SDKs; change both, in one commit.

Use exact `==` here, and carry the reason in a comment, as the existing lines do. Nothing in the
working tree verifies this file; a rebuild and a container run are the only evidence.

## npm dependency

No `package-lock.json` is committed anywhere in this repo; npm resolves at build time. That is
why the pattern is an `overrides` entry rather than a lockfile edit, and why there is no targeted
relock step to run locally.

- Server tracked in this repo → the `overrides` block in the matching `mcp-servers/*/package.json`.
- Server the build clones → add the package to the `npm pkg set` call preceding its `npm install`
  in the root `Dockerfile`.

Both take a range. Verification happens at image build, not in the working tree.

## Rules

- **Targeted update, never a full relock.** See the top of this file.
- **Never hand-edit `poetry.lock`.**
- **Never add a dependency whose license falls outside** the `allow-only` list in
  `pyproject.toml` under `[tool.pip-licenses]`.
- **A pin carrying a `# Security (EPMCDME-...)` comment is load-bearing.** Do not relax or remove
  it; the convention is owned by [`../security/README.md`](../security/README.md).
- **Adding a brand-new dependency is not a bump.** It needs review on licence, maintenance, and
  transitive footprint — not just a version choice.
- **`uv-constraints.txt` and the `mcp` pin in `pyproject.toml` move together**, in one commit.
