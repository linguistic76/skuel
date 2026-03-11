# GitHub Actions Workflows

This directory contains CI/CD workflows for SKUEL.

## Documentation Quality Checks (`docs.yml`)

**Purpose**: Automatically validate documentation quality on every push/PR.

**Triggers**:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`
- Manual dispatch (workflow_dispatch)

**Only runs when documentation-related files change**:
- `docs/**`
- `.claude/skills/**`
- `scripts/docs_*.py`
- `scripts/skills_validator.py`
- `.github/workflows/docs.yml`

### Jobs

#### 1. `validate_documentation`

Runs on every trigger. Performs 4 checks:

| Check | Script | Failure Level | Description |
|-------|--------|---------------|-------------|
| **Freshness** | `docs_freshness.py --critical-only` | ❌ Fails CI | Docs 30+ days out of sync with code |
| **Skills** | `skills_validator.py` | ❌ Fails CI | Missing skills files, broken metadata |
| **Broken Links** | `docs_freshness.py --json` | ⚠️ Warning only | >10 missing doc references |
| **Review Schedule** | `docs_review_scheduler.py` | ℹ️ Info only | Docs overdue for review |

**CI Failure Conditions**:
- Critical freshness issues (30+ days)
- Skills validation errors

**PR Comments**:
Automatically posts results to PRs with:
- ✅/❌ Status for each check
- ⚠️ Warnings for broken links
- Expandable details section

#### 2. `documentation_metrics`

Runs only on `main` branch merges. Generates metrics report.

**Metrics Collected**:
- Freshness status (total, stale, fresh, by tracking type)
- Skills status (total, checks passed, errors, warnings)
- Review schedule (total tracked, overdue, upcoming, current)

**Artifact**: `documentation-metrics` (retained for 90 days)

### Running Locally

Before pushing, run the same checks locally:

```bash
# Check critical freshness issues
uv run python scripts/docs_freshness.py --critical-only

# Validate skills
uv run python scripts/skills_validator.py

# Full freshness report
uv run python scripts/docs_freshness.py

# Review schedule
uv run python scripts/docs_review_scheduler.py
```

### Configuration

**Python Version**: 3.12
**Package Manager**: uv
**Caching**:
- uv venv cached based on `uv.lock` hash
- Pip cache enabled for faster setup-python

### Troubleshooting

**"No module named 'yaml'"**:
- uv dependencies not installed
- Check `pyproject.toml` includes `pyyaml`

**"docs directory not found"**:
- Scripts expect to run from project root
- Working directory should be `/home/mike/skuel/app`

**False positives in freshness**:
- Add `tracking: conceptual` to docs without code refs
- Add `last_reviewed` and `review_frequency` to frontmatter
- See `/docs/freshness_config.yaml` for configuration

**Skills validation failures**:
- Check required files: SKILL.md, QUICK_REFERENCE.md, PATTERNS.md
- Verify `skills_metadata.yaml` has no circular dependencies
- Ensure docs have `related_skills` backlinks

### Future Enhancements

Potential additions:
- [ ] Markdown linting (markdownlint)
- [ ] Spell checking (codespell)
- [ ] Link checking (external links)
- [ ] Documentation coverage metrics
- [ ] Auto-update of INDEX.md
- [ ] Automatic frontmatter validation

---

**Last Updated**: 2026-01-29
