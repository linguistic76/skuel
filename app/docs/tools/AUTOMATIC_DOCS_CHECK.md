# Automatic Documentation Check
**Status:** ✅ Active (post-commit hook)
**Date Added:** 2026-01-30

## Overview

SKUEL now automatically checks if documentation needs updating after every git commit. The system uses a hybrid approach combining pattern detection, text search, and LLM analysis to find docs that may be stale.

## How It Works

### Trigger: Git Post-Commit Hook

Every time you commit code, the `.git/hooks/post-commit` hook automatically runs `docs_contextual_check.py` to analyze your changes.

```bash
# Your normal workflow
git add core/services/ls/ls_core_service.py
git commit -m "Add DomainConfig to LsCoreService"

# Hook runs automatically after commit
# Output (only if docs need updating):
📄 Documentation Update Suggestions

🔴 HIGH CONFIDENCE (1)
  📄 docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md
     Tracks DomainConfig migration progress, currently shows 33/34

Update docs with:
  poetry run python scripts/docs_update.py --doc docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md

To disable this check: git config skuel.docs-check false
```

### Three Detection Methods

| Method | Speed | Accuracy | Purpose |
|--------|-------|----------|---------|
| **Pattern Detection** | Instant | High (for known patterns) | Fast checks for common patterns (DomainConfig, BaseService, etc.) |
| **Text Search** | <1s | Medium | Find docs mentioning changed files/terms (uses ripgrep) |
| **LLM Analysis** | 2-5s | High | Semantic understanding of what changed and what docs need updating |

### What It Can Detect

✅ **Statistical updates** - Service counts, percentages, scores
✅ **Migration progress** - Phase completion, progress tracking
✅ **Pattern adoption** - When you adopt a pattern across multiple files
✅ **Cross-references** - Docs that mention changed code
✅ **Architectural summaries** - High-level docs that summarize patterns
✅ **File references** - Traditional mtime-based staleness (via docs_freshness.py)

### What It Can't Detect

❌ **Conceptual changes** - Major architecture shifts requiring manual review
❌ **New features** - Entirely new functionality not yet documented
❌ **Deleted code** - When you remove something, docs may need pruning

---

## Usage

### Automatic (Default)

The hook runs automatically after every commit. **No action needed.**

### Manual Check

Run the check manually anytime:

```bash
# Full check (with LLM analysis)
./dev docs-check

# Fast check (text search only, no API calls)
./dev docs-check-fast

# Check specific commit range
poetry run python scripts/docs_contextual_check.py --since HEAD~3
```

### Disable the Hook

If you find it annoying or want to commit without checks:

```bash
# Disable permanently
git config skuel.docs-check false

# Re-enable later
git config skuel.docs-check true

# Or skip for one commit
git commit -n -m "message"  # -n skips all hooks
```

---

## Configuration

### Git Config Options

```bash
# Disable docs check
git config skuel.docs-check false

# Re-enable docs check
git config skuel.docs-check true

# Check current status
git config --get skuel.docs-check
```

### Environment Variables

```bash
# Required for LLM analysis (optional - fallback to text search if missing)
export ANTHROPIC_API_KEY="your-key-here"
```

**Note:** If `ANTHROPIC_API_KEY` is not set, the tool still works but only uses pattern detection and text search (fast mode).

---

## Examples

### Example 1: DomainConfig Migration

```bash
$ git commit -m "Add DomainConfig to 3 services"
[main abc1234] Add DomainConfig to 3 services
 3 files changed, 45 insertions(+), 12 deletions(-)

📄 Documentation Update Suggestions

🔴 HIGH CONFIDENCE (1)
  📄 docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md
     Tracks migration progress - 3 new services migrated

Update docs with:
  poetry run python scripts/docs_update.py --doc docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md
```

### Example 2: BaseService Changes

