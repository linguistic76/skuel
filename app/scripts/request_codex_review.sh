#!/usr/bin/env bash
# Request a Codex review on a PR and wait for the verdict — timeboxed.
#
# Encodes SKUEL's streamlined Codex policy (2026-06-10): Codex is advisory on
# a timer, not an unbounded gate. A healthy Codex answers in ~90s; waiting
# longer than a few minutes buys nothing, and GitHub status-page ceremony
# (indicator back to "none") lags real recovery by up to hours. So:
#
#   1. Summon `@codex review` and poll BOTH verdict channels every 20s:
#      - inline review (state COMMENTED, "Reviewed commit" SHA) = FINDINGS
#      - plain issue comment (no SHA)                           = CLEAN
#   2. Verdict within the deadline (default 240s):
#      - clean    -> apply `codex-considered`, exit 0 (merge-ready)
#      - findings -> print them, exit 2 (address, push, re-run this script)
#   3. No-show at deadline -> CAPABILITY probe (a live API call, never the
#      status page). API healthy -> one automatic re-summon + second timebox
#      (the mention itself may have been dropped; polling stays anchored at
#      the FIRST summon so a gap-delivered verdict is still seen). API
#      degraded, or second no-show -> post an outage note, apply
#      `codex-considered`, exit 3 (proceed per workflow — considered, not
#      zero). A window whose channel reads ALL failed exits 1 without
#      labeling — an unreadable surface is not a no-show.
#
# Worst case is bounded at ~2x deadline + slack instead of "until the GitHub
# status page feels better".
#
# All gh calls go through a retry wrapper with an explicitly captured token —
# GitHub auth incidents (2026-06-10) showed per-call 401 flapping that a
# single retry usually clears.
#
# Usage:
#   scripts/request_codex_review.sh <pr-number> [deadline-seconds]
#
# Exit codes: 0 clean (labeled) | 2 findings | 3 no-show (labeled, proceed)
#             1 usage / unrecoverable infra error

set -uo pipefail

REPO="linguistic76/skuel"
PR="${1:-}"
DEADLINE="${2:-240}"
POLL_INTERVAL=20

if [[ -z "$PR" || ! "$PR" =~ ^[0-9]+$ ]]; then
  echo "usage: $0 <pr-number> [deadline-seconds]" >&2
  exit 1
fi
if [[ ! "$DEADLINE" =~ ^[0-9]+$ ]] || (( DEADLINE < POLL_INTERVAL )); then
  echo "✗ deadline must be an integer >= ${POLL_INTERVAL}s (got: $DEADLINE)" >&2
  exit 1
fi

# --- resilient gh ----------------------------------------------------------

TOK=""
acquire_token() {
  local i
  for i in 1 2 3; do
    TOK=$(gh auth token 2>/dev/null) && [[ -n "$TOK" ]] && return 0
    sleep 2
  done
  return 1
}

gh_retry() {
  local i out
  for i in 1 2 3; do
    out=$(GH_TOKEN="$TOK" gh "$@" 2>&1) && { printf '%s' "$out"; return 0; }
    if [[ "$out" == *"401"* || "$out" == *"Requires authentication"* ]]; then
      sleep 5
      acquire_token || true
      continue
    fi
    printf '%s' "$out" >&2
    return 1
  done
  printf '%s' "$out" >&2
  return 1
}

# Through gh_retry deliberately: a FLAPPING API (one of three attempts
# succeeds) counts as healthy -> we re-summon, which is the right bet — the
# mention may still deliver, and the cost is one more bounded timebox.
api_healthy() {
  gh_retry api graphql -f query='query{viewer{login}}' >/dev/null 2>&1
}

acquire_token || { echo "✗ could not read gh auth token" >&2; exit 1; }

# --- summon + poll ---------------------------------------------------------

# Prints the summon timestamp; prints nothing on failure (exit inside $(...)
# only leaves the subshell, so callers must check for empty output).
summon() {
  local since
  since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  gh_retry api "repos/$REPO/issues/$PR/comments" -f body="@codex review" --jq .html_url >/dev/null \
    || { echo "✗ failed to post summon comment" >&2; return 1; }
  echo "$since"
}

