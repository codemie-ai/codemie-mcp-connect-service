# CVE Remediation Patterns

Templates for common fix types. Always check `git log -- Dockerfile` first to see what patterns the project already uses — follow them for consistency.

---

## Pattern 1: OS Package Version Bump

Use when: the CVE is in an OS package installed via the system package manager.

Detect the distro from the `FROM` line in the Dockerfile:
- `debian`, `ubuntu` → apt
- `alpine` → apk
- `rhel`, `centos`, `fedora`, `ubi` → dnf or yum

### Apt (Debian/Ubuntu)

If the package is already pinned via an `ARG`, bump the `ARG` to a version that includes the fix. No TODO comment needed — this is just a version bump.

```dockerfile
ARG PACKAGE_VERSION=<new-fixed-version>
# The existing RUN apt-get install already references ${PACKAGE_VERSION}
```

If the package is not pinned, add a layer:
```dockerfile
# TODO: Remove once base image ships with <pkg> >= <fixed-version>
# Remediation for <CVE-ID> (<pkg>@<vulnerable-version>)
RUN apt-get update && apt-get install -y --no-install-recommends <pkg>=<fixed-version> && rm -rf /var/lib/apt/lists/*
```

Check available versions: `https://packages.debian.org/<codename>/<pkg>` or run `apt-cache madison <pkg>` inside a container based on the same image.

### Apk (Alpine)

If the package is pinned via an `ARG`, bump it. Otherwise, add an upgrade layer:

```dockerfile
# TODO: Remove once base image ships with <pkg> >= <fixed-version>
# Remediation for <CVE-ID> (<pkg>@<vulnerable-version>)
RUN apk update && apk add --upgrade --no-cache <pkg>=<fixed-version>-r<revision> && rm -rf /var/cache/apk/*
```

Check available versions: `https://pkgs.alpinelinux.org/packages`

### Dnf/Yum (RHEL/CentOS/Fedora/UBI)

```dockerfile
# TODO: Remove once base image ships with <pkg> >= <fixed-version>
# Remediation for <CVE-ID> (<pkg>@<vulnerable-version>)
RUN dnf update -y <pkg> && dnf clean all
```

Check available versions: `https://packages.fedoraproject.org/` or the appropriate RHEL/CentOS package mirror.

---

## Pattern 2: npm Bundled Dependency — Copy-Dance

Use when: the CVE is in a package that npm (the package manager itself) bundles in its own `node_modules`. Trivy reports the path as something like:
```
$(npm root -g)/npm/node_modules/<pkg>/
```

**How it works:**
1. Install the patched version globally (it lands at `$(npm root -g)/<pkg>`)
2. Copy it into npm's internal bundle (replacing the vulnerable nested copy)
3. Uninstall from global (cleanup)
4. Clean npm cache

```dockerfile
# TODO: Remove this layer once the base image ships with <pkg> >= <fixed-version>
# Remediation for <CVE-ID> (<pkg>@<vulnerable-version> bundled in npm)
ARG <PKG>_VERSION=<fixed-version>
RUN npm install -g <pkg>@${<PKG>_VERSION} \
    && <PKG>_SRC="$(npm root -g)/<pkg>" \
    && <PKG>_DST="$(npm root -g)/npm/node_modules/<pkg>" \
    && rm -rf "$<PKG>_DST" \
    && cp -r "$<PKG>_SRC" "$<PKG>_DST" \
    && npm uninstall -g <pkg> \
    && npm cache clean --force
```

**Placement:** BEFORE any app-level `npm install -g` that follows.

---

## Pattern 3: npm Transitive/Nested Dependency — Find-Based Patch

Use when: the CVE is in a transitive dependency of an installed tool, and it may be nested in multiple subdirectories rather than at a single known path. Trivy reports paths like:
```
$(npm root -g)/<some-tool>/node_modules/<pkg>/
```

**How it works:**
1. Install the patched version globally (it lands at `$(npm root -g)/<pkg>`)
2. Use `find` + `grep` to locate ALL nested copies matching the vulnerable version
3. Replace each with the patched version
4. Uninstall from global (cleanup)
5. Clean npm cache

The `grep -q '"version": "<vulnerable>"'` approach is reliable — it matches the exact version string in `package.json` without needing to parse JSON.

```dockerfile
# TODO: Remove this layer once <dependent-tool> ships with <pkg> >= <fixed-version>
# Remediation for <CVE-ID> (<pkg>@<vulnerable-version> nested in <dependent-tool>)
ARG <PKG>_VERSION=<fixed-version>
RUN npm install -g <pkg>@${<PKG>_VERSION} \
    && <PKG>_SRC="$(npm root -g)/<pkg>" \
    && find "$(npm root -g)" -mindepth 2 -name "<pkg>" -type d | while read dir; do \
           grep -q '"version": "<vulnerable-version>"' "$dir/package.json" 2>/dev/null \
           && rm -rf "$dir" \
           && cp -r "$<PKG>_SRC" "$dir" \
           || true; \
       done \
    && npm uninstall -g <pkg> \
    && npm cache clean --force
```

**Placement:** AFTER the tool install that brought in the vulnerable transitive dep.

**Why `|| true`?**
`SHELL ["/bin/bash", "-o", "pipefail", "-c"]` means any failed command in a pipeline fails the layer. The `grep -q ... && rm ... && cp ...` compound returns non-zero when the version doesn't match — that's expected and means "this copy is not vulnerable, skip it". `|| true` suppresses that exit code so the loop continues without error.

---

## Pattern 4: Direct npm Dependency — Version Bump in ARG

Use when: the CVE is in a package installed directly via `npm install -g` in the Dockerfile (i.e., it's pinned as a top-level dependency).

```dockerfile
ARG <PKG>_VERSION=<fixed-version>
# ... existing: RUN npm install -g <pkg>@${<PKG>_VERSION} ...
```

No TODO comment needed — this is just a version bump of a pinned dependency.

---

## Pattern 5: Python Dependency — pip Upgrade

Use when: the CVE is in a Python package.

**If pinned in `requirements.txt`:** bump the version directly in the file.

**If installed in the Dockerfile via pip, add a layer:**
```dockerfile
# TODO: Remove once base image ships with <pkg> >= <fixed-version>
# Remediation for <CVE-ID> (<pkg>@<vulnerable-version>)
RUN pip install --no-cache-dir "<pkg>==<fixed-version>"
```

Check available versions: `pip index versions <pkg>` or `https://pypi.org/project/<pkg>/#history`

---

## Choosing the Right Pattern

**Step 1 — Identify the target from Trivy output or the Jira ticket:**

| Trivy target field | Package manager | Pattern |
|---|---|---|
| `debian` / `ubuntu` | apt | Pattern 1 (apt) |
| `alpine` | apk | Pattern 1 (apk) |
| `rhel` / `centos` / `fedora` / `ubi` | dnf/yum | Pattern 1 (dnf) |
| `Node.js` | npm | See Step 2 |
| `Python` | pip | Pattern 5 |

**Step 2 — For Node.js vulnerabilities, check the path Trivy reports:**

| Path pattern | Pattern to use |
|---|---|
| `.../npm/node_modules/<pkg>/` | Pattern 2 (copy-dance) |
| `.../<some-tool>/node_modules/<pkg>/` | Pattern 3 (find-based) |
| Top-level installed package | Pattern 4 (version bump) |

When in doubt for Node.js, use Pattern 3 (find-based) — it's comprehensive and will catch all nested copies regardless of location.

**Step 3 — If the Dockerfile `FROM` line doesn't make the OS obvious**, run:
```bash
docker run --rm <base-image> cat /etc/os-release
```
