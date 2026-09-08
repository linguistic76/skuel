#!/usr/bin/env bash
# SKUEL secret-leak scan — the single implementation.
#
# Reads a unified diff on stdin, scans its ADDED lines, and exits non-zero if
# anything credential-shaped is found. `pre-commit` and `pre-push` both call
# this, so the two can no longer drift apart (they used to carry hand-synced
# copies of the pattern array, and the README asked humans to keep them equal).
#
# Two independent halves, because credentials come in two shapes:
#
#   1. CONTENT  — provider-issued keys with their own prefix (`sk-ant-…`,
#      `ghp_…`). Patterns live in secret-patterns.txt.
#
#   2. ASSIGNMENT — a credential-catalog NAME assigned a non-placeholder value,
#      whatever the value looks like. Names live in credential-keys.txt.
#      This half exists because Deepgram keys (40 hex), AuraDB passwords and
#      SESSION_SECRET_KEY are prefix-free high-entropy strings: a content regex
#      that caught them would also catch every hash, UUID and lockfile digest
#      in the tree. The name is the signal, not the value.
#
# A match is always printed REDACTED — the point of this hook is to keep the
# secret out of terminal scrollback and CI logs, not to show it to you.
#
# Usage:  <unified diff on stdin> | secret-scan.sh "<where, for the message>"
# Exit:   0 = clean · 1 = at least one match (reported on stderr)
#
# Bypass is the caller's business: both hooks honour SKUEL_ALLOW_SECRETS=1 and
# never invoke this script when it is set.
#
# See: app/scripts/git-hooks/README.md
#      app/tests/unit/scripts/test_secret_scan.py  (drives this file directly)

set -uo pipefail

context="${1:-staged changes}"
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

patterns_file="$here/secret-patterns.txt"
catalog_file="$here/credential-keys.txt"

for f in "$patterns_file" "$catalog_file"; do
  if [[ ! -r "$f" ]]; then
    printf '\033[31m✗ secret-scan: missing data file: %s\033[0m\n' "$f" >&2
    exit 1
  fi
done

# An assigned value shorter than this is a template placeholder, not a secret.
# It also encodes the empty-value arm of `_is_placeholder` below.
MIN_SECRET_LEN=20

diff_text=$(cat)

# One or two leading '+': a plain diff addition, or a line a merge resolution
# added relative to BOTH parents in a `--cc` combined diff. Excludes the
# '+++ b/file' header. pre-commit diffs never carry '++' lines, so using the
# combined-diff form for both callers is strictly stronger, never weaker.
added_lines=$(grep -E '^\+{1,2}[^+]' <<<"$diff_text" || true)
[[ -z "$added_lines" ]] && exit 0

fail=0

# $1 = label · $2 = matching lines · $3 = sed -E expression that redacts them.
report() {
  local label="$1" matches="$2" redact="$3" shown
  printf '\033[31m✗ Possible %s in %s:\033[0m\n' "$label" "$context" >&2
  if shown=$(printf '%s\n' "$matches" | sed -E -e "$redact" 2>/dev/null); then
    printf '%s\n' "$shown" | head -5 | sed 's/^/    /' >&2
  else
    # A redaction that fails must never fall through to printing the raw line.
    printf '    (%s line(s) withheld — redaction expression failed)\n' \
      "$(printf '%s\n' "$matches" | wc -l | tr -d ' ')" >&2
  fi
  fail=1
}

# ---------------------------------------------------------------------------
# Half 1 — content shapes
# ---------------------------------------------------------------------------
while IFS= read -r entry || [[ -n "$entry" ]]; do
  [[ -z "${entry// /}" || "$entry" == \#* ]] && continue
  label="${entry%%|*}"
  regex="${entry#*|}"
  matches=$(grep -E -- "$regex" <<<"$added_lines" || true)
  [[ -n "$matches" ]] && report "$label" "$matches" 's/'"$regex"'/[REDACTED]/g'
done < "$patterns_file"

# ---------------------------------------------------------------------------
# Half 2 — assignment shapes
# ---------------------------------------------------------------------------
# Placeholder rule, mirrored from core/config/credential_store.py::_is_placeholder
# so the hook and the credential funnel agree on what a placeholder is:
#
#   empty                     → excluded by MIN_SECRET_LEN
#   `your-*` prefix           → the second grep below
#   member of _PLACEHOLDER_VALUES → every member is empty or `your-`-prefixed
#                             except `test-key`, which is 8 chars. So the two
#                             arms above subsume the list today; that is an
#                             agreement, not a coincidence, and
#                             test_secret_scan.py pins it by driving this script
#                             with every member of the real set.
while IFS= read -r key || [[ -n "$key" ]]; do
  [[ -z "${key// /}" || "$key" == \#* ]] && continue
  lead="^\+{1,2}[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=[[:space:]]*[\"']?"
  matches=$(grep -E -- "${lead}[^[:space:]\"']{${MIN_SECRET_LEN},}" <<<"$added_lines" \
    | grep -Ev -- "${lead}your-" || true)
  # Redact everything past the first `=`; the name is what the reader needs.
  [[ -n "$matches" ]] && report "$key assignment" "$matches" 's/=.*/=[REDACTED]/'
done < "$catalog_file"

exit "$fail"
