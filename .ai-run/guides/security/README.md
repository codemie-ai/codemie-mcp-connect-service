# Fixing a security finding in this repository

**Read first:** [`../README.md`](../README.md) — the guide index.
**This file owns:** the order of a remediation, the component vocabulary, what may be edited for
each component, and what to run afterwards.
**Owned elsewhere:** which manifest holds a package and the command to move it →
[`../build/dependencies.md`](../build/dependencies.md) · building and scanning an image →
[`../build/README.md`](../build/README.md) · what each gate proves →
[`../quality-gates.md`](../quality-gates.md) · branch and commit format →
[`../standards/git-workflow.md`](../standards/git-workflow.md).

This file does not restate general remediation theory. Bounded constraint operators per
ecosystem, the OS-package decision tree, and when a Dockerfile override is a last resort belong
to the tooling that drives the fix. Follow it; here is only what is specific to this repository.

## Where to find the current values

**Nothing below is copied into this document.** A version, a gate list, or a dependency set
written down here would be a snapshot that rots silently. Run the command instead — its answer
is correct on the day you run it.

| You need | Run |
|---|---|
| The gate commands this repo declares | `grep -A6 'tool.poetry.scripts' pyproject.toml` and `grep -E '^[a-z-]+:' Makefile` |
| Every image and its Dockerfile | `git ls-files '*Dockerfile*'` |
| Which pins are load-bearing security fixes | `grep -rn "Security (EPMCDME" Dockerfile pyproject.toml images/ mcp-servers/` |
| What a package currently resolves to | `poetry show <package>` |
| Whether a package is direct or transitive | `poetry show --tree \| grep -B3 <package>` |
| Which manifests exist at all | `git ls-files '*pyproject.toml' '*requirements*.txt' '*package.json' '*.lock'` |
| Whether anything re-checks this after merge | `ls .gitlab-ci.yml .github/workflows 2>&1` — nothing does today |
| What the last comparable fix looked like | `git log --oneline --grep='CVE' -15`, then `git show <sha>` |

The last row is the most useful and the most skipped. This repository has fixed dozens of CVEs;
the pattern for your case almost certainly already exists in its history.

## The order

Steps 1 and 2 are the ones that get skipped, and skipping either produces a fix in a file that
has no effect on the scanned artifact.

1. **Identify the component** — the vocabulary section below.
2. **Locate the surface the package actually lives on** — five of them, including the build
   itself and the `uvx` run-time constraint file. The table is in
   [`../build/dependencies.md`](../build/dependencies.md).
3. **Classify the fix location by the nature of the finding.** An OS package is fixed in the
   image layer; a language package is fixed in its manifest, never as a Dockerfile override,
   because an override leaves the lock file vulnerable for every other consumer.
4. **Apply the minimal change** with a pin comment.
5. **Run what that change requires** — the table under § After the fix.
6. **Commit** as `EPMCDME-NNNNN: <action>`, naming the CVEs in the body.

## Component vocabulary

A ticket names an image; the repository names directories. This mapping exists nowhere in the
code, so it cannot be derived — it is the one thing here worth stating outright.

| Ticket says | Means | May touch |
|---|---|---|
| `codemie-mcp-connect-service` | The main image: root `Dockerfile`, build context `.` | `Dockerfile`, `pyproject.toml`, `poetry.lock`, `uv-constraints.txt`, `src/`, `tests/`, `mcp-servers/*/package.json` |
| `codemie-python` **or** `codemie-mcp-connect-service-python` | The separate additional image: `images/python/` | `images/python/Dockerfile`, `images/python/requirements.txt` |

Both ticket names in the second row are the same image. Editing outside a component's column
changes something the finding was never about.

The two rows are two different images with different lifecycles, not two halves of one product.
The first is the service this repository ships; the second is an older standalone scripting
runtime that is still built and still scanned. Which Dockerfile belongs to which, and why the
two under `mcp-servers/` belong to neither, is in
[`../build/README.md`](../build/README.md) § Which Dockerfile is which.

## After the fix — what to run

Scope the verification to what you changed. Running the whole set on a Dockerfile-only edit
proves nothing extra; running none of it on a manifest edit proves nothing at all.

| What you changed | Run | Why |
|---|---|---|
| `pyproject.toml` / `poetry.lock` | `poetry check --lock`, then the blocking gates in [`../quality-gates.md`](../quality-gates.md), then rebuild + rescan | The lock must agree with the manifest before any later gate means anything |
| `src/` as part of the fix | The blocking gates, plus a test covering the changed path | |
| A `Dockerfile` only | Rebuild + rescan — [`../build/README.md`](../build/README.md) | No gate sees inside the image |
| `images/python/` | Rebuild + rescan only | That image has no tests and no lock file |
| `mcp-servers/*/package.json` | Rebuild + rescan only | npm resolves at build time; no lock file is committed |
| `uv-constraints.txt` | Rebuild, then launch the affected `uvx` tool in the container | The constraint applies at run time; a scan of the built image does not exercise it |

Verify the **named** CVE is absent from the rebuilt image. A shorter findings list is not
evidence that yours is the one that went away.

## Gates that block, and commands that only look like gates

Which gates are blocking, and which commands mislead, is observed behaviour — no config file
states it. Both tables live in [`../quality-gates.md`](../quality-gates.md); read the traps table
there before treating any exit code as a verdict.

The short version: `pytest -m integration` collects nothing and exits 5, `pip-licenses` across
the whole environment exits 1 on a dev dependency, and `pre-commit` has no configuration to run.
The first is inside the pre-merge chain in `README.md`, which therefore cannot pass as written.

**A gate that could not run is not a gate that passed.** A build failing on registry access, a
scanner with a stale database — report unverified and stop.

## Never regenerate a lock file

Change the one package, then run that package manager's targeted update for that one package. A
full relock re-resolves everything, so the security fix becomes indistinguishable from unrelated
churn and no reviewer can separate them. Commands: [`../build/dependencies.md`](../build/dependencies.md).

Commit the manifest and its lock file together, or the repository has a state where the two
disagree.

## Every security pin carries a comment

A pin without a comment is indistinguishable from an ordinary version bump, and the next person
to touch the constraint relaxes it. Find the existing examples with the `grep` in the table
above; copy their shape.

```toml
# Security (EPMCDME-12875): pin >=0.0.31 to fix CVE-2026-53539, CVE-2026-53538,
# CVE-2026-53537, CVE-2026-53540 (multipart form parsing vulnerabilities)
```

Such a pin is load-bearing. Do not relax or remove it as cleanup. When upstream ships the fix,
remove it in its own commit that says so — the `# TODO: Remove once ...` lines above the Go pins
in the root `Dockerfile` are the pattern.

**Known divergence:** most pins in `pyproject.toml` still use unbounded `>=`, which admits the
next breaking release. Two do not: `fastapi` uses a caret, and `mcp` is pinned exactly, because
`uv-constraints.txt` must name the same version — see
[`../build/dependencies.md`](../build/dependencies.md) § `uvx` run-time dependency. New pins
should use the tightest bounded form the ecosystem offers, unless matching an existing unbounded
line in the same block. Converting the existing ones is a separate change with its own testing.

## Secrets

`gitleaks` is a blocking gate. A leaked credential is never fixed by deleting the line: it is
compromised the moment it is committed and must be rotated by a human. Scrubbing the working
tree without rotating leaves a live secret in the history and wherever it was already used.
