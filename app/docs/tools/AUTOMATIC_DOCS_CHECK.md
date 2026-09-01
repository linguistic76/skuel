---
updated: 2026-07-09
---

# Automatic Documentation Check
**Status:** Active (Claude Code PostToolUse hook)
**Date Added:** 2026-01-30
**Replaced:** 2026-03-30 (migrated from `scripts/docs_contextual_check.py` + git post-commit hook to Claude Code hook)

## Overview

SKUEL automatically checks if documentation needs updating after every git commit. A Claude Code PostToolUse hook (`.claude/hooks/post-commit-docs.sh`) fires after any Bash command that invokes `git commit`, analyzes changed files, finds referencing docs and skills, and injects context so Claude can evaluate staleness.

## How It Works

### Trigger: Claude Code PostToolUse Hook

Every time you commit code via Claude Code's Bash tool, the hook automatically:
1. Collects changed code files (`.py`/`.js`/`.css`/`.sh`/`.toml`/`.yaml`, deletions included) from the commit
2. Finds docs/skills that reference those filenames (via `grep`)
3. Cross-references `skills_metadata.yaml` to identify affected skills
4. Returns `hookSpecificOutput.additionalContext` (full detail, injected into Claude's context) plus a `systemMessage` summary (visible to the user)

**Trigger mechanics (fixed 2026-06-10, hardened twice same day):** the
PostToolUse matcher fires on every Bash call; the script filters for a
`git commit` invocation at a command-segment boundary, so compound chains
like `git add ... && git commit ...` are covered (the original prefix-only
check missed them, which kept the hook silent for most real commits).

The primary guard is **commit-identity dedupe**: the last-checked HEAD sha
persists in `.git/skuel-docs-check-last` (per-worktree, survives sessions),
and each commit sha is checked AT MOST ONCE — a command that merely
*mentions* "git commit" (e.g. a grep pattern) re-matches the regex but finds
the sha already checked and stays silent. A no-findings analysis still
records the sha (a completed check is a completed check).

Recency is a SANITY bound, not the evidence: with the stats marker
(`N files changed`) confirming a commit in the tool output, the standard
window applies (`SKUEL_DOCS_CHECK_MAX_AGE_S`, default 300s); when the marker
is hidden — piped output (`git commit ... | tail -5`) or
`git commit --quiet`, which silently skipped a 58-file commit before the
hardening — a generous fallback window applies
(`SKUEL_DOCS_CHECK_FALLBACK_AGE_S`, default 1800s). The dedupe is what makes
1800s safe: it closes the long-chain blind spot
(`git commit | tail && gh pr checks --watch` outlived the previous 60s
window) without re-introducing duplicate advisories. The residual false
positive — a "git commit"-mentioning non-commit command firing on a
never-checked HEAD younger than the window — costs one advisory for a real
recent commit, at most once per sha.

The original output also placed `additionalContext` at the JSON top level,
where PostToolUse ignores it — it must be nested under
`hookSpecificOutput`.

Note: merges via `gh pr merge` never trigger the hook (no local `git commit`;
the squash commit is created server-side). That is by design — branch content
is checked at local commit time.

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

### Staleness Decision Policy — Present-Tense Docs vs Pinned Snapshots

When the hook flags a doc, classify it before deciding whether "references a
changed file" means "stale" (established on PR #577/#578, 2026-07-09):

- **Present-tense docs get currency fixes.** Architecture, patterns, guides,
  reference — and **roadmaps with open phases**: as long as any phase is
  unfinished, a roadmap is read for current understanding, so a claim that now
  reads as a wrong *present* fact must be corrected. Where such a doc narrates
  history, keep the history accurate and add the present state (e.g. "X/Y *at
  convergence time*; the set is registry-sourced, Z joined later via arc #N")
  rather than rewriting what happened.
- **Pinned snapshots stay as written.** Docs that declare their own
  point-in-time scope — reviews pinned to a reviewed commit
  (`docs/Reviews/*` with a `**Reviewed commit:**` header), dated outcome
  logs, ADR *Context* sections describing the world at decision time. Their
  line numbers, counts, and vocabulary are correct *relative to the pinned
  revision*; "updating" them makes the doc claim it reviewed code it didn't.

The test: does the doc **declare its own snapshot** (a reviewed commit, a
date-scoped outcome)? → pinned, leave alone. Is it **read to understand the
system today** (any doc with open or forward-looking content)? → present-tense,
fix currency.

If pinned snapshots accumulating drift becomes a problem, the lever is a
lifecycle convention (archive or prune resolved reviews), not in-place edits.

### What It Can Detect

- Cross-references: docs that mention changed code files
- Skill staleness: skills whose primary docs or skill files reference changed code
- Statistical updates: Claude semantically evaluates whether counts/metrics are stale

### What It Can't Detect

- Conceptual changes: major architecture shifts requiring manual review
- New features: entirely new functionality not yet documented
- Docs that describe a changed file without naming it (prose-only references)

### When It's Silent

- No code files (`.py`/`.js`/`.css`/`.sh`/`.toml`/`.yaml`) in the commit
- No docs reference the changed filenames
- The commit failed (`nothing to commit`)
- HEAD sha already checked (`.git/skuel-docs-check-last` — each commit is checked at most once)
- HEAD is older than the recency window — 300s with the stats marker, 1800s without (sanity bound against false regex matches)
- Running outside Claude Code (standard git commits bypass the hook)

---

## Architecture

### File Locations

| File | Purpose |
|------|---------|
| `.claude/hooks/post-commit-docs.sh` | Claude Code PostToolUse hook — fires after any Bash command invoking `git commit` |
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
    |-- 1. Collect changed code files
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