# Prints the verdict (if any) and returns:
#   0 clean | 2 findings | 1 none yet | 4 channels unreadable
#
# A failed lookup is NOT an empty result (Codex P2 on #276): counting an
# unreadable channel as zero lets the script reach the no-show path and
# label codex-considered without ever reading the review surface. rc 4
# propagates so the caller keeps polling, and a window with zero successful
# reads hard-fails instead of labeling.
#
# Pagination: REST list endpoints default to 30 items/page in ascending
# order, so on a comment-heavy PR a fresh verdict can land beyond page 1 and
# read as a false no-show — the outage path would then label over an unread
# verdict (Codex P2 on #276). Comments endpoints take `since` (only items
# updated after the summon return, so page 1 holds them all); the reviews
# endpoint has no `since`, so per_page=100 covers it (a PR with >100 reviews
# is out of scope for a timeboxed advisory check). The jq time filters stay
# as belt-and-braces (`since` matches on updated_at >=, jq on created/
# submitted_at strictly >).
check_verdict() {
  local since="$1" reviews comments
  reviews=$(gh_retry api "repos/$REPO/pulls/$PR/reviews?per_page=100" \
    --jq "[.[] | select(.user.login|test(\"codex\";\"i\")) | select(.submitted_at > \"$since\")] | length" \
    2>/dev/null) || return 4
  [[ "$reviews" =~ ^[0-9]+$ ]] || return 4
  if (( reviews > 0 )); then
    echo "── Codex FINDINGS (inline review) ──"
    gh_retry api "repos/$REPO/pulls/$PR/comments?since=$since&per_page=100" \
      --jq ".[] | select(.user.login|test(\"codex\";\"i\")) | select(.created_at > \"$since\") | \"\(.path):\(.line // 0)\n\(.body)\n\"" || true
    return 2
  fi
  comments=$(gh_retry api "repos/$REPO/issues/$PR/comments?since=$since&per_page=100" \
    --jq "[.[] | select(.user.login|test(\"codex\";\"i\")) | select(.created_at > \"$since\")] | length" \
    2>/dev/null) || return 4
  [[ "$comments" =~ ^[0-9]+$ ]] || return 4
  if (( comments > 0 )); then
    local body
    body=$(gh_retry api "repos/$REPO/issues/$PR/comments?since=$since&per_page=100" \
      --jq "[.[] | select(.user.login|test(\"codex\";\"i\")) | select(.created_at > \"$since\") | .body] | join(\"\n\")" || true)
    # Only the known clean signature counts as clean. Anything else from
    # Codex on this channel (agentic task summaries, suggestion lists,
    # account/connect boilerplate) must be READ, not auto-labeled — observed
    # live: an agentic "Committed changes on the current branch" comment.
    if grep -qiE "didn'?t find any (major )?issues" <<< "$body"; then
      echo "── Codex CLEAN verdict ──"
      printf '%s\n' "${body:0:300}"
      return 0
    fi
    echo "── Codex responded with an UNRECOGNIZED comment shape — read before proceeding ──"
    printf '%s\n' "$body"
    return 2
  fi
  return 1
}

# The label IS the gate's unblock signal — a silent failure here would
# report merge-ready without satisfying the gate (happened live during the
# 2026-06-10 auth incident). Hard-fail so the caller retries explicitly.
apply_label() {
  if gh_retry api "repos/$REPO/issues/$PR/labels" -f "labels[]=codex-considered" --jq '.[0].name' >/dev/null; then
    echo "✓ codex-considered applied"
    return 0
  fi
  echo "✗ could not apply codex-considered (gate NOT satisfied) — apply manually:" >&2
  echo "  gh pr edit $PR --add-label codex-considered" >&2
  return 1
}

# Returns: 0 clean | 2 findings | 1 genuine no-show (>=1 successful read) |
#          4 window had ZERO successful reads (channels unreadable — caller
#          must NOT treat as no-show, never label)
wait_for_verdict() {
  local since="$1" elapsed=0 rc read_ok=0
  while (( elapsed < DEADLINE )); do
    sleep "$POLL_INTERVAL"; elapsed=$(( elapsed + POLL_INTERVAL ))
    check_verdict "$since"; rc=$?
    case $rc in
      0|2) return $rc ;;
      1)   read_ok=1; echo "  … ${elapsed}s / ${DEADLINE}s" >&2 ;;
      4)   echo "  … ${elapsed}s / ${DEADLINE}s (channel read FAILED)" >&2 ;;
    esac
  done
  (( read_ok )) && return 1
  return 4
}

echo "▶ summoning @codex review on #$PR (deadline ${DEADLINE}s)"
SINCE=$(summon)
[[ -n "$SINCE" ]] || exit 1

wait_for_verdict "$SINCE"; RC=$?
if [[ $RC -eq 0 ]]; then apply_label || exit 1; exit 0; fi
if [[ $RC -eq 2 ]]; then echo "→ address findings, push, re-run this script"; exit 2; fi

# No-show. Capability probe decides between re-summon and outage protocol.
if [[ $RC -eq 1 ]] && api_healthy; then
  echo "▶ no verdict in ${DEADLINE}s but API healthy — one automatic re-summon"
  # SINCE stays anchored at the FIRST summon (Codex P2 on #276): resetting
  # it to the re-summon timestamp would hide a verdict that landed in the
  # gap between window 1's last poll and the second mention. The re-summon
  # is just a nudge; window 2's first poll then catches any gap verdict.
  summon >/dev/null || exit 1
  wait_for_verdict "$SINCE"; RC=$?
  if [[ $RC -eq 0 ]]; then apply_label || exit 1; exit 0; fi
  if [[ $RC -eq 2 ]]; then echo "→ address findings, push, re-run this script"; exit 2; fi
fi

if [[ $RC -eq 4 ]]; then
  echo "✗ verdict channels were unreadable for an entire window — cannot" >&2
  echo "  distinguish no-show from unread verdict; NOT labeling. Re-run when" >&2
  echo "  the API stabilizes." >&2
  exit 1
fi

echo "▶ Codex no-show — applying outage protocol (considered, not zero)"
gh_retry api "repos/$REPO/issues/$PR/comments" \
  -f body="Codex was summoned twice with a ${DEADLINE}s timebox each and delivered no verdict on any channel (healthy Codex answers in ~90s) — treating as infra failure per workflow and applying \`codex-considered\`. Re-summon later if a verdict is wanted." \
  --jq .html_url >/dev/null || true
apply_label || exit 1
exit 3
