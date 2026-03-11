---
title: Documentation Freshness Guide
updated: 2026-03-04
status: current
category: user-guides
tags: [documentation, freshness, health-checks, hooks, cross-references, staleness]
related: [HEALTH_CHECKS.md, AUTOMATIC_DOCS_CHECK.md, GIT_HOOKS.md]
---

# Documentation Freshness Guide

SKUEL has three documentation freshness systems that work together. Each fills a different gap — automatic detection after commits, proactive health checks, and structural cross-reference validation.

```
Commit lands
    │
    ├─ Claude Code hook (post-commit-docs.sh)
    │    → finds docs referencing changed files
    │    → identifies affected skills
    │    → Claude evaluates semantic staleness
    │
    └─ Git hook (post-commit)
         → detects new .md files
         → prompts INDEX.md / CLAUDE.md update

Any time
    │
    ├─ ./dev health          → 4 automated checks
    ├─ ./dev health-xref     → cross-reference + staleness
    └─ ./dev docs-check      → LLM-assisted doc review
```

---

## System 1: Claude Code Post-Commit Hook

**File:** `.claude/hooks/post-commit-docs.sh`
**Trigger:** Fires after any `git commit` via Bash tool use
**Cost:** ~0ms for non-commits, ~80ms for commits

After a commit, the hook:
1. Collects changed `.py` files
2. Finds docs/skills that reference those filenames (via `grep`)
3. Cross-references `skills_metadata.yaml` to identify affected skills
4. Returns a system message so Claude can semantically evaluate staleness

### What You See

```
POST-COMMIT DOCS CHECK: A commit just landed...

Changed Python files (3):
  - core/services/tasks_service.py
  - core/services/tasks/tasks_core_service.py
  - adapters/inbound/tasks_routes.py

Docs that reference changed files (2):
  - docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md
  - .claude/skills/python/SKILL.md

Skills that may need review (1):
  - @python (skill file directly references changed files)

ACTION: ...determine if any of the flagged docs are actually stale...
```

Claude then reads the flagged docs, compares them against what actually changed, and either updates stale content or confirms nothing needs changing.

### Skill Detection Logic

A skill is flagged when either:
- One of its `primary_docs` (from `skills_metadata.yaml`) appears in the referencing docs list
- A file inside `.claude/skills/{name}/` appears in the referencing docs list

### When It's Silent

- No `.py` files in the commit
- No docs reference the changed filenames
- The commit failed (`nothing to commit`)

---

## System 2: Health Checks (`./dev health`)

**Location:** `scripts/health/` + `scripts/validate_cross_references.py`
**Trigger:** Manual — run anytime, especially after refactors

Four checks that catch different kinds of drift:

```bash
./dev health              # all four checks
./dev health-modules      # dead Python modules only
./dev health-links        # broken doc links only
./dev health-names        # stale identifiers in docs only
./dev health-xref         # cross-reference + staleness only
```

All four exit non-zero when issues are found (CI-compatible).

### Check 1: Dead Modules (`health-modules`)

Finds Python files with zero importers — orphaned after refactors.

```
Dead Modules — 23 files with zero importers:
  ● (example removed — skuel_query_templates.py deleted March 2026)
```

**When to run:** After monolith dissolution, service splits, major refactors.
**False positives:** Low. Review flagged files before deleting — some may be dynamically loaded.

### Check 2: Dead Doc Links (`health-links`)

Finds broken links in `.md` files (markdown links, backtick paths, bare absolute paths).

```
  docs/patterns/three_tier_type_system.md
    L 500  [backtick]  /core/models/task/task_converters.py
```

**When to run:** After file renames or deletes.

### Check 3: Stale Names (`health-names`)

Finds renamed or deleted identifiers in documentation code blocks.

```
  CLAUDE.md
    L  47  KuTaskCreateRequest → TaskCreateRequest
    L 945  [DELETED] ProfileLayout
```