```bash
$ git commit -m "Add new mixin to BaseService"
[main def5678] Add new mixin to BaseService
 2 files changed, 67 insertions(+), 8 deletions(-)

📄 Documentation Update Suggestions

🔴 HIGH CONFIDENCE (2)
  📄 docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md
     Documents BaseService mixins and patterns
  📄 docs/guides/BASESERVICE_QUICK_START.md
     Quick start guide references BaseService structure

Update docs with:
  poetry run python scripts/docs_update.py --doc docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md
  poetry run python scripts/docs_update.py --doc docs/guides/BASESERVICE_QUICK_START.md
```

### Example 3: No Updates Needed

```bash
$ git commit -m "Fix typo in comment"
[main ghi9012] Fix typo in comment
 1 file changed, 1 insertion(+), 1 deletion(-)

# No output - hook runs silently when no docs need updating
```

---

## Architecture

### File Locations

| File | Purpose |
|------|---------|
| `app/scripts/docs_contextual_check.py` | Main script - detection logic |
| `.git/hooks/post-commit` | Git hook - runs after commits (at repo root) |
| `app/scripts/docs_update.py` | LLM-assisted doc updater |
| `app/scripts/docs_freshness.py` | Traditional mtime-based staleness |

**Note:** The git repository is at `/home/mike/skuel/` but application code is in the `app/` subdirectory. The hook is at repo root (`.git/hooks/post-commit`) and references scripts with the `app/` prefix.

### Detection Flow

```
Git Commit
    ↓
post-commit hook
    ↓
docs_contextual_check.py
    ├─→ 1. Pattern Detection (instant)
    ├─→ 2. Text Search (ripgrep, <1s)
    └─→ 3. LLM Analysis (Claude, 2-5s)
    ↓
Merge & Deduplicate
    ↓
Print Suggestions
    ↓
Developer Reviews & Updates
```

### Confidence Levels

**HIGH** 🔴
- LLM analysis with high confidence
- Multiple detection methods agree
- Known patterns matched

**MEDIUM** 🟡
- LLM analysis with medium confidence
- Pattern detection matched
- Single detection method

**LOW** ⚪ (only shown in verbose mode)
- Text search only
- Weak pattern match
- Speculative suggestion

---

## Cost Analysis

### API Usage

**Per commit check:**
- Input tokens: ~1,500-3,000 (changed files)
- Output tokens: ~200-500 (suggestions)
- Cost: ~$0.01-0.03 per check

**Monthly estimate:**
- 20 commits/week × 4 weeks = 80 commits/month
- 80 commits × $0.02 avg = **$1.60/month**

**Annual estimate:** ~$20/year

### ROI

**Without tool:**
- 30 min/update × 3 updates/week = 1.5 hours/week
- 1.5 hours × 50 weeks = 75 hours/year
- Value at $100/hour = $7,500/year

**With tool:**
- 5 min/update × 3 updates/week = 15 min/week
- 0.25 hours × 50 weeks = 12.5 hours/year
- Value at $100/hour = $1,250/year

**Savings:** 62.5 hours/year = $6,250/year
**Cost:** $20/year in API calls
**Net benefit:** **$6,230/year**

---

## Troubleshooting

### Hook Not Running

**Symptom:** No output after commits, even when code changes

**Check 1: Verify hook exists and is executable**
```bash
# From project root
ls -la .git/hooks/post-commit
# Should show: -rwxrwxr-x (executable)

# If not executable, fix it
chmod +x .git/hooks/post-commit
```

**Check 2: Verify hook is in correct location**
```bash
# Git repo root (where .git directory lives)
git rev-parse --show-toplevel  # Should show /home/mike/skuel

# Hook MUST be in repository .git/hooks/, not app/.git/hooks/
ls -la $(git rev-parse --show-toplevel)/.git/hooks/post-commit
```

**Check 3: Test hook manually**
```bash
# Run hook directly to see if it works
.git/hooks/post-commit
# Should show documentation suggestions or run silently
```

