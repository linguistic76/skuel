#!/bin/bash
#
# Claude Code PostToolUse Hook: Documentation Staleness Detection
#
# Fires after every Bash tool use. Fast-exits for non-commits (~0ms).
# For commits: collects changed files, finds referencing docs, returns
# a systemMessage so Claude can semantically evaluate staleness.
#
# This replaces regex-based pattern matching with Claude's semantic
# understanding of what actually changed and whether docs need updating.
#

set -euo pipefail

# Read JSON from stdin into variable
INPUT=$(cat)

# Fast path: extract command using Python (jq not guaranteed)
COMMAND=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
    print(data.get('tool_input', {}).get('command', ''))
except Exception:
    print('')
" "$INPUT" 2>/dev/null || echo "")

if [[ "$COMMAND" != *"git commit"* ]]; then
    echo '{}'
    exit 0
fi

# Check if the commit succeeded by looking at tool_response
TOOL_RESPONSE=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
    resp = data.get('tool_response', '')
    print(resp if isinstance(resp, str) else json.dumps(resp))
except Exception:
    print('')
" "$INPUT" 2>/dev/null || echo "")

if [[ "$TOOL_RESPONSE" == *"nothing to commit"* ]] || [[ "$TOOL_RESPONSE" == *"no changes added"* ]]; then
    echo '{}'
    exit 0
fi

# Get project root
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)/app
if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo '{}'
    exit 0
fi

# Get changed .py files from the commit
CHANGED_FILES=$(git -C "$PROJECT_ROOT" diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null | grep '\.py$' || true)
if [[ -z "$CHANGED_FILES" ]]; then
    echo '{}'
    exit 0
fi

# Get diff stat summary (one line)
DIFF_STAT=$(git -C "$PROJECT_ROOT" diff-tree --no-commit-id --stat HEAD 2>/dev/null | tail -1 || true)

# Detect newly added .md files (for INDEX.md updates)
NEW_DOCS=$(git -C "$PROJECT_ROOT" diff-tree --no-commit-id --diff-filter=A -r HEAD 2>/dev/null | awk '{print $NF}' | grep '\.md$' || true)

# Build ripgrep patterns from changed filenames (deduplicated basenames)
PATTERNS=""
declare -A SEEN_BASENAMES 2>/dev/null || true
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    bn=$(basename "$file")
    # Simple dedup: skip if we already have this basename in the pattern
    if [[ "$PATTERNS" == *"$bn"* ]]; then
        continue
    fi
    if [[ -n "$PATTERNS" ]]; then
        PATTERNS="$PATTERNS|$bn"
    else
        PATTERNS="$bn"
    fi
done <<< "$CHANGED_FILES"

# Limit to 20 patterns to avoid huge regex
PATTERN_COUNT=$(echo "$PATTERNS" | tr '|' '\n' | wc -l)
if [[ "$PATTERN_COUNT" -gt 20 ]]; then
    PATTERNS=$(echo "$PATTERNS" | tr '|' '\n' | head -20 | tr '\n' '|' | sed 's/|$//')
fi

# Find docs that reference changed files
# Note: rg is a Claude Code alias, not available in hook subprocesses.
# Use grep -rl which is universally available.
REFERENCING_DOCS=""
if [[ -n "$PATTERNS" ]]; then
    REFERENCING_DOCS=$(grep -rl -E "$PATTERNS" \
        "$PROJECT_ROOT/docs/" \
        "$PROJECT_ROOT/CLAUDE.md" \
        "$PROJECT_ROOT/.claude/skills/" \
        --include="*.md" \
        2>/dev/null | \
        sed "s|$PROJECT_ROOT/||g" | \
        sort -u || true)
fi

# Count results
FILE_COUNT=$(echo "$CHANGED_FILES" | grep -c '.' || echo 0)
DOC_COUNT=0
if [[ -n "$REFERENCING_DOCS" ]]; then
    DOC_COUNT=$(echo "$REFERENCING_DOCS" | grep -c '.' || echo 0)
