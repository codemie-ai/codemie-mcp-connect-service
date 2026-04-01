---
name: security-lead
description: Use this skill when the user asks to "fix a CVE", "remediate a vulnerability", "patch a security issue", "address trivy findings", or provides one or more Jira ticket IDs related to security/CVE. Acts as a security lead to guide CVE remediation from ticket analysis through Dockerfile patching, container build, and Trivy verification. Always use this skill for security-related Jira tickets even if the user just pastes a URL or ticket ID without saying "security".
version: 0.3.0
---

# Security Lead: CVE Remediation Guide

## Purpose

This skill acts as a security lead for remediating CVE vulnerabilities in container-based projects. It covers the full cycle: reading the Jira ticket, identifying the vulnerable component, choosing the right fix pattern, implementing the Dockerfile change, building the image, and verifying with Trivy.

## Container Runtime Detection

Before any build or scan command, detect which runtime is available and the host architecture:

```bash
if command -v docker &>/dev/null; then
  RUNTIME=docker
elif command -v podman &>/dev/null; then
  RUNTIME=podman
else
  echo "Neither docker nor podman found"; exit 1
fi

HOST_ARCH=$(uname -m)  # x86_64 = amd64 host, arm64/aarch64 = ARM host
```

Use these variables for all subsequent commands:

| Runtime | Host | Build command |
|---|---|---|
| Docker | amd64 | `sudo docker build -t <img> .` |
| Docker | arm64 | `sudo docker buildx build --load --platform=linux/amd64 -t <img> .` |
| Podman | any | `podman build --platform linux/amd64 --format docker -t <img> .` |

| Action | Docker | Podman |
|---|---|---|
| Trivy scan | `sudo trivy image <img> --ignore-unfixed --severity HIGH,CRITICAL` | `trivy image <img> --ignore-unfixed --severity HIGH,CRITICAL` |

Podman is rootless by default — no `sudo` needed. Docker typically needs `sudo` unless the user is in the `docker` group. `docker buildx` is only needed on ARM hosts (cross-compiling to amd64).

## Workflow

### Phase 1: Requirement Gathering

**Set ticket(s) to In Progress via brianna** — do this before any analysis or code changes so the team knows work has started:

```
Use Skill tool with skill="brianna" and args:
- Action: transition ticket to In Progress
- Ticket ID: [provided by user]
```

When multiple tickets are provided, transition them all in parallel.

**Fetch Jira ticket(s) via brianna** — request description and summary fields only:

```
Use Skill tool with skill="brianna" and args:
- Action: get ticket details
- Ticket ID: [provided by user]
- Fields: description, summary ONLY
```

When multiple tickets are provided, fetch them in parallel. Extract from each ticket:
- **CVE ID** (e.g. CVE-2026-33671)
- **Package name** (e.g. openssl, picomatch)
- **Installed version** (e.g. 2.3.1)
- **Fixed version(s)** (e.g. 2.3.2, 3.0.2)
- **Severity** (HIGH / CRITICAL)
- **Target** (Node.js / OS / Python / other)

### Phase 2: CVE Analysis

First, check the `FROM` line in the Dockerfile to identify the base OS. Then identify the component category — this determines the fix strategy:

| Target | Package manager | Fix Strategy |
|---|---|---|
| OS package (Debian/Ubuntu) | apt | Bump pinned `ARG` version or add `apt-get install` pin layer |
| OS package (Alpine) | apk | Bump pinned `ARG` version or add `apk add --upgrade` layer |
| OS package (RHEL/CentOS/Fedora/UBI) | dnf/yum | Add `dnf update -y <pkg>` layer |
| Node.js (npm bundled) | npm | Copy-dance patch (see `references/remediation-patterns.md`) |
| Node.js (transitive/nested) | npm | Find-based patch (see `references/remediation-patterns.md`) |
| Node.js (direct) | npm | Bump pinned `ARG` version |
| Python | pip | Bump version in `requirements.txt` or add `pip install --upgrade` layer |

Check the git log for previous fixes to understand the project's established patterns:
```bash
git log --oneline -- Dockerfile | head -10
git show <commit> -- Dockerfile
```

### Phase 3: Determine Image Name

Look for the image name in:
- `Makefile` (build targets)
- `docker-compose.yml` / `compose.yaml`
- CI/CD pipeline files (`.gitlab-ci.yml`, `.github/workflows/*.yml`, `Jenkinsfile`)
- The project directory name as a fallback

