#!/usr/bin/env bash
# Apply the `codex-considered` label race-safely and confirm the gate goes green.
#
# WHEN TO RUN: only AFTER a real Codex verdict was read and considered (the
# request_codex_review.sh contract). This script does NOT check that a verdict
# exists — it solves a different problem:
#
# THE RACE (observed live on #584, 2026-07-10): the Codex Review Gate workflow
# (.github/workflows/codex-gate.yml) removes `codex-considered` when it processes
# a `synchronize` event. Workflow runs are queued, not instant — so a gate run
# still in flight from the LAST push strips the label even when the label was
# applied AFTER that push. The label then silently vanishes and the gate reads
# RED at merge time. Re-adding once no runs were in flight stuck fine.
#
# So the race-safe sequence, all in-script:
#   1. wait for any in-flight "Codex Review Gate" runs on the PR head SHA to
#      complete (these are the pull_request-event runs that can strip the label),
#   2. apply the label (idempotent if already present),
#   3. poll the "Codex Review Gate" COMMIT STATUS on the head SHA until it
#      reports success, re-adding the label ONCE if something still strips it.
# If the head SHA changes mid-flight (a new push), abort — new code must be
# re-reviewed and re-considered, not auto-labeled.
#
# Like request_codex_review.sh, all waiting lives in this portable bash
# primitive (harness-agnostic), and all gh calls go through a 401-retry wrapper.
#
# Usage:
#   scripts/apply_codex_considered.sh <pr-number> [deadline-seconds]
#
# Exit codes: 0 gate green with label | 3 timeout (gate NOT confirmed green)
#             4 head SHA moved (label dropped deliberately) | 1 usage / API failure

set -uo pipefail

REPO="linguistic76/skuel"
PR="${1:-}"
DEADLINE="${2:-600}"
POLL_INTERVAL=15

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
  for _ in 1 2 3; do
    TOK=$(gh auth token 2>/dev/null) && [[ -n "$TOK" ]] && return 0
    sleep 2
  done
  return 1
}

gh_retry() {
  local out
  for _ in 1 2 3; do
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

# --- primitives ------------------------------------------------------------

head_sha() {
  gh_retry api "repos/$REPO/pulls/$PR" --jq .head.sha
}

# Count queued/in-progress "Codex Review Gate" workflow runs on the head SHA.
# These are the pull_request-event runs (synchronize/labeled/…) — exactly the
# ones whose synchronize handler strips the label. issue_comment-event runs
# carry the default branch's SHA, so they never match this filter (and they
# never remove the label anyway — only synchronize does).
inflight_gate_runs() {
  local sha="$1"
  gh_retry api "repos/$REPO/actions/runs?head_sha=$sha&per_page=100" \
    --jq '[.workflow_runs[] | select(.name == "Codex Review Gate") | select(.status != "completed")] | length'
}

# Latest "Codex Review Gate" commit status on the SHA (combined-status endpoint
# returns the newest status per context). Prints success/failure/pending, or
# "none" when the gate has not posted a status on this SHA yet.
gate_status() {
  local sha="$1"
  gh_retry api "repos/$REPO/commits/$sha/status" \
    --jq '[.statuses[] | select(.context == "Codex Review Gate")] | (.[0].state // "none")'
}

label_present() {
  local labels
  labels=$(gh_retry api "repos/$REPO/issues/$PR/labels" --jq '[.[].name] | join(",")') || return 2
  [[ ",$labels," == *",codex-considered,"* ]]
}

apply_label() {
  gh_retry api "repos/$REPO/issues/$PR/labels" -f "labels[]=codex-considered" --jq '.[0].name' >/dev/null
}

# --- main ------------------------------------------------------------------

SHA=$(head_sha)
[[ -n "$SHA" ]] || { echo "✗ could not resolve PR #$PR head SHA" >&2; exit 1; }
echo "▶ PR #$PR @ ${SHA:0:8} — race-safe codex-considered application"

ELAPSED=0
READDED=0
LABELED=0

while (( ELAPSED < DEADLINE )); do
  # A new push means new code: the prior consideration no longer applies.
  CUR=$(head_sha) || CUR=""
  if [[ -n "$CUR" && "$CUR" != "$SHA" ]]; then
    echo "✗ head moved ${SHA:0:8} → ${CUR:0:8} — a new commit invalidates the" >&2
    echo "  consideration. Re-review (request_codex_review.sh), then re-run this." >&2
    exit 4
  fi

  # Phase 1: drain in-flight gate runs before touching the label.
  INFLIGHT=$(inflight_gate_runs "$SHA") || INFLIGHT=""
  if [[ ! "$INFLIGHT" =~ ^[0-9]+$ ]]; then
    echo "  … ${ELAPSED}s / ${DEADLINE}s (run-list read FAILED — retrying)" >&2
  elif (( INFLIGHT > 0 )); then
    echo "  … ${ELAPSED}s / ${DEADLINE}s ($INFLIGHT gate run(s) in flight — label would be race-stripped)" >&2
  else
    # Phase 2: no runs in flight — apply (or re-apply once) the label.
    # An unreadable label list is NOT a stripped label (same principle as
    # request_codex_review.sh's rc-4 channel handling) — never spend the
    # one re-add budget on an API blip.
    label_present; LP=$?
    if (( LP == 2 )); then
      echo "  … ${ELAPSED}s / ${DEADLINE}s (label read FAILED — retrying)" >&2
    elif (( LP == 0 )); then
      LABELED=1
    else
      if (( LABELED && READDED )); then
        echo "✗ label stripped again after one re-add — something keeps removing it;" >&2
        echo "  inspect the PR's gate runs before forcing it." >&2
        exit 3
      fi
      if apply_label; then
        (( LABELED )) && { READDED=1; echo "  ↺ label was stripped — re-added once" >&2; }
        LABELED=1
        echo "✓ codex-considered applied"
      else
        echo "  … ${ELAPSED}s / ${DEADLINE}s (label apply FAILED — retrying)" >&2
      fi
    fi

    # Phase 3: labeled — wait for the labeled-event run to post a green status.
    if (( LABELED )); then
      STATE=$(gate_status "$SHA") || STATE="unreadable"
      case "$STATE" in
        success)
          echo "✓ Codex Review Gate is GREEN on ${SHA:0:8} — safe to merge"
          exit 0 ;;
        *)
          echo "  … ${ELAPSED}s / ${DEADLINE}s (gate status: $STATE)" >&2 ;;
      esac
    fi
  fi

  sleep "$POLL_INTERVAL"; ELAPSED=$(( ELAPSED + POLL_INTERVAL ))
done

echo "▶ gate not confirmed green after ${DEADLINE}s. The label may be applied but"
echo "  UNVERIFIED — re-run this script, and re-check labels + gate before merging."
exit 3