fi

# Identify skills whose primary docs appear in the referencing docs list
SKILL_LIST=""
SKILL_COUNT=0
if [[ "$DOC_COUNT" -gt 0 ]]; then
    SKILL_LIST=$(python3 -c "
import sys, yaml
try:
    metadata_file = sys.argv[1] + '/.claude/skills/skills_metadata.yaml'
    with open(metadata_file) as f:
        data = yaml.safe_load(f)
    ref_docs = set(sys.argv[2].split('\n')) if sys.argv[2] else set()
    results = []
    for skill in data.get('skills', []):
        name = skill['name']
        reasons = []
        for doc in skill.get('primary_docs', []):
            doc_rel = doc.lstrip('/')
            if doc_rel in ref_docs:
                reasons.append(f'primary doc {doc_rel.rsplit(\"/\", 1)[-1]} references changed files')
                break
        skill_dir = '.claude/skills/' + name + '/'
        for rd in ref_docs:
            if rd.startswith(skill_dir):
                reasons.append('skill file directly references changed files')
                break
        if reasons:
            results.append(f'  - @{name} ({reasons[0]})')
    print('\n'.join(results))
except Exception:
    pass
" "$PROJECT_ROOT" "$REFERENCING_DOCS" 2>/dev/null || true)
    if [[ -n "$SKILL_LIST" ]]; then
        SKILL_COUNT=$(echo "$SKILL_LIST" | grep -c '.' || echo 0)
    fi
fi

# Only produce a message if there are referencing docs or new .md files
if [[ "$DOC_COUNT" -eq 0 ]] && [[ -z "$NEW_DOCS" ]]; then
    echo '{}'
    exit 0
fi

# Format changed files as a compact list
CHANGED_LIST=$(echo "$CHANGED_FILES" | head -15 | sed 's/^/  - /' || true)
if [[ "$FILE_COUNT" -gt 15 ]]; then
    CHANGED_LIST="$CHANGED_LIST
  - ... and $((FILE_COUNT - 15)) more"
fi

# Format referencing docs
DOC_LIST=""
if [[ -n "$REFERENCING_DOCS" ]]; then
    DOC_LIST=$(echo "$REFERENCING_DOCS" | head -15 | sed 's/^/  - /' || true)
    if [[ "$DOC_COUNT" -gt 15 ]]; then
        DOC_LIST="$DOC_LIST
  - ... and $((DOC_COUNT - 15)) more"
    fi
fi

# Format new docs
NEW_DOC_LIST=""
if [[ -n "$NEW_DOCS" ]]; then
    NEW_DOC_LIST=$(echo "$NEW_DOCS" | sed 's/^/  - /')
fi

# Build structured message
MSG="POST-COMMIT DOCS CHECK: A commit just landed. Review whether any documentation needs updating.

Commit stats: $DIFF_STAT
Changed Python files ($FILE_COUNT):
$CHANGED_LIST"

if [[ -n "$DOC_LIST" ]]; then
    MSG="$MSG

Docs that reference changed files ($DOC_COUNT):
$DOC_LIST"
fi

if [[ -n "$NEW_DOC_LIST" ]]; then
    MSG="$MSG

Newly added .md files (may need INDEX.md entry):
$NEW_DOC_LIST"
fi

if [[ -n "$SKILL_LIST" ]]; then
    MSG="$MSG

Skills that may need review ($SKILL_COUNT):
$SKILL_LIST"
fi

MSG="$MSG

ACTION: Using your understanding of what this commit changed and why, determine if any of the flagged docs are actually stale. For each stale doc, apply targeted updates. Also check flagged skills for stale content. If nothing is stale, just confirm no updates needed. Do NOT update docs for trivial changes (typo fixes, formatting, import reordering)."

# Use Python for reliable JSON escaping
python3 -c "
import json, sys
print(json.dumps({'additionalContext': sys.argv[1]}))
" "$MSG"

exit 0
