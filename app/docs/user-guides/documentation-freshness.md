---
title: Documentation Freshness Guide
updated: 2026-09-10
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
    (Git post-commit hook removed — doc detection
     merged into Claude Code hook above)

Any time
    │
    └─ ./dev health          → the automated drift checks
         (roster: ./dev health --list; one at a time: ./dev help)
```

---

## System 1: Claude Code Post-Commit Hook

**File:** `.claude/hooks/post-commit-docs.sh`
**Trigger:** Fires after any Bash command invoking `git commit` (compound chains included)
**Cost:** ~0ms for non-commits, ~80ms for commits

After a commit, the hook:
1. Collects changed code files (`.py`/`.js`/`.css`/`.sh`/`.toml`/`.yaml`, deletions included)
2. Finds docs/skills that reference those filenames (via `grep`)
3. Cross-references `skills_metadata.yaml` to identify affected skills
4. Returns `hookSpecificOutput.additionalContext` + a `systemMessage` summary so Claude can semantically evaluate staleness

### What You See

```
POST-COMMIT DOCS CHECK: A commit just landed...

Changed code files (3):
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

**Location:** the `HEALTH_CHECKS` array in `app/dev` — one roster, read by the
`health` block, the `health-<name>` targets, `./dev help` and the weekly janitor
**Trigger:** Manual — run anytime, especially after refactors

```bash
./dev health              # every check in the roster
./dev health --list       # print the roster (name:script)
./dev health-<name>       # one check; `./dev help` lists the targets
```

Each check exits non-zero when issues are found (CI-compatible). Everything in the
roster also runs weekly via `.github/workflows/weekly-janitor.yml`, which reads
the roster from `./dev health --list`; `health-mypy` sits outside it (~80s) and
has its own weekly workflow.

**The roster and the per-check detail live in
[../tools/HEALTH_CHECKS.md](../tools/HEALTH_CHECKS.md)** — what each check finds,
its sample output, its scope and its known limitations. This guide deliberately
does not repeat them: the two enumerations that stood here (a command block and
the Quick Reference table below) had both gone three checks stale, listing five
of eight, which is what a second copy of a membership fact does.

Two per-check notes that belong to *this* guide's workflow rather than to the
checks themselves:

- **`health-names` is only as good as its tables.** Update `scripts/health/stale_names.py`
  whenever you rename or delete a significant class, method, enum or module;
  `./dev health-names --list` shows the current rules.
- **`health-xref` reads frontmatter, not prose.** A doc declares its skill links in
  `related_skills:` — an `@skill` mention in the body is invisible to the validator.
  Fixing a stale skill means reviewing its `SKILL.md` against its updated
  `primary_docs`, then bumping `last_reviewed` in
  `.claude/skills/skills_metadata.yaml`.

---

## System 3: Git Hooks

### Post-Merge: Library Change Detection

**Script:** `scripts/git-hooks/post-merge`

After `git pull` or merge, detects when `uv.lock` changed and reports affected skills.

```
📦 python-fasthtml: 0.12.21 → 0.12.39
   Skills potentially affected:
   - @fasthtml (primary)
```

---

## Recommended Workflow

### After Every Commit (Automatic)

The Claude Code PostToolUse hook fires automatically after commits. Claude evaluates staleness and acts if needed. No action required.

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
| `./dev health` | Run every health check except `health-mypy` |
| `./dev health --list` | Print the roster — the names the `health-<name>` targets take |
| `./dev help` | The individual `health-<name>` targets, one line each |
| `./dev docs-check` | Run post-commit docs hook manually |

**Configuration files:**

| File | Purpose |
|------|---------|
| `.claude/hooks/post-commit-docs.sh` | Claude Code post-commit hook |
| `.claude/skills/skills_metadata.yaml` | Skill registry (source of truth) |
| `scripts/health/stale_names.py` | Renamed/deleted identifier rules |
| `scripts/git-hooks/post-merge` | Git post-merge hook |

---

## Reference Documentation

For implementation details and architecture, see the underlying reference docs:
- `/docs/tools/HEALTH_CHECKS.md` — health check script internals
- `/docs/tools/AUTOMATIC_DOCS_CHECK.md` — LLM-assisted doc checking
- `/docs/development/GIT_HOOKS.md` — git hook implementation
- `/docs/CROSS_REFERENCE_INDEX.md` — auto-generated skill↔doc mapping
- `@docs-skills-evolution` — complete documentation evolution framework