Only scans code blocks (fenced ` ``` ` and inline backticks), not prose. Prose mentions like "we renamed X to Y" are legitimate.

**Maintenance:** Update `scripts/health/stale_names.py` whenever you rename or delete a significant class, method, enum, or module. Run `./dev health-names --list` to see all rules.

### Check 4: Cross-References (`health-xref`)

Validates bidirectional consistency between skills and documentation, and detects stale skills.

```
✅ Bidirectional Links: 80/111 (72.1%)
❌ Broken Links: 1
⚠️  Missing Reverse Links: 51
🔵 Stale Skills: 0
```

**What it checks:**

| Check | Severity | Meaning |
|-------|----------|---------|
| Broken skill reference | Error | `@skill-name` in a doc doesn't exist in `skills_metadata.yaml` |
| Broken doc link | Error | Doc referenced in `skills_metadata.yaml` doesn't exist on disk |
| Missing reverse link | Warning | Doc references `@skill` but skill doesn't list that doc (or vice versa) |
| Stale skill | Info | A skill's `primary_docs` have git commits after its `last_reviewed` date |

**Fixing stale skills:**
1. Review the skill's `SKILL.md` against its updated primary docs
2. Make any needed changes to the skill content
3. Bump `last_reviewed` in `.claude/skills/skills_metadata.yaml`

**More detail:** `uv run python scripts/validate_cross_references.py --verbose`

---

## System 3: Git Hooks

Two git hooks fire on different events. Neither blocks operations.

### Post-Commit: New Documentation Detection

**Script:** `scripts/hooks/post-commit` → `scripts/docs_contextual_check_v2.py`

Detects newly added `.md` files and prompts for INDEX updates. Separate from the Claude Code hook (System 1) — this is a standard git hook.

| Trigger | Action |
|---------|--------|
| New `.md` in `docs/` | Prompt to update `docs/INDEX.md` |
| New `.md` in `.claude/skills/` | Prompt to update `CLAUDE.md` |

### Post-Merge: Library Change Detection

**Script:** `scripts/hooks/post-merge`

After `git pull` or merge, detects when `uv.lock` changed and reports affected skills.

```
📦 python-fasthtml: 0.12.21 → 0.12.39
   Skills potentially affected:
   - @fasthtml (primary)
```

### Disable / Re-enable

```bash
git config skuel.docs-check false   # disable post-commit hook
git config skuel.docs-check true    # re-enable
```

---

## Recommended Workflow

### After Every Commit (Automatic)

Both hooks fire automatically. Claude evaluates staleness from the Claude Code hook and acts if needed. The git post-commit hook surfaces new `.md` files. No action required.

### After Refactors (Manual)

```bash
./dev health                # catch all drift
./dev health-names --list   # review rename/delete rules — add new ones if you renamed something
```

### Monthly Maintenance

```bash
./dev health                # full sweep
uv run python scripts/docs_freshness.py --stale   # mtime-based staleness
```

### After Renaming or Deleting

1. Update `scripts/health/stale_names.py` with the old → new mapping
2. Run `./dev health-names` to find remaining references
3. Fix flagged docs
4. Run `./dev health-links` to catch broken paths

---

## Quick Reference

| Command | What It Does |
|---------|-------------|
| `./dev health` | Run all 4 health checks |
| `./dev health-modules` | Find orphaned Python files |
| `./dev health-links` | Find broken doc links |
| `./dev health-names` | Find stale identifiers in doc code blocks |
| `./dev health-xref` | Validate skill↔doc cross-references |
| `./dev docs-check` | LLM-assisted doc review |
| `./dev docs-check-fast` | Text-search doc review (no LLM) |

**Configuration files:**

| File | Purpose |
|------|---------|
| `.claude/hooks/post-commit-docs.sh` | Claude Code post-commit hook |
| `.claude/skills/skills_metadata.yaml` | Skill registry (source of truth) |
| `scripts/health/stale_names.py` | Renamed/deleted identifier rules |
| `scripts/hooks/post-commit` | Git post-commit hook |
| `scripts/hooks/post-merge` | Git post-merge hook |

---

## Reference Documentation

For implementation details and architecture, see the underlying reference docs:
- `/docs/tools/HEALTH_CHECKS.md` — health check script internals
- `/docs/tools/AUTOMATIC_DOCS_CHECK.md` — LLM-assisted doc checking
- `/docs/development/GIT_HOOKS.md` — git hook implementation
- `/docs/CROSS_REFERENCE_INDEX.md` — auto-generated skill↔doc mapping
- `@docs-skills-evolution` — complete documentation evolution framework
