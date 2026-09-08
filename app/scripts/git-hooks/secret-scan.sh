#!/usr/bin/env bash
# SKUEL secret-leak scan — the single implementation.
#
# Reads a unified diff on stdin, scans its ADDED lines, and exits non-zero if
# anything credential-shaped is found. `pre-commit` and `pre-push` both call
# this file, which is what keeps the commit-time and push-time fences identical:
# there is one pattern set, not two that a human has to keep equal.
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
# '+++ b/file' header. pre-commit diffs carry no '++' lines, so the combined-diff
# form is strictly stronger for both callers, never weaker.
added_lines=$(grep -E '^\+{1,2}[^+]' <<<"$diff_text" || true)
[[ -z "$added_lines" ]] && exit 0

fail=0

# EVERY redaction is applied to EVERY line printed, not just the one whose match
# produced the report. One added line can carry two credentials — an OpenAI key
# and an Anthropic key — and reporting them separately with only the current
# expression prints each secret verbatim in the other's report. So the whole set
# is assembled first, below, and `report` applies all of it.
redact_args=(-E)
add_redaction() { redact_args+=(-e "$1"); }

# $1 = label · $2 = matching lines.
report() {
  local label="$1" matches="$2" shown
  printf '\033[31m✗ Possible %s in %s:\033[0m\n' "$label" "$context" >&2
  if shown=$(printf '%s\n' "$matches" | sed "${redact_args[@]}" 2>/dev/null); then
    printf '%s\n' "$shown" | head -5 | sed 's/^/    /' >&2
  else
    # A redaction that fails must never fall through to printing the raw line.
    printf '    (%s line(s) withheld — redaction expression failed)\n' \
      "$(printf '%s\n' "$matches" | wc -l | tr -d ' ')" >&2
  fi
  fail=1
}

# ---------------------------------------------------------------------------
# Read the two data files once. `#` comments and blank lines are ignored.
# ---------------------------------------------------------------------------
read_data_file() {
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "${line// /}" || "$line" == \#* ]] && continue
    printf '%s\n' "$line"
  done < "$1"
}

mapfile -t pattern_entries < <(read_data_file "$patterns_file")
mapfile -t catalog_keys < <(read_data_file "$catalog_file")

# The lead a credential NAME can appear behind, in either syntax. Split out
# because both the matcher and the redaction expression need it.
#
#   assignment    KEY=value · KEY: value · export KEY=value
#     The env / shell / YAML-mapping form (`NEO4J_PASSWORD: ${NEO4J_PASSWORD}` in
#     docker-compose.yml). A quoted value here may contain spaces: a passphrase is
#     one value, not four, and anchoring the floor to its first word would clear
#     `NEO4J_PASSWORD="correct horse battery staple"`.
#
#   data literal  "KEY": value · config["KEY"] = value
#     JSON, dict literals, and subscript assignment, inline or one key per line.
#     The value must be SPACE-FREE to count. In this repo a dict keyed by a
#     credential name holds a *description* — `"OPENAI_API_KEY": "OpenAI API key
#     for embeddings and AI features"` in core/config/environment_validator.py,
#     and the catalog in credential_setup.py itself. Accepting a spaced value here
#     reports the credential catalog as a leak; a real credential has no spaces.
# Between the name and its value: an optional `]` (subscript assignment), an
# optional type annotation (`SESSION_SECRET_KEY: str = "…"`), then `=` or `:`.
# The annotation group is optional and its `[=:]` is required, so a bare YAML
# mapping (`KEY: value`) still matches by skipping the group.
_ident="[A-Za-z_][A-Za-z0-9_.]*(\[[^]]*\])?"
sep="[[:space:]]*\]?[[:space:]]*(:[[:space:]]*${_ident}[[:space:]]*)?[=:][[:space:]]*"
# A comment prefix is allowed before the name: a credential parked in a commented
# config example (`# NEO4J_PASSWORD=…`) is in the history exactly as much as an
# uncommented one.
_comment="(([#;]+|//|--|\*)[[:space:]]*)?"
assign_lead_for()  { printf '^\\+{1,2}[[:space:]]*%s(export[[:space:]]+)?%s%s' "$_comment" "$1" "$sep"; }
literal_lead_for() { printf '^\\+{1,2}.*[\"'"'"']%s[\"'"'"']%s' "$1" "$sep"; }

