# Documentation Tooling Analysis
**Date:** 2026-01-30
**Context:** Investigation of docs_freshness.py limitations and recommendations for improvement

## Executive Summary

**Finding:** The current `docs_freshness.py` script is **fundamentally limited** to detecting mtime-based staleness of explicitly referenced code files. It **cannot detect** the types of documentation updates that occurred in this session (Phase 4 completion, statistical updates, cross-referential consistency).

**Recommendation:** **Hybrid approach** - Keep existing tool for its narrow use case, add complementary git-aware semantic tool for broader coverage.

---

## The Problem: What docs_freshness.py Can't Detect

### Test Case: Phase 4 DomainConfig Migration

**What happened:**
1. Code changes committed: 9 services migrated to DomainConfig
2. Documentation updated: 3 files needed updates to reflect completion
3. Script result: `uv run python scripts/docs_freshness.py --stale` → **"No stale documentation found!"**

**Why it failed:**

| Update Type | Example | Can Script Detect? |
|-------------|---------|-------------------|
| Statistical updates | "25 services" → "34 services" | ❌ No |
| New work completion | Added Phase 4 section | ❌ No |
| Cross-referential consistency | Doc A references info in Doc B | ❌ No |
| Architectural summaries | Architecture health 9.6→9.8 | ❌ No |
| Explicit file references with mtime | `**File:** core/services/base_service.py` changed | ✅ Yes |

---

## How docs_freshness.py Works

### Detection Mechanism

