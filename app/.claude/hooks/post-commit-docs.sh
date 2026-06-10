#!/bin/bash
#
# Claude Code PostToolUse Hook: Documentation Staleness Detection
#
# Fires after any Bash command that invokes `git commit` — including compound
# chains like `git add ... && git commit ...` (the PostToolUse matcher fires
# on every Bash call; filtering happens inside this script). Collects changed
# files, finds referencing docs/skills, and returns additionalContext (for
# Claude to semantically evaluate staleness) + a systemMessage summary.
#
# See: /docs/tools/AUTOMATIC_DOCS_CHECK.md
#

set -euo pipefail

# Read JSON from stdin
INPUT=$(cat)

# Filter by the actual command that ran — the parent matcher fires on every Bash
# call, so we have to short-circuit here for non-commit commands. Settings.json
# does NOT support an "if" field on hooks; filtering MUST happen inside the script.
TOOL_COMMAND=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
    cmd = data.get('tool_input', {}).get('command', '')
    print(cmd if isinstance(cmd, str) else '')
except Exception:
    print('')
" "$INPUT" 2>/dev/null || echo "")

# Match a `git commit` invocation at a command-segment boundary (start of
# command, or after ; & | or whitespace) — a bare prefix check missed every
# compound chain ("git add ... && git commit ..."), which kept this hook
# silent for most real commits.
COMMIT_RE='(^|[;&|[:space:]])git[[:space:]]+commit'
if [[ ! "$TOOL_COMMAND" =~ $COMMIT_RE ]]; then
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

# Positive marker: a successful git commit prints its stats summary
# ("N file(s) changed, ..."). Requiring it kills the false-fire class where
# a non-commit command merely CONTAINS the string "git commit" (e.g. a grep
# pattern) inside the recency window. Known miss: `git commit --quiet`
# prints nothing and is skipped — acceptable for an advisory check.
COMMIT_MARKER_RE='[0-9]+ files? changed'
if [[ ! "$TOOL_RESPONSE" =~ $COMMIT_MARKER_RE ]]; then
    echo '{}'
    exit 0
fi

# Get project root
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)/app
if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo '{}'
    exit 0
fi

# Guard against false fires: the regex can match inside a quoted string
# (e.g. a commit message that merely *mentions* git commit), and HEAD would
# then be some older commit. Only proceed if HEAD was committed moments ago.
MAX_AGE_S="${SKUEL_DOCS_CHECK_MAX_AGE_S:-300}"
HEAD_TS=$(git -C "$PROJECT_ROOT" log -1 --format=%ct 2>/dev/null || echo 0)
if (( $(date +%s) - HEAD_TS > MAX_AGE_S )); then
    echo '{}'
    exit 0
fi

# Get changed code files from the commit (deletions included — docs that
# reference a deleted file definitely need updating). Not just .py: static
# JS, hooks, and config are documented in skills/docs too.
CHANGED_FILES=$(git -C "$PROJECT_ROOT" diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null | grep -E '\.(py|js|css|sh|toml|ya?ml)$' || true)
if [[ -z "$CHANGED_FILES" ]]; then
    echo '{}'
    exit 0
fi

# Get diff stat summary (one line)
DIFF_STAT=$(git -C "$PROJECT_ROOT" diff-tree --no-commit-id --stat HEAD 2>/dev/null | tail -1 || true)

# Detect newly added .md files (for INDEX.md updates)
NEW_DOCS=$(git -C "$PROJECT_ROOT" diff-tree --no-commit-id --diff-filter=A -r HEAD 2>/dev/null | awk '{print $NF}' | grep '\.md$' || true)

# Build grep patterns from changed filenames (deduplicated basenames,
# dots escaped so "x.py" doesn't match "xapy")
PATTERNS=""
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    bn=$(basename "$file")
    bn="${bn//./\\.}"
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
Changed code files ($FILE_COUNT):
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

# Build a short user-visible summary
SUMMARY="📄 Post-commit docs check: $FILE_COUNT files changed"
if [[ "$DOC_COUNT" -gt 0 ]]; then
    SUMMARY="$SUMMARY, $DOC_COUNT docs may need review"
fi
if [[ "$SKILL_COUNT" -gt 0 ]]; then
    SUMMARY="$SUMMARY, $SKILL_COUNT skills flagged"
fi

# Use Python for reliable JSON escaping.
# additionalContext = full detail for Claude — for PostToolUse hooks it MUST
# be nested under hookSpecificOutput or the harness ignores it (a top-level
# additionalContext was silently dropped). systemMessage = visible summary.
python3 -c "
import json, sys
print(
    json.dumps(
        {
            'hookSpecificOutput': {
                'hookEventName': 'PostToolUse',
                'additionalContext': sys.argv[1],
            },
            'systemMessage': sys.argv[2],
        }
    )
)
" "$MSG" "$SUMMARY"

exit 0
