# CLAUDE.md

Guidance for Claude Code when working with this repository.

@AGENTS.md

---

## Claude Code Specific Notes

- Use the `gitlab-mr` skill for commit + MR workflow (enforces EPMCDME-xxx ticket format)
- Use the `security-lead` skill for CVE remediation workflow
- Virtual environment activation is mandatory: `source .venv/bin/activate`
- All quality checks must pass before commit: see AGENTS.md for comprehensive pre-commit check