```python
# 1. Extract explicit code references via regex patterns
PATTERNS = [
    r"\*\*File:\*\*\s*`([^`]+)`",           # **File:** `/path/to/file.py`
    r"\*\*Directory:\*\*\s*`([^`]+)`",      # **Directory:** `/path/to/dir/`
    r"\*\*Package:\*\*\s*`([^`]+)`",        # **Package:** `/path/to/package/`
]

# 2. Compare modification times
if code_file_mtime > doc_file_mtime:
    flag_as_stale()
```

### Strengths ✅

1. **Fast:** No API calls, pure filesystem operations
2. **Precise:** When it detects staleness, it's accurate
3. **Zero-cost:** No LLM credits required
4. **Deterministic:** Same input = same output

### Limitations ❌

1. **Requires explicit patterns:** Docs must use `**File:**` format
2. **Mtime-based only:** Can't detect semantic changes
3. **No context awareness:** Doesn't understand what the doc is ABOUT
4. **No cross-references:** Can't track doc-to-doc dependencies
5. **No statistical tracking:** Can't detect outdated numbers/metrics
6. **Git-unaware:** Can't see what CHANGED in the code, only WHEN

---

## What Human + AI Can Do (But Script Can't)

### This Session's Updates

**Human approach:**
1. Semantic understanding: "We completed Phase 4 migration"
2. Context search: Find docs mentioning "DomainConfig", "migration", "25 services"
3. Logical consistency: If we migrated 9 MORE services, update the count
4. Cross-referential reasoning: Update all docs that reference this info
5. Architectural synthesis: Recalculate health scores based on completion

**Result:** 3 files updated correctly, full consistency achieved

**Script approach:**
1. Check mtime of files referenced with `**File:**` pattern
2. No matches found (these docs don't use that pattern)
3. Report: "No stale documentation"

**Result:** ❌ Missed all updates

---

## Comparison: docs_freshness.py vs docs_update.py

| Feature | docs_freshness.py | docs_update.py |
|---------|------------------|----------------|
| **Detection** | Mtime + explicit refs | Uses freshness.py output |
| **Analysis** | None | LLM-based (Claude API) |
| **Cost** | Free | ~$0.02-0.10 per doc |
| **Accuracy** | High for narrow case | High for broad cases |
| **Context awareness** | None | Full code + doc context |
| **Human approval** | N/A | Interactive or --yes |
| **Use case** | Detect stale refs | Generate updates |

**Key insight:** `docs_update.py` depends on `docs_freshness.py` for detection, so if freshness fails to detect, update never runs.

---

## Root Cause Analysis

### Why Mtime-Based Detection Fails

**Scenario: Phase 4 Migration**

```
Timeline:
├─ 2026-01-29: DOMAINCONFIG_MIGRATION_COMPLETE.md written (documents Phase 1-3)
├─ 2026-01-30: 9 new services migrated (Phase 4)
└─ 2026-01-30: Doc needs Phase 4 section added

Code files referenced in doc:
- core/services/base_service.py (mtime: 2026-01-29)
- core/services/domain_config.py (mtime: 2026-01-29)

Doc mtime: 2026-01-29

Result: Doc mtime == Code mtime → NOT STALE (wrong!)
```

**The issue:** The doc needs updating NOT because referenced code changed, but because:
1. **New work was completed** (9 new services migrated)
2. **Statistics changed** (25 → 34 services)
3. **Sections are missing** (no Phase 4 section yet)

None of these are detectable via mtime comparison.

---

## Proposed Solutions

### Option 1: Improve docs_freshness.py ⚠️ (Limited upside)

**Possible enhancements:**
```python
# 1. Git-aware tracking
def check_git_changes(file_path, since_date):
    """Check if file has commits since doc was last updated"""
    # Uses git log to see actual changes, not just mtime

# 2. Statistical tracking
def extract_metrics(doc_content):
    """Find numbers that might be service counts, scores, etc."""
    # Pattern: "25 services", "9.6/10", "100%"

# 3. Cross-reference detection
def find_referencing_docs(doc_path):
    """Find other docs that mention this doc's content"""
    # Full-text search across docs/
```

**Problems:**
- Still can't detect "new work completion" without explicit tracking
- Statistical tracking is brittle (every "25" isn't a service count)
- Cross-reference detection requires semantic understanding
- Git-aware tracking helps but doesn't solve the core issue

**Verdict:** ⚠️ **Marginal improvement, high complexity**

---

### Option 2: Event-Driven Doc Updates ✅ (Recommended)

**Approach:** Trigger doc checks when code changes, not on a schedule

#### Implementation Pattern A: Git Hook

```bash
# .git/hooks/post-commit
#!/bin/bash
# After every commit, check if docs need updating

uv run python scripts/docs_contextual_check.py \
    --changed-files "$(git diff-tree --no-commit-id --name-only -r HEAD)"
```

**Flow:**
1. Developer commits code changes
2. Hook runs `docs_contextual_check.py`
3. Script uses LLM to analyze changes + find related docs
4. Outputs: "Consider updating: docs/migrations/X.md, CLAUDE.md"
5. Developer can run update command or handle manually

#### Implementation Pattern B: Explicit Command

```bash
# Developer workflow
git commit -m "Complete Phase 4 migration"
./dev docs-check  # New command: check if docs need updating

# Output:
# "You modified 9 service files. Consider updating:
#  - docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md (add Phase 4)
#  - CLAUDE.md (update service count)
#  - docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md (update status)"
```

**Advantages:**
- ✅ Runs in context of actual changes (not stale mtime comparison)
- ✅ Developer is present and has context ("I just completed Phase 4")
- ✅ Can use git diff to see WHAT changed, not just WHEN
- ✅ Can prompt with specific suggestions based on change patterns
- ✅ Optional: auto-run via hook, or manual via command

**Disadvantages:**
- ❌ Requires API calls (costs ~$0.01-0.05 per check)
- ❌ Slower than mtime-based (2-5 seconds vs instant)
- ❌ Requires internet connection

---

### Option 3: Hybrid Approach ✅✅ (BEST)

**Combine both tools for comprehensive coverage:**

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **docs_freshness.py** | Mtime-based staleness | Daily/weekly cron, CI checks |
| **docs_contextual_check.py** (NEW) | Semantic staleness | After commits, before PRs |
| **docs_update.py** | Generate updates | When staleness detected |

#### New Tool: docs_contextual_check.py

```python
#!/usr/bin/env python3
"""
Contextual Documentation Checker

Uses git changes + LLM analysis to find docs that need updating based on
code changes, even without explicit file references.

Usage:
    # Check based on recent commits
    uv run python scripts/docs_contextual_check.py --since HEAD~3

    # Check specific files
    uv run python scripts/docs_contextual_check.py --files core/services/ls/*.py

    # Check after git commit (via hook)
    uv run python scripts/docs_contextual_check.py --changed-files "$(git diff-tree ...)"
"""

def analyze_changes(changed_files: list[str], docs_dir: Path) -> list[str]:
    """
    Use LLM to analyze code changes and find related docs.

    Prompt pattern:
    "These files changed: [list]
     Which docs in /docs might need updating based on these changes?
     Consider: migration docs, count/statistics, architecture summaries."
    """
    pass

def find_statistical_references(query: str, docs_dir: Path) -> list[Path]:
    """
    Find docs mentioning specific terms (e.g., "25 services", "DomainConfig").

    Uses ripgrep for fast text search.
    """
    pass
```

**Workflow:**

```bash
# 1. Developer completes work
git add core/services/ls/ls_core_service.py
git commit -m "Add DomainConfig to LsCoreService"

# 2. Git hook runs contextual check
uv run python scripts/docs_contextual_check.py --changed-files "core/services/ls/ls_core_service.py"

# 3. Output:
# "🔍 Checking for related documentation...
#
#  Found potential updates needed:
#  - docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md
#    Reason: Mentions DomainConfig migration progress (currently shows 33/34)
#  - CLAUDE.md (line 753)
#    Reason: References DomainConfig migration status
#
#  Run updates?
#  uv run python scripts/docs_update.py --doc docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md"

# 4. Developer reviews and runs update command
```

---

## Recommendation: Hybrid Approach Implementation

### Phase 1: Keep Existing Tool (1 day)
- ✅ `docs_freshness.py` - Works well for explicit file references
- ✅ `docs_update.py` - Works well for generating updates
- Status: **No changes needed**

### Phase 2: Add Contextual Checker (2-3 days)
- 🔨 Create `docs_contextual_check.py`
- Features:
  - Git-aware: analyze changed files via git diff
  - LLM-powered: use Claude to find related docs
  - Fast search: use ripgrep for statistical references
  - Interactive: suggest docs, don't auto-update

### Phase 3: Add Git Hook (Optional, 1 day)
- 🔨 Create `.git/hooks/post-commit`
- Runs contextual checker after commits
- Can be disabled via `git config skuel.docs-check false`

### Phase 4: Add Dev Command (1 day)
- 🔨 Add `./dev docs-check` command
- Wraps contextual checker with nice UI
- Shows suggestions, offers to run updates

---

## Cost-Benefit Analysis

### Current State
- **Cost:** $0 (no API calls)
- **Coverage:** ~20% (only explicit file references)
- **Developer burden:** High (manual doc updates, easy to forget)

### With Hybrid Approach
- **Cost:** ~$0.10-0.50 per week (contextual checks after commits)
- **Coverage:** ~80% (mtime + semantic + statistical + cross-refs)
- **Developer burden:** Low (prompted when needed, auto-suggestions)

### ROI Calculation

**Without tool:**
- 30 minutes per doc update to find all related docs manually
- 3 doc updates per week average = 1.5 hours/week
- Miss ~30% of updates = stale docs accumulate

**With tool:**
- 5 minutes per doc update (tool finds them, suggests changes)
- 3 doc updates per week = 15 minutes/week
- Miss ~5% of updates = high doc freshness

**Time saved:** 1.25 hours/week = ~60 hours/year
**Cost:** ~$25/year in API calls
**Value:** Developer time worth $50-200/hour → $3,000-12,000/year saved

---

## Implementation Sketch: docs_contextual_check.py

```python
#!/usr/bin/env python3
"""
Contextual Documentation Checker

Finds docs that need updating based on code changes, using:
1. Git diff analysis
2. LLM semantic understanding
3. Fast text search for statistical references
"""

import anthropic
import subprocess
from pathlib import Path

def get_changed_files(since: str = "HEAD~1") -> list[str]:
    """Get files changed since given ref."""
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", since],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().split("\n")

def find_docs_mentioning(terms: list[str], docs_dir: Path) -> dict[str, list[str]]:
    """Use ripgrep to find docs mentioning specific terms."""
    results = {}
    for term in terms:
        result = subprocess.run(
            ["rg", "-l", term, str(docs_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            results[term] = result.stdout.strip().split("\n")
    return results

def analyze_with_llm(
    changed_files: list[str],
    docs_dir: Path,
    client: anthropic.Anthropic,
) -> list[tuple[str, str]]:
    """
    Use LLM to find docs that might need updating.

    Returns list of (doc_path, reason) tuples.
    """
    # Read changed files
    file_contents = {}
    for file in changed_files[:10]:  # Limit to avoid huge prompts
        try:
            content = Path(file).read_text(encoding="utf-8")
            file_contents[file] = content[:5000]  # Truncate
        except Exception:
            continue

    # Build prompt
    prompt = f"""These code files were just changed:

{chr(10).join(f"- {f}" for f in changed_files)}

Changed file contents (truncated):
{chr(10).join(f"### {f}\n```python\n{c[:2000]}\n```\n" for f, c in file_contents.items())}

Which documentation files in /docs might need updating based on these changes?

Consider:
1. Migration docs tracking progress (e.g., "X of Y completed")
2. Architecture docs summarizing patterns
3. CLAUDE.md sections referencing these patterns
4. Pattern docs with examples from these files
5. Statistics/counts that might have changed

Return JSON array of objects with:
- doc_path: relative path from project root
- reason: why this doc might need updating
- confidence: low/medium/high

Only include docs with medium or high confidence.
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse JSON response (simplified - add error handling)
    import json
    return [(d["doc_path"], d["reason"]) for d in json.loads(response.content[0].text)]

def main():
    # 1. Get changed files
    changed_files = get_changed_files()

    # 2. Fast text search for statistical references
    # Example: if core/services/tasks/tasks_core_service.py changed,
    # search docs for "tasks", "TasksCoreService", "DomainConfig"

    # 3. LLM analysis for semantic connections
    client = anthropic.Anthropic()
    suggestions = analyze_with_llm(changed_files, Path("docs"), client)

    # 4. Print results
    print("🔍 Documentation update suggestions:\n")
    for doc_path, reason in suggestions:
        print(f"📄 {doc_path}")
        print(f"   Reason: {reason}\n")

    # 5. Offer to run updates
    print("\nRun updates with:")
    for doc_path, _ in suggestions:
        print(f"  uv run python scripts/docs_update.py --doc {doc_path}")

if __name__ == "__main__":
    main()
```

---

## Conclusion

**TL;DR:**
- ❌ **Don't try to improve docs_freshness.py** - it's doing its job correctly for its narrow use case
- ✅ **Add a complementary tool** that uses git + LLM for semantic staleness detection
- ✅ **Run it after commits** (via hook or explicit command) when developer has context
- ✅ **Keep both tools** - mtime-based for scheduled checks, semantic for commit-time checks

**Next Steps:**
1. Decide: git hook (automatic) vs explicit command (manual)?
2. Implement `docs_contextual_check.py` with LLM analysis
3. Test on next significant code change
4. Iterate based on false positive/negative rate

**Expected outcome:** 80% doc coverage with minimal developer burden and low cost (~$25/year).
