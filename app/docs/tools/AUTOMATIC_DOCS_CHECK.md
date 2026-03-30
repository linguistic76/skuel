# Automatic Documentation Check
**Status:** Active (Claude Code PostToolUse hook)
**Date Added:** 2026-01-30
**Replaced:** 2026-03-30 (migrated from `scripts/docs_contextual_check.py` + git post-commit hook to Claude Code hook)

## Overview

SKUEL automatically checks if documentation needs updating after every git commit. A Claude Code PostToolUse hook (`.claude/hooks/post-commit-docs.sh`) fires after `git commit` bash commands, analyzes changed files, finds referencing docs and skills, and injects context so Claude can evaluate staleness.

## How It Works

### Trigger: Claude Code PostToolUse Hook

Every time you commit code via Claude Code's Bash tool, the hook automatically:
1. Collects changed `.py` files from the commit
2. Finds docs/skills that reference those filenames (via `grep`)
3. Cross-references `skills_metadata.yaml` to identify affected skills
4. Returns a system message so Claude can semantically evaluate staleness

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

### What It Can Detect

- Cross-references: docs that mention changed code files
- Skill staleness: skills whose primary docs or skill files reference changed code
- Statistical updates: Claude semantically evaluates whether counts/metrics are stale

### What It Can't Detect

- Conceptual changes: major architecture shifts requiring manual review
- New features: entirely new functionality not yet documented
- Deleted code: when you remove something, docs may need pruning

### When It's Silent

- No `.py` files in the commit
- No docs reference the changed filenames
- The commit failed (`nothing to commit`)
- Running outside Claude Code (standard git commits bypass the hook)

---

## Architecture

### File Locations

| File | Purpose |
|------|---------|
| `.claude/hooks/post-commit-docs.sh` | Claude Code PostToolUse hook — fires after `git commit` |
| `.claude/skills/skills_metadata.yaml` | Skill registry (source of truth for skill metadata) |
| `scripts/docs_freshness.py` | Traditional mtime-based staleness checker |
| `scripts/docs_update.py` | LLM-assisted doc updater |

### Detection Flow

```
Git Commit (via Claude Code Bash tool)
    |
PostToolUse hook fires
    |
post-commit-docs.sh
    |-- 1. Collect changed .py files
    |-- 2. Grep docs/skills for references to those files
    |-- 3. Cross-reference skills_metadata.yaml
    |
System message injected into Claude context
    |
Claude evaluates semantic staleness
    |-- Updates stale docs
    |-- Or confirms nothing needs changing
```

---

## Comparison with docs_freshness.py

| Feature | Claude Code hook | docs_freshness.py |
|---------|-----------------|-------------------|
| **Trigger** | After git commits (Claude Code) | Manual/scheduled |
| **Detection** | Git-aware + semantic eval | Mtime + file refs |
| **Speed** | ~80ms | Instant |
| **Cost** | $0 (uses active Claude session) | Free |
| **Accuracy** | ~80% coverage | ~20% coverage |
| **Use Case** | Real-time after changes | Scheduled audits |

**Recommendation:** Use both!
- Claude Code hook: after commits (real-time, semantic)
- `docs_freshness.py`: weekly/monthly audits (scheduled, mtime-based)

---

## Historical Note

Prior to 2026-03-30, documentation checking used two scripts:
- `scripts/docs_contextual_check.py` (v1) / `scripts/docs_contextual_check_v2.py` — standalone Python scripts that ran LLM analysis
- `scripts/hooks/post-commit` — a git hook that called the v2 script

These were replaced by the Claude Code PostToolUse hook, which is simpler (a shell script that injects context into the active Claude session) and costs $0 in additional API calls.

---

## Related Documentation

- `/docs/user-guides/documentation-freshness.md` - Complete freshness guide
- `/docs/development/GIT_HOOKS.md` - Git hooks overview
- `/scripts/docs_freshness.py` - Traditional mtime-based checker
- `/scripts/docs_update.py` - LLM-assisted doc updater
