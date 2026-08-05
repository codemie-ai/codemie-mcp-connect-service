# CLAUDE.md

Guidance for Claude Code when working with this repository.

@AGENTS.md

---

## Claude Code Specific Notes

- Use the `gitlab-mr` skill for commit + MR workflow (enforces EPMCDME-xxx ticket format)
- Use the `security-lead` skill for CVE remediation workflow
- `poetry run <tool>` resolves the in-project `.venv` on its own; activate only for bare tool binaries
- Run quality gates one at a time, not as one chained string: see `.ai-run/guides/quality-gates.md`
- Some commands here look like gates and are not — check that guide's traps table before reading an exit code
