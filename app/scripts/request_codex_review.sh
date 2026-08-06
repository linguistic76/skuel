#!/usr/bin/env bash
# Request a Codex review on a PR and wait for the verdict — patiently, in-script.
#
# DESIGN: harness-agnostic. SKUEL must drive Codex from any agent / LLM / harness
# (Claude Code, OpenCode, …), so ALL the waiting lives in this portable bash
# primitive — never in a harness-specific scheduler (e.g. Claude Code's
# ScheduleWakeup). Any caller just runs the script and gets a verdict or a clean
# "still pending". How a harness INVOKES it (foreground, or backgrounded so the
# agent stays free) is the caller's concern, not the workflow's.
#
# WHY THIS SHAPE (lesson from #317, 2026-06-16): the prior version assumed
# "healthy Codex answers in ~90s; waiting longer buys nothing" and, on timeout,
# AUTO-APPLIED `codex-considered` as an "outage protocol". Both were wrong:
#   - Codex answered in ~13m 41s on #317 — ~4.7min AFTER the old script gave up.
#     So the deadline was structurally shorter than Codex's real latency, and a
#     normal-but-slow review got mislabeled an "outage".
#   - Worse, auto-labeling on timeout asserts "a verdict was considered" when
#     NOTHING was read — defeating the gate. It nearly merged a PR past a real
#     P2 finding Codex delivered minutes later.
# So now: wait long enough to actually catch Codex (default 20min), and NEVER
# apply the label without a real verdict. The label means a human/agent READ a
# verdict and decided — not that a timer expired.
#
# Verdict channels (poll BOTH every interval):
#   - inline review comments / submitted reviews (SHA-anchored) = FINDINGS
#   - plain issue comment matching the clean signature           = CLEAN
#   - any other Codex issue comment                              = READ-it (rc 2)
#
# Outcomes:
#   - clean    -> post consideration note + apply `codex-considered`, exit 0
#   - findings -> print them, exit 2 (read; address or write an accept/reject
#                 consideration note; then apply the label deliberately)
#   - timeout  -> gate stays RED, exit 3, NO label. Re-run to keep waiting. If
#                 Codex is genuinely down and you must proceed, applying the
#                 label is a DELIBERATE call — add a note saying so.
#   - unreadable window (zero successful channel reads) -> exit 1, NO label.
#
# All gh calls go through a retry wrapper with an explicitly captured token —
# GitHub auth incidents (2026-06-10) showed per-call 401 flapping that a single
# retry usually clears.
#
# Usage:
#   scripts/request_codex_review.sh <pr-number> [deadline-seconds]
#
# Exit codes: 0 clean (labeled) | 2 findings (read, not labeled)
#             3 timeout/pending (NOT labeled, gate stays red) | 1 usage / unreadable

set -uo pipefail