### Phase 4: Branch Creation

Create a feature branch before any changes. For multiple related CVEs (same package or same CVE ID across versions), use a single branch:

```bash
git checkout -b <TICKET-ID>
```

If the branch already exists, switch to it:
```bash
git checkout <TICKET-ID>
```

### Phase 5: Implement the Fix

Apply the appropriate pattern from `references/remediation-patterns.md`.

**Key rules:**
- Always add a `TODO` comment above each patch layer explaining when it can be removed (e.g., "Remove once base image ships with X >= Y")
- Place `ARG` declarations immediately before the `RUN` that uses them
- Combine multiple fixes for the same CVE into as few layers as possible
- Before choosing a target version, verify what is actually available in the package registry

**Checking latest package versions:**
- Debian/Ubuntu: `https://packages.debian.org/` or `apt-cache madison <pkg>` inside a container
- Alpine: `https://pkgs.alpinelinux.org/packages`
- RHEL/Fedora: `https://packages.fedoraproject.org/`
- npm: `npm show <pkg> version`
- pip: `pip index versions <pkg>` or check `https://pypi.org/project/<pkg>/`

### Phase 5.5: codemie-mcp-connect-service Pre-Build Requirement

**When working in the `codemie-mcp-connect-service` repo**, the Dockerfile's `mcp-servers` stage copies `ai-run-mcp-servers/` from the build context. This directory is not part of the repo and must be cloned before building:

```bash
cd <project-root>
git clone git@gitbud.epam.com:epm-cdme/ai-run-mcp-servers.git
```

**Before committing**, delete it so it is never committed to the repo:

```bash
rm -rf ai-run-mcp-servers
```

Do this cleanup immediately after a successful Trivy scan, before Phase 8.

### Phase 6: Build and Verify

**Build** using the command from Container Runtime Detection that matches your runtime and host.

If the build fails, read the error — most failures are package version mismatches or install conflicts. Check the appropriate package registry for the actual available version, adjust, and rebuild.

**Scan** after a successful build:
```bash
# Docker:
sudo trivy image <image-name> --ignore-unfixed --severity HIGH,CRITICAL

# Podman:
trivy image <image-name> --ignore-unfixed --severity HIGH,CRITICAL
```

Parse the results:
- If the patched CVE still appears → the fix didn't reach the vulnerable location; revisit the remediation pattern
- If new CVEs appear that weren't in the original ticket → note them but don't fix unless asked
- If output shows `0` vulnerabilities for the fixed packages → proceed to Phase 7

### Phase 7: Report Results

Provide a concise summary table:

```
| CVE | Package | Before | After | Status |
|-----|---------|--------|-------|--------|
| CVE-XXXX-YYYY | pkg | old-ver | new-ver | Fixed |
```

If a CVE still shows after fixing, iterate: inspect the exact path Trivy reported, compare with what the fix targeted, and adjust the remediation layer.

### Phase 8: Commit and MR

After successful Trivy verification, use the `gitlab-mr` skill to commit, push, and create the MR.

The commit message must reference all fixed ticket IDs:
```
<TICKET-ID>: Remediate CVE-XXXX-YYYY by patching <package> in <location>
```

For multiple tickets fixing the same CVE:
```
<TICKET-ID1>, <TICKET-ID2>: Remediate CVE-XXXX-YYYY by patching <package>
```

## Batching Multiple Tickets

When fixing multiple CVEs in one session:
- Same CVE across different versions of the same package → single branch, single commit
- Different CVEs on different packages → single branch, can still be one commit if they're in the same Dockerfile
- Reference all ticket IDs in the commit message

## Key Principles

- Detect docker vs podman at the start — don't hardcode either
- Check the `FROM` line before picking a fix pattern — distro determines the package manager
- Read existing patch layers in the Dockerfile before writing new ones — follow the exact same pattern
- Never remove existing TODO-marked patch layers unless the Trivy scan confirms the CVE is gone without them
- Prefer bumping a direct version (ARG) over adding a patch layer when possible — fewer layers is cleaner
- A patch layer that passes Trivy is correct even if the approach differs from what you expected

## Reference Files

- **`references/remediation-patterns.md`** — Detailed patterns for each fix type with templates
