---
name: gitlab-mr
description: Manages git commits with Jira tickets (EPMCDME-xxx format), pushes, and GitLab MR creation. Works in any GitLab repository — repo info is detected at runtime. Use this skill whenever the user says "commit changes", "push changes", "create MR", "make merge request", "push and open PR", or any similar GitLab workflow request. Enforces Jira ticket format in commit messages.
version: 1.0.0
---

# GitLab Merge Request Workflow

## Instructions

### 1. Check Current State

Start by checking the repo state so you know what you're working with:

```bash
# Current branch and remote
git branch --show-current
git remote get-url origin

# Uncommitted changes
git status --short

# Existing MR for current branch
glab mr list --source-branch=$(git branch --show-current) 2>/dev/null || echo "No MR"
```

### 2. Validate Jira Ticket (Required for Commits)

Before committing, confirm a Jira ticket is in context:

- Look for `EPMCDME-xxx` pattern in the conversation
- Check if the user provided a ticket number
- If none found: ask — "What is the Jira ticket number (EPMCDME-xxx) for this commit?"

Don't commit without a ticket — it's required for traceability.

### 3. Handle Based on User Request

**"commit changes"** → Commit only:
```bash
git add .
git commit -m "EPMCDME-xxx: Action and message"
```

**"push changes"** → Push only:
```bash
git push --set-upstream origin $(git branch --show-current)
```

**"create MR"** → Full workflow (see step 4).

### 4. Create MR Workflow

#### If on `main` branch:
1. Create a feature branch first: `git checkout -b <type>/<description>`
2. Then commit, push, and open MR

#### If MR already exists:
```bash
git push --set-upstream origin $(git branch --show-current)
# Report: "Changes pushed to existing MR: <url>"
```

#### If no MR exists:
```bash
git push --set-upstream origin $(git branch --show-current)

glab mr create \
  --title "EPMCDME-xxx: Brief description" \
  --description "## Summary
[2-4 sentence overview]

## Changes
- [Key highlights only]

## Impact
[Optional: before/after for user-facing changes]

## Checklist
- [ ] Self-reviewed
- [ ] Manual testing performed
- [ ] Documentation updated (if needed)
- [ ] No breaking changes (or documented)"
```

## Commit Format

**Required Pattern**: `EPMCDME-xxx: Action and message`

```bash
# Valid
git commit -m "EPMCDME-123: Add new documentation"
git commit -m "EPMCDME-456: Fix authentication bug"
git commit -m "EPMCDME-789: Refactor user service"

# Invalid
git commit -m "Add new feature"            # Missing ticket
git commit -m "feat: add feature"          # Wrong format
git commit -m "EPMCDME-123 add feature"    # Missing colon
```

## Branch Format

**Pattern**: `<type>/<description>` — Jira ticket is optional in the branch name

```
feat/add-user-profile
fix/auth-timeout
docs/api-guide
feat/EPMCDME-123-user-settings
```

## MR Title Format

**Pattern**: `EPMCDME-xxx: Brief description` — always lead with the ticket number.

## Troubleshooting

### "glab: command not found"
```bash
brew install glab        # macOS
snap install glab        # Linux
```

### No Jira ticket in context
Ask the user: "What is the Jira ticket number (EPMCDME-xxx) for this commit?"
Validate it matches `EPMCDME-\d+` before proceeding.

### Already on main branch
Create a feature branch before committing:
```bash
git checkout -b <type>/<short-description>
```

### No changes to commit
Check `git status` — nothing staged or working tree is clean.

### MR already exists
Push to the existing MR; don't create a new one.

## Examples

**User**: "commit these auth changes for EPMCDME-456"
```bash
git add .
git commit -m "EPMCDME-456: Fix OAuth2 token refresh"
```

**User**: "commit the changes" (no ticket mentioned)
→ Ask for ticket, then commit once provided.

**User**: "push and create MR for EPMCDME-321"
1. Check for existing MR
2. Commit: `EPMCDME-321: <description>`
3. Push branch
4. Create MR titled `EPMCDME-321: <description>`

**User**: "push my changes"
1. Check if MR exists
2. Push to existing MR, or push-only if none exists (don't create MR unless asked)