REPO="linguistic76/skuel"
PR="${1:-}"
DEADLINE="${2:-1200}"
POLL_INTERVAL=30
# Absolute, so every follow-up command this script PRINTS is runnable from the
# caller's cwd — the repo root and app/ both document invoking this script.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Shell-escaped form, for PRINTING only — a copy-pasted command must survive a
# checkout path containing whitespace. Never exec this: %q emits escapes that are
# text, not a filename. Execution sites use "$SCRIPT_DIR/..." quoted directly.
APPLY_CMD=$(printf '%q' "$SCRIPT_DIR/apply_codex_considered.sh")

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
# unreadable channel as zero lets the script reach the timeout path without
# ever reading the review surface. rc 4 propagates so the caller keeps polling,
# and a window with zero successful reads hard-fails instead of going quiet.
#
# Pagination: REST list endpoints default to 30 items/page in ascending order,
# so on a comment-heavy PR a fresh verdict can land beyond page 1 and read as a
# false pending. Comments endpoints take `since` (only items updated after the
# summon return, so page 1 holds them all); the reviews endpoint has no `since`,
# so per_page=100 covers it. The jq time filters stay as belt-and-braces
# (`since` matches on updated_at >=, jq on created/submitted_at strictly >).
check_verdict() {
  local since="$1" reviews inline comments
  reviews=$(gh_retry api "repos/$REPO/pulls/$PR/reviews?per_page=100" \
    --jq "[.[] | select(.user.login|test(\"codex\";\"i\")) | select(.submitted_at > \"$since\")] | length" \
    2>/dev/null) || return 4
  [[ "$reviews" =~ ^[0-9]+$ ]] || return 4
  # Inline comments are a first-class verdict surface, not a detail of the
  # review object (Codex P2 on #276): line-anchored comments can arrive without
  # a matching review, and skipping this lookup would route exactly that case
  # into a false pending — silently waiting over unread findings.
  inline=$(gh_retry api "repos/$REPO/pulls/$PR/comments?since=$since&per_page=100" \
    --jq "[.[] | select(.user.login|test(\"codex\";\"i\")) | select(.created_at > \"$since\")] | length" \
    2>/dev/null) || return 4
  [[ "$inline" =~ ^[0-9]+$ ]] || return 4
  if (( reviews > 0 || inline > 0 )); then
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
    # Only the known clean signature counts as clean. Anything else from Codex
    # on this channel (agentic task summaries, suggestion lists, account/connect
    # boilerplate) must be READ, not auto-labeled — observed live: an agentic
    # "Committed changes on the current branch" comment.
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

# The repo workflow (AGENTS.md, .github/workflows/README.md) treats a PR-side
# "Codex consideration" note as the audit trail for what was accepted/rejected
# before the label unblocks the gate. The clean path posts it automatically; on
# findings the note is written manually during the address cycle (it must say
# WHAT was accepted/rejected and why).
post_clean_consideration() {
  if gh_retry api "repos/$REPO/issues/$PR/comments" \
    -f body="**Codex consideration:** clean verdict — no findings to accept or reject." \
    --jq .html_url >/dev/null; then
    echo "✓ consideration note posted"
    return 0
  fi
  echo "⚠ could not post the consideration note — add it manually for the audit trail" >&2
  return 0  # the verdict comment itself is on the PR; don't block the label on this
}

# The label IS the gate's unblock signal — a silent failure here would report
# merge-ready without satisfying the gate (happened live during the 2026-06-10
# auth incident), and a plain label-add can be RACE-STRIPPED by a gate run still
# in flight from the last push (happened live on #584). Delegate to the
# race-safe applier, which drains in-flight gate runs and confirms the gate
# status actually goes green. Applied ONLY after a real CLEAN verdict was read
# (never on timeout).
apply_label() {
  if "$SCRIPT_DIR/apply_codex_considered.sh" "$PR"; then
    return 0
  fi
  echo "✗ codex-considered NOT confirmed green — re-run when ready:" >&2
  echo "  $APPLY_CMD $PR" >&2
  return 1
}

# Poll a single anchored window to the deadline. One cheap re-summon at the
# halfway mark guards against a dropped mention (anchored at the FIRST summon so
# a verdict that lands in the gap is still seen — Codex P2 on #276). Returns:
#   0 clean | 2 findings | 1 genuine timeout (>=1 successful read) |
#   4 window had ZERO successful reads (channels unreadable — caller must NOT
#     treat as a verdict, never label)
wait_for_verdict() {
  local since="$1" elapsed=0 rc read_ok=0 resummoned=0
  while (( elapsed < DEADLINE )); do
    sleep "$POLL_INTERVAL"; elapsed=$(( elapsed + POLL_INTERVAL ))
    check_verdict "$since"; rc=$?
    case $rc in
      0|2) return $rc ;;
      1)   read_ok=1
           if (( ! resummoned && elapsed >= DEADLINE / 2 )); then
             summon >/dev/null && resummoned=1
             echo "  … ${elapsed}s / ${DEADLINE}s (re-nudged @codex)" >&2
           else
             echo "  … ${elapsed}s / ${DEADLINE}s" >&2
           fi ;;
      4)   echo "  … ${elapsed}s / ${DEADLINE}s (channel read FAILED)" >&2 ;;
    esac
  done
  (( read_ok )) && return 1
  return 4
}

echo "▶ summoning @codex review on #$PR"
echo "  waiting up to ${DEADLINE}s — Codex on this repo has taken >13min; patience is in-script by design (portable across harnesses)."
SINCE=$(summon)
[[ -n "$SINCE" ]] || exit 1

wait_for_verdict "$SINCE"; RC=$?
case $RC in
  0)
    post_clean_consideration
    apply_label || exit 1
    exit 0
    ;;
  2)
    echo "→ Codex returned findings (above). READ them, then either address them"
    echo "  or write a PR-side accept/reject consideration note, and apply the label"
    echo "  deliberately (race-safe): $APPLY_CMD $PR"
    exit 2
    ;;
  4)
    echo "✗ verdict channels were unreadable for the entire window — cannot tell" >&2
    echo "  pending from an unread verdict; NOT labeling. Re-run when the API stabilizes." >&2
    exit 1
    ;;
  *)
    echo "▶ no Codex verdict after ${DEADLINE}s. This is NOT a no-show to label past —"
    echo "  Codex reviews here have taken >13min. The Codex Review Gate stays RED."
    echo "  Re-run this script to keep waiting, or check the PR shortly. Apply"
    echo "  codex-considered ONLY after reading a real verdict. If Codex is genuinely"
    echo "  down and you must proceed, that is a deliberate call — add a consideration"
    echo "  note saying so, then: $APPLY_CMD $PR"
    exit 3
    ;;
esac
