---
updated: 2026-03-30
---

# Git Hooks for SKUEL

**Purpose:** Automated library-change detection after merges.

---

## Installed Hooks

| Hook | Trigger | Script | Blocks? |
|------|---------|--------|---------|
| `post-merge` | After `git pull` / merge | `scripts/hooks/post-merge` | No |

The hook does not block operations. It surfaces information you'd otherwise miss.

**Note:** Post-commit documentation checking was previously handled by a git `post-commit` hook (`scripts/hooks/post-commit` + `scripts/docs_contextual_check_v2.py`). This was replaced (2026-03-30) by the Claude Code PostToolUse hook at `.claude/hooks/post-commit-docs.sh`. See `/docs/tools/AUTOMATIC_DOCS_CHECK.md`.

---

## Post-Merge Hook: Library Change Detection

**Script:** `scripts/hooks/post-merge`

Runs after `git pull` or merge. Detects when `uv.lock` changed and reports
which library versions changed and which skills may be affected.

```
⚠️  Library versions changed. Consider reviewing:

📦 python-fasthtml: 0.12.21 → 0.12.39
   Skills potentially affected:
   - @fasthtml (primary)
```

---

## Manual Validation

Run at any time, especially after major changes:

```bash
# Full report (broken links + missing reverse links + stale skills)
uv run python scripts/validate_cross_references.py

# Verbose (includes orphaned docs)
uv run python scripts/validate_cross_references.py --verbose

# Errors only (zero exit if clean)
uv run python scripts/validate_cross_references.py --errors-only
```

### What the Validator Checks

**Broken links** (❌ Error — must fix):
- Skill referenced in a doc doesn't exist in `skills_metadata.yaml`
- Doc referenced in `skills_metadata.yaml` doesn't exist on disk

**Missing reverse links** (⚠️ Warning):
- Doc references `@skill` but skill doesn't list that doc in its metadata
- Skill lists a doc but doc doesn't reference `@skill`

**Stale skills** (🔵 Info):
- A skill's `primary_docs` have git commits after the skill's `last_reviewed` date
- Indicates the skill content may be out of sync with its documentation

```
🔵 STALE SKILLS — primary docs updated since last review (1):

  @domain-route-config
    Primary docs updated since last review (2026-03-01):
    DOMAIN_ROUTE_CONFIG_PATTERN.md (modified 2026-03-15)
    💡 Review @domain-route-config SKILL.md, then update last_reviewed in skills_metadata.yaml
```

**Skill counts are derived dynamically** — `VALID_SKILLS` is no longer hardcoded.
Adding a skill to `skills_metadata.yaml` is all that's needed for it to be recognised.

---

## Updating `last_reviewed`

When you update a skill after a staleness warning:

1. Review the skill's `SKILL.md` against its updated primary docs
2. Make any needed changes to the skill content
3. Update `last_reviewed` in `.claude/skills/skills_metadata.yaml`:

```yaml
- name: domain-route-config
  last_reviewed: "2026-03-15"   # ← bump to today
  ...
```

---

## Related Files

| File | Purpose |
|------|---------|
| `scripts/hooks/post-merge` | Post-merge hook (library change detection) |
| `.claude/hooks/post-commit-docs.sh` | Claude Code PostToolUse hook (post-commit doc checking) |
| `scripts/validate_cross_references.py` | Full cross-reference + staleness validator |
| `.claude/skills/skills_metadata.yaml` | Skill registry (source of truth for valid skills) |

---

## Troubleshooting

**Hook not running** — check permissions:
```bash
ls -la .git/hooks/post-merge   # should show -rwxr-xr-x
chmod +x .git/hooks/post-merge
```

**Stale skills showing unexpectedly** — check git dates vs `last_reviewed`:
```bash
git log -1 --format="%Y-%m-%d" -- docs/patterns/YOUR_DOC.md
```