**Check 4: Verify docs-check is enabled**
```bash
# Check if docs-check is disabled
git config --get skuel.docs-check

# Re-enable if needed
git config skuel.docs-check true
```

**Common Issue: Wrong Hook Location**

SKUEL uses a nested repository structure:
- Git repo root: `/home/mike/skuel/` (contains `.git/`)
- Application code: `/home/mike/skuel/app/` (contains scripts/)
- Hook location: `/home/mike/skuel/.git/hooks/post-commit` ✅
- Script location: `/home/mike/skuel/app/scripts/docs_contextual_check.py` ✅

The hook must be in the repository's `.git/hooks/` directory (at git root), NOT in `app/.git/hooks/`. The hook script accounts for the `app/` subdirectory when locating the Python script.

### No LLM Analysis

If you see only pattern/text suggestions:

```bash
# Check if ANTHROPIC_API_KEY is set
echo $ANTHROPIC_API_KEY

# If empty, set it
export ANTHROPIC_API_KEY="your-key-here"

# Or add to your shell profile (~/.bashrc, ~/.zshrc)
echo 'export ANTHROPIC_API_KEY="your-key-here"' >> ~/.bashrc
```

### False Positives

If you get suggestions for docs that don't need updating:

1. Review the confidence level (focus on HIGH/MEDIUM)
2. Run `./dev docs-check-fast` to see text search matches
3. Report patterns to improve detection logic

### False Negatives

If docs need updating but weren't detected:

1. Check if the doc uses standard reference patterns
2. Run `./dev docs-check --since HEAD~5` to check more commits
3. Manually run: `poetry run python scripts/docs_update.py --all`

---

## Comparison with docs_freshness.py

| Feature | docs_contextual_check.py | docs_freshness.py |
|---------|-------------------------|-------------------|
| **Trigger** | After git commits | Manual/scheduled |
| **Detection** | Git-aware + LLM + text | Mtime + file refs |
| **Speed** | 2-5 seconds | Instant |
| **Cost** | ~$0.02 per run | Free |
| **Accuracy** | ~80% coverage | ~20% coverage |
| **Use Case** | Real-time after changes | Scheduled audits |

**Recommendation:** Use both!
- `docs_contextual_check.py` - After commits (real-time)
- `docs_freshness.py` - Weekly/monthly audits (scheduled)

---

## Future Enhancements

### Planned (Priority Order)

1. **Smart batching** - Batch API calls across multiple commits
2. **Learning mode** - Learn from false positives/negatives
3. **Auto-update mode** - Optional `--auto-update` flag for trusted patterns
4. **Pre-commit check** - Block commits if critical docs are stale
5. **CI integration** - Fail PR if docs haven't been updated

### Under Consideration

- **Doc templates** - Auto-generate doc sections for new patterns
- **Cross-repo** - Check docs in related repos
- **Slack notifications** - Post suggestions to team channel

---

## Related Documentation

- `/docs/investigations/DOCS_TOOLING_ANALYSIS.md` - Why we built this tool
- `/scripts/docs_freshness.py` - Traditional mtime-based checker
- `/scripts/docs_update.py` - LLM-assisted doc updater
- `/docs/patterns/DOCUMENTATION_MAINTENANCE.md` - Doc maintenance patterns

---

## Feedback

This tool is new (2026-01-30). Please provide feedback:

- **False positives** - Suggestions for docs that don't need updating
- **False negatives** - Missed docs that needed updating
- **Performance** - Too slow? Too noisy?
- **Feature requests** - What would make it better?

Open issues at: https://github.com/anthropics/claude-code/issues (or internal tracker)

---

## Quick Reference

```bash
# Automatic (runs after every commit)
# No action needed - just commit normally

# Manual check
./dev docs-check

# Fast check (no LLM)
./dev docs-check-fast

# Disable
git config skuel.docs-check false

# Re-enable
git config skuel.docs-check true

# Update suggested docs
poetry run python scripts/docs_update.py --doc <path>
poetry run python scripts/docs_update.py --all
```
