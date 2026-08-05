# Building and scanning images

**Read first:** [`../README.md`](../README.md) — the guide index.
**This file owns:** which Dockerfile is the repository's main image and which are not, their
contexts and paths, registry access, build stages, and scanning.
**Owned elsewhere:** which manifest a package lives in →
[`dependencies.md`](dependencies.md) · which component a ticket means and the full remediation
process, and the component vocabulary → [`../security/README.md`](../security/README.md).

Rebuilding and rescanning is the only way to prove a container CVE is gone.

## Which Dockerfile is which

Four are tracked. **Only the root one is this repository's product.**

| Dockerfile | Standing | Build context |
|---|---|---|
| `Dockerfile` (repo root) | **The main image.** The service itself, and the only image the Helm chart under `deploy-templates/` deploys | repo root |
| `images/python/Dockerfile` | **Separate, additional image.** A standalone Python scripting runtime. Not the service, but live: built, scanned, and the target of its own CVE tickets | `images/python/` |
| `mcp-servers/postgres-typescript/Dockerfile`, `mcp-servers/puppeteer-typescript/Dockerfile` | Per-server images that nothing in this repository builds or references. The root build compiles both servers from source in its `mcp-servers` stage instead | that server's directory |

Base image tags are omitted on purpose — they move with every base bump. Read the current set,
and confirm the file list, from the tree:

```bash
git ls-files '*Dockerfile*'
git ls-files '*Dockerfile*' | xargs grep -nE '^FROM'
```

**An unqualified "the Dockerfile" means the root one.** `images/python/Dockerfile` is reached
only through a ticket naming `codemie-python` or `codemie-mcp-connect-service-python` — both
names are that same second image, per the component table in
[`../security/README.md`](../security/README.md). Editing the root file for a finding against the
scripting image, or the reverse, produces a diff that changes nothing in the scanned artifact.

## Build commands

From `README.md` and `images/python/README.md`.

```bash
# The main image. Context is the repo root: the build copies mcp-servers/, src/, scripts/,
# pyproject.toml, poetry.lock, uv-constraints.txt, and README.md.
docker build --platform linux/amd64 -t codemie-mcp-connect-service .

# The additional scripting image.
docker build -t codemie-python images/python/
```

`images/python` declares five build args — `grep -n '^ARG' images/python/Dockerfile` lists them,
and `images/python/README.md` tabulates the defaults. The only one you would normally set is
`INSTALL_SIMPLE_DECK`, default `false`. True installs `simple-deck` from PyPI in the same layer
as the rest of `requirements.txt` — no credentials, no extra index, no build secret:

```bash
docker build --build-arg INSTALL_SIMPLE_DECK=true -t codemie-python images/python/
```

## Registry access comes first

Both images pull base layers from `dhi.io`, which is private. A build can fail on authentication
before it ever reads a line you changed, so confirm access first — a login is something only a
human can supply, and discovering that after the diff is written wastes the run.

Probe the tags the Dockerfiles name right now, with the same runtime you will build with —
`docker` and `podman` keep separate credentials, so a login to one does not authenticate the
other:

```bash
# External base tags only — the grep for ':' drops internal stage names like `base`.
git ls-files '*Dockerfile*' | xargs grep -hE '^FROM' | awk '{print $2}' | grep ':' | sort -u \
  | xargs -n1 docker manifest inspect > /dev/null
```

Exit non-zero, or `unauthorized`, means log in to that registry (`docker login dhi.io`) before
starting. **A build that fails on authentication is a check that did not run, never a failed
fix.**

## What the main build actually does

Multi-stage. Knowing what each stage is for prevents editing the wrong one. List the current
stages and their boundaries first:

```bash
grep -n '^FROM' Dockerfile
```

| Stage | What it is for |
|---|---|
| `github-mcp-build` | Clones `github/github-mcp-server`, applies Go module pins, builds the binary |
| `base` | The Python base plus apt packages, Node, Maven, and the JDKs |
| `mcp-servers` | Clones upstream MCP servers and builds the ones under `mcp-servers/` |
| `app-builder` | Poetry installs the service into a project-local `.venv` |
| `runtime` | Installs uv and ngrok, creates the unprivileged `codemie` user, copies the venv and source in |

The runtime stage also sets `ENV UV_CONSTRAINT=/etc/uv-constraints.txt`, from the repo-root
`uv-constraints.txt` it copies in. That file constrains every tool `uvx` installs *at container
run time* — a dependency surface that exists only inside the running image and appears in no
lock file. It is what holds `mcp-server-fetch` off the newest `mcp` release. Adding a constraint
there is a real dependency change; see [`dependencies.md`](dependencies.md).

```bash
grep -n 'uv-constraints\|UV_CONSTRAINT' Dockerfile
```

The build is long: three JDK downloads, a Chromium install, several `git clone` and `npm install`
steps. It needs network throughout. There are no `pre_build` steps to run yourself; every
external dependency is fetched inside the build.

## Scan

```bash
trivy image --severity HIGH,CRITICAL codemie-mcp-connect-service
```

On a runner with no container daemon, save an OCI tar at build time and scan the tar instead.

Verify the specific CVE rather than eyeballing a list. The fix holds only when the named CVE is
absent from the rebuilt image; a shorter findings list is not proof that yours is the one gone.

## Failure modes

- **A network failure is not a clean scan.** A build or pull that fails on DNS, auth, or rate
  limiting means the gate did not run. Report it as unverified and stop.
- **A stale local tag scans clean while the fix is untested.** Rebuild before every scan, or tag
  each verification build distinctly.
- **`images/python` has no test suite.** Rebuild and rescan are the only evidence for it.
- **The service image carries far more than the service.** A finding can come from Node, Java,
  Go, Chromium, or an MCP server, none of which live in `pyproject.toml`. Match the flagged
  package to its surface in [`dependencies.md`](dependencies.md) before editing.
