# Git Hooks for SKUEL

**Purpose:** Automated documentation prompts and library-change detection after commits.

---

## Installed Hooks

| Hook | Trigger | Script | Blocks? |
|------|---------|--------|---------|
| `post-commit` | After every commit | `scripts/hooks/post-commit` | No |
| `post-merge` | After `git pull` / merge | `scripts/hooks/post-merge` | No |

Neither hook blocks commits. They surface information you'd otherwise miss.

---

## Post-Commit Hook: New Documentation Detection

**Script:** `scripts/hooks/post-commit` → `scripts/docs_contextual_check_v2.py`

Runs after every commit. Checks whether any newly added `.md` files need INDEX entries.

### What It Detects

| Trigger | Confidence | Action |
|---------|------------|--------|
| New `.md` in `docs/` | CRITICAL | Prompt to update `docs/INDEX.md` |
| New `.md` in `.claude/skills/` | HIGH | Prompt to update `CLAUDE.md` |

Only detects **new files** (added, not modified). Cross-reference analysis was removed
(it flagged every doc mentioning a changed filename — too many false positives).
Semantic doc-update awareness is handled by the Claude Code PostToolUse hook.

### Disable / Re-enable

```bash
git config skuel.docs-check false   # disable
git config skuel.docs-check true    # re-enable
```

---

## Post-Merge Hook: Library Change Detection

**Script:** `scripts/hooks/post-merge`

Runs after `git pull` or merge. Detects when `poetry.lock` changed and reports
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
poetry run python scripts/validate_cross_references.py

# Verbose (includes orphaned docs)
poetry run python scripts/validate_cross_references.py --verbose

# Errors only (zero exit if clean)
poetry run python scripts/validate_cross_references.py --errors-only
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
| `scripts/hooks/post-commit` | Post-commit hook (new file detection) |
| `scripts/hooks/post-merge` | Post-merge hook (library change detection) |
| `scripts/docs_contextual_check_v2.py` | New documentation file detector |
| `scripts/validate_cross_references.py` | Full cross-reference + staleness validator |
| `.claude/skills/skills_metadata.yaml` | Skill registry (source of truth for valid skills) |

---

## Troubleshooting

**Hook not running** — check permissions:
```bash
ls -la .git/hooks/post-commit   # should show -rwxr-xr-x
chmod +x .git/hooks/post-commit
```

**Too noisy** — disable the post-commit docs check:
```bash
git config skuel.docs-check false
```

**Stale skills showing unexpectedly** — check git dates vs `last_reviewed`:
```bash
git log -1 --format="%Y-%m-%d" -- docs/patterns/YOUR_DOC.md
```
