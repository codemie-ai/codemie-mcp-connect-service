# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | CodeMie MCP Connect Service | README.md:1, pyproject.toml:2 |
| Repository/package | codemie-mcp-connect-service | pyproject.toml:2 |
| Project code/key | EPMCDME | git log (all commits), .claude/skills/gitlab-mr/SKILL.md:3 |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Jira |
| Key/prefix | EPMCDME |

## Ticket Adapter

**Status**: configured
**Adapter**: Invoke the `codemie-jira-assistant` skill via the Skill tool.
**Lookup**: Invoke the `codemie-jira-assistant` skill with the ticket key and a request for summary, description, acceptance criteria, and links.
**Create**: Invoke the `codemie-jira-assistant` skill with the complete ticket payload or approved story file as the argument.
**Output**: Ticket key and URL returned by the skill.

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitLab |
| Repository remote | https://gitbud.epam.com/epm-cdme/codemie-mcp-connect-service |
| Default target branch | main |
| Review artifact type | MR |

## MR Adapter

**Status**: configured
**Adapter**: `glab` CLI via `.claude/skills/gitlab-mr` skill
**Instructions**: Use the `gitlab-mr` skill for commit + push + MR creation workflow. Skill enforces EPMCDME-xxx ticket format in commit messages, manages git push with upstream tracking, and creates GitLab MRs. See `.claude/skills/gitlab-mr/SKILL.md` for full workflow.

## Complexity Scoring

**Status**: configured
**Field**: Labels
**Format**: t-shirt

## Lifecycle Intent Handling

### record_complexity_score
Via the `codemie-jira-assistant` skill, add a complexity label to the ticket with the size from `data.complexity_size` (XS–XXL, as-is):
`initial` → `sdlc-factory-est-<SIZE>`, `actual` → `sdlc-factory-act-<SIZE>`. Add only — never remove or change existing labels, so an `sdlc-standard` ticket ends with both labels.
Ticket ID: from the branch name (`EPMCDME-\d+`) or the run work item.

### get_field
For `Labels`: always return `field_value: null` — complexity labels are additive, there is nothing to overwrite.