# ---------------------------------------------------------------------------
# Assemble EVERY redaction before reporting anything (see `report` above).
# ---------------------------------------------------------------------------
for entry in "${pattern_entries[@]}"; do
  add_redaction 's/'"${entry#*|}"'/[REDACTED]/g'
done
for key in "${catalog_keys[@]}"; do
  # Anchored on the key, not the line's first `=`: for an inline literal
  # (`config = {"KEY": …}`) that would be the assignment to `config`, and would
  # swallow the one thing the reader needs — which credential to rotate.
  add_redaction "s/(${key}[\"']?${sep}).*/\1[REDACTED]/"
done

# ---------------------------------------------------------------------------
# Half 1 — content shapes
# ---------------------------------------------------------------------------
for entry in "${pattern_entries[@]}"; do
  label="${entry%%|*}"
  regex="${entry#*|}"
  matches=$(grep -E -- "$regex" <<<"$added_lines" || true)
  [[ -n "$matches" ]] && report "$label" "$matches"
done

# ---------------------------------------------------------------------------
# Half 2 — assignment shapes
# ---------------------------------------------------------------------------
# What counts as a placeholder, and is therefore not reported:
#
#   empty, or shorter than MIN_SECRET_LEN   → the length quantifier below
#   `your-*` prefix                         → the placeholder alternation below
#   a `$`-interpolation (`${VAR}`, `$VAR`)  → a reference to a credential is not one
#   an angle-bracketed token                → the docs convention; the only arm that
#                                             looks PAST the start of the value,
#                                             because `NEO4J_AUTH=neo4j/<password>`
#                                             in SETUP.md is a composite whose
#                                             placeholder half is second
#
# This is deliberately BROADER than core/config/credential_store.py::_is_placeholder,
# which calls only the empty string, a `your-*` prefix and its own _PLACEHOLDER_VALUES
# list placeholders. Every member of that list is covered here (each is empty,
# `your-`-prefixed, or under the length floor — test_secret_scan.py pins that by
# driving this script with the real set), so the hook never reports something the
# funnel would accept.
#
# The length floor is what the committed templates need: `.env.example` carries
# `firefly-local-dev` and `sk-your-openai-key`, and the setup docs carry
# `<your-openai-key>` — none `your-`-prefixed, none in _PLACEHOLDER_VALUES. An
# exact-list rule would report all three, and a scan that blocks `.env.example`
# gets bypassed with SKUEL_ALLOW_SECRETS=1 until it stops being a fence at all.
#
# The floor's cost, stated plainly: a locally-chosen credential under
# MIN_SECRET_LEN characters is not caught by this half. That is a real gap, and
# it is bounded — every provider-issued credential in the catalog is far longer
# (an AuraDB password is 43 base64url chars, SESSION_SECRET_KEY 43, a Firefly PAT
# hundreds), so what it leaves uncovered is a short hand-picked local password.
# The content half catches the provider keys regardless of how they are assigned.
floor="{${MIN_SECRET_LEN},}"
next_floor="{$((MIN_SECRET_LEN - 1)),}"
# A double- or single-quoted run (spaces allowed), or a bare token.
assign_value="([\"][^\"]${floor}|['][^']${floor}|[^[:space:]\"'][^[:space:]]${next_floor})"
literal_value="[\"']?[^[:space:]\"'][^[:space:]\"']${next_floor}"
# `your-` matches ANYWHERE in the value, not only at its start: `.env.example`
# carries `sk-your-openai-key` and `# ANTHROPIC_API_KEY=sk-ant-your-anthropic-key`,
# where the convention sits behind a provider prefix. Same reason the
# angle-bracket arm looks past the start.
placeholder="([^[:space:]]*your-|[$]|[^[:space:]]*<[^>[:space:]]*>)"

for key in "${catalog_keys[@]}"; do
  assign_lead="$(assign_lead_for "$key")"
  literal_lead="$(literal_lead_for "$key")"
  matches=$(grep -E -- "${assign_lead}${assign_value}|${literal_lead}${literal_value}" <<<"$added_lines" \
    | grep -Ev -- "(${assign_lead}|${literal_lead})[\"']?${placeholder}" || true)
  [[ -n "$matches" ]] && report "$key assignment" "$matches"
done

exit "$fail"
