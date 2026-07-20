# Git Workflow

## Branch Naming Convention

**Pattern**: `EPMCDME-XXXX`, `EPMCDME-XXXX_short-description`, or `EPMCDME-XXXX-short-description`

All feature, bugfix, and task branches MUST start with a Jira ticket number. A description is optional and can be separated by underscore or hyphen.

| Good | Bad |
|---|---|
| `EPMCDME-13528` | `feature/sdlc-factory` (no ticket) |
| `EPMCDME-13528_implement-sdlc-factory` | `fix-dockerfile` (no ticket) |
| `EPMCDME-13321-remove-obsolete-patches` | `branch-without-ticket` (no ticket) |
| `EPMCDME-13179_upgrade-libssh2` | `EPMCDME` (incomplete) |

**Evidence**: git branch -a shows current branch `EPMCDME-13528-Implement-sdlc-factory`, remote branches follow pattern

## Commit Message Format

**Pattern**: `EPMCDME-XXXX: Action and description`

Format follows conventional commits with mandatory Jira ticket prefix. All commits MUST start with `EPMCDME-XXXX:` followed by a concise imperative-mood description.

**Required by**: `.claude/skills/gitlab-mr/SKILL.md` enforces this format before allowing commits

| Good | Bad |
|---|---|
| `EPMCDME-13321: Remove obsolete security patch overrides from Dockerfile` | `Remove obsolete patches` (no ticket) |
| `EPMCDME-13179: Upgrade libssh2-1t64 to 1.11.1-1+deb13u1 to fix CVE-2026-55200` | `EPMCDME-13179 upgrade libssh2` (missing colon) |
| `EPMCDME-13007: Remediate CVE-2026-12151 (undici) and CVE-2026-23879 (py7zr)` | `Fixed some CVEs` (vague, no ticket) |

**Evidence**: `git log --oneline -10` shows 100% compliance with EPMCDME-XXXX: format

**Components**:
1. **Ticket Prefix**: `EPMCDME-XXXX:` (required, enforced by gitlab-mr skill)
2. **Action**: Imperative verb (Add, Remove, Fix, Upgrade, Implement, Refactor, etc.)
3. **Description**: Clear description of what changed and why (may include CVE numbers, component names)

**Conventional Commit Types** (from CONTRIBUTING.md):
- `feat(<scope>):` — new feature
- `fix(<scope>):` — bug fix
- `docs(<scope>):` — documentation changes
- `style(<scope>):` — formatting, no code change
- `refactor(<scope>):` — code restructure without behavior change
- `perf(<scope>):` — performance improvement
- `test(<scope>):` — add or update tests
- `chore(<scope>):` — maintenance tasks
- `ci(<scope>):` — CI/CD pipeline changes

**Scopes** (from CONTRIBUTING.md): `api`, `bridge`, `cache`, `auth`, `transport`, `docker`, `config`, `docs`

## Merge Strategy

**Strategy**: Squash merge

GitLab MRs are squashed into a single commit when merged to `main`. This keeps the main branch history clean while preserving full context in MR discussions.

**Why**: Production service with multiple contributors — squash merge ensures clean linear history on main branch while detailed commit history remains visible in MRs.

## Anti-Patterns

| Avoid | Prefer | Why |
|---|---|---|
| Committing without ticket number | Wait for ticket assignment or ask for it | Traceability requirement — `.claude/skills/gitlab-mr/SKILL.md` will block commits without EPMCDME-xxx |
| `git commit -m "wip"` or `git commit -m "fixes"` | Descriptive commit with ticket and clear action | Commit messages are project documentation |
| Force-pushing to `main` | Never force-push to main | Destructive — would overwrite team's work |
| Multiple unrelated changes in one commit | One logical change per commit | Easier to review, revert, and understand |
| Committing without running quality checks | Run full pre-commit check (see quality-gates.md) before committing | Prevents CI failures and broken builds |

## Workflow Steps

**Using gitlab-mr skill** (recommended):

1. Make code changes
2. Invoke `gitlab-mr` skill — it will:
   - Check git status and current branch
   - Validate Jira ticket is in context (asks if not found)
   - Stage changes with `git add`
   - Create commit with `EPMCDME-xxx: Message` format
   - Push with `--set-upstream` if needed
   - Create GitLab MR via `glab mr create`

**Manual workflow** (if not using skill):

1. Ensure on feature branch: `git branch --show-current`
2. Stage changes: `git add <files>` (prefer specific files over `git add .`)
3. Run quality checks: see `.ai-run/guides/quality-gates.md`
4. Commit with ticket: `git commit -m "EPMCDME-xxx: Description"`
5. Push: `git push --set-upstream origin $(git branch --show-current)`
6. Create MR: `glab mr create --title "EPMCDME-xxx: Title" --fill`

## Troubleshooting

| Issue | Solution |
|---|---|
| gitlab-mr skill blocks commit (no ticket found) | Provide ticket number in conversation: "Use ticket EPMCDME-12345" |
| Pre-commit hooks fail | Fix reported issues (format, lint, type errors), then retry commit |
| `git push` rejected (branch diverged) | Pull latest changes: `git pull origin $(git branch --show-current)`, resolve conflicts, then push |
| Accidentally committed to `main` | Create feature branch: `git checkout -b EPMCDME-xxx_fix`, reset main: `git checkout main && git reset --hard origin/main` |
| MR conflicts with target branch | Pull main into feature branch: `git checkout EPMCDME-xxx_branch && git pull origin main`, resolve conflicts, push |

**Evidence**:
- `.claude/skills/gitlab-mr/SKILL.md`:1-50 — skill enforces ticket format and workflow
- `CONTRIBUTING.md`:9-41 — documented contribution workflow
- `git log --oneline -10` — 100% EPMCDME-xxx: format compliance
- `git remote -v` — GitLab remote at gitbud.epam.com
