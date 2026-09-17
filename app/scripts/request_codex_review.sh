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
# Verdict channels (poll ALL every interval, and PRINT every one that fires):
#   - inline review comments (SHA-anchored)             = FINDINGS
#   - the BODY of a submitted review                    = FINDINGS
#   - plain issue comment matching the clean signature  = CLEAN
#   - any other Codex issue comment                     = READ-it (rc 2)
#   - EXCEPT the review-status widget                   = PENDING, never a verdict
#
# The status widget is one issue comment Codex posts the moment it is summoned
# (marker `<!-- codex-pull-request-review-summary -->`) and then EDITS in place:
# a table whose Status cell moves from "Running" to "Completed". It carries no
# findings and no clean signature in either state — the verdict arrives on the
# channels above, and can land minutes after the widget — so it is filtered out
# of the issue-comment channel by its marker: it can neither clean nor "find".
#
# The first two are INDEPENDENT surfaces and a finding can arrive on either, so
# every channel the verdict COUNTS is also PRINTED. Counting one without printing
# it is worse than not reading it: the reader is told findings exist and shown a
# different set. (Incident: #1301.)
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
# RESUMING (--resume): a wait that dies — the harness stops it, the terminal
# goes away — loses the poll, not the summon. Re-running plainly would post a
# SECOND `@codex review` and anchor its window at that second comment, so a
# verdict landing between the two is never read. `--resume` posts nothing.
# Every summon this script posts records the head SHA it asks about
# (`<!-- codex-summon head=<sha> -->`, invisible in the rendered PR), and a
# resumed wait anchors at the OLDEST summon by the authenticated user FOR THE
# CURRENT HEAD since the last `codex-considered` labeling. A verdict is about a
# SHA: a summon for another head reviewed other code, whatever its date (commit
# dates are supplied by the commit — a force-push of an older commit carries an
# older date — so no timestamp can stand in for the SHA), and a considered
# verdict closes its cycle (the label event's time is the server's, not the
# commit's). Oldest, never newest: a verdict lands on whichever summon Codex
# answers, and anchoring at the first one reads it wherever it lands — after
# the summon, after the halfway re-nudge, or between the two. Codex's own
# activity is deliberately not consulted: a verdict that landed just before a
# re-nudge would otherwise make the re-nudge look like the unanswered one, and
# every resumed poll would filter that verdict out. A summon posted by hand or
# without the marker is not resumable — run plainly to summon.
# The deadline is per call, from now, so the recommended shape on a
# memory-bounded machine — a bounded FOREGROUND call under the harness's tool
# timeout, re-run with --resume until a verdict — is
# `scripts/request_codex_review.sh <PR#> 540` then
# `scripts/request_codex_review.sh <PR#> 540 --resume`, as many times as needed.
# A resumed wait never re-nudges (the summon is on the PR — the operator can
# see it; a fresh summon is a plain run, deliberately).
#
# Usage:
#   scripts/request_codex_review.sh <pr-number> [deadline-seconds] [--resume]
#
# Exit codes: 0 clean (labeled) | 2 findings (read, not labeled)
#             3 timeout/pending (NOT labeled, gate stays red) | 1 usage / unreadable

set -uo pipefail

REPO="linguistic76/skuel"
PR=""
DEADLINE=""
RESUME=0
for arg in "$@"; do
  case "$arg" in
    --resume) RESUME=1 ;;
    *)
      if [[ -z "$PR" ]]; then PR="$arg"
      elif [[ -z "$DEADLINE" ]]; then DEADLINE="$arg"
      else echo "usage: $0 <pr-number> [deadline-seconds] [--resume]" >&2; exit 1
      fi ;;
  esac
done
DEADLINE="${DEADLINE:-1200}"
# Seconds between verdict polls. Overridable for the unit tests only, which
# drive the whole flow against a stubbed gh and cannot afford a real interval.
POLL_INTERVAL="${CODEX_POLL_INTERVAL:-30}"
# Absolute, so every follow-up command this script PRINTS is runnable from the
# caller's cwd — the repo root and app/ both document invoking this script.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Shell-escaped form, for PRINTING only — a copy-pasted command must survive a
# checkout path containing whitespace. Never exec this: %q emits escapes that are
# text, not a filename. Execution sites use "$SCRIPT_DIR/..." quoted directly.
APPLY_CMD=$(printf '%q' "$SCRIPT_DIR/apply_codex_considered.sh")

if [[ -z "$PR" || ! "$PR" =~ ^[0-9]+$ ]]; then
  echo "usage: $0 <pr-number> [deadline-seconds] [--resume]" >&2
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

# --- summon + poll ---------------------------------------------------------

# The status widget's marker (see header): every read of the issue-comment
# channel — verdict count, verdict body, resume anchor — filters on it.
widget='select(.body|test("codex-pull-request-review-summary")|not)'

# The SHA a verdict would be about.
head_sha() {
  gh_retry api "repos/$REPO/pulls/$PR" --jq .head.sha
}

# Prints the summon timestamp; prints nothing on failure (exit inside $(...)
# only leaves the subshell, so callers must check for empty output). The
# comment records the head it asks about — the join key a resumed wait uses.
summon() {
  local since sha
  since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  sha=$(head_sha) && [[ -n "$sha" ]] || { echo "✗ could not read the head sha of #$PR" >&2; return 1; }
  gh_retry api "repos/$REPO/issues/$PR/comments" \
    -f body="@codex review
<!-- codex-summon head=$sha -->" --jq .html_url >/dev/null \
    || { echo "✗ failed to post summon comment" >&2; return 1; }
  echo "$since"
}

# Prints the anchor for a resumed wait: the oldest summon by the authenticated
# user that names the current head, posted after the last `codex-considered`
# labeling (see the header for why the SHA, why oldest, and why Codex's own
# activity plays no part). Prints nothing, with the reason on stderr, when
# there is no summon to resume. Paginated: whole-history reads, not
# since-windows; --paginate emits one value per page, and ISO-8601 Z
# timestamps sort as text.
find_resume_anchor() {
  local login sha labeled summons anchor
  login=$(gh_retry api user --jq .login) || { echo "✗ could not read the authenticated login" >&2; return 1; }
  [[ -n "$login" ]] || { echo "✗ gh reports no login" >&2; return 1; }
  sha=$(head_sha) && [[ -n "$sha" ]] || { echo "✗ could not read the head sha of #$PR" >&2; return 1; }
  labeled=$(gh_retry api --paginate "repos/$REPO/issues/$PR/events?per_page=100" \
    --jq '[.[] | select(.event == "labeled") | select(.label.name == "codex-considered") | .created_at] | max // empty') \
    || { echo "✗ could not read the label history of #$PR" >&2; return 1; }
  labeled=$(sed '/^$/d' <<< "$labeled" | sort | tail -1)
  summons=$(gh_retry api --paginate "repos/$REPO/issues/$PR/comments?per_page=100" \
    --jq ".[] | select(.user.login == \"$login\") | select(.body|test(\"codex-summon head=$sha\")) | .created_at") \
    || { echo "✗ could not list the summons on #$PR" >&2; return 1; }
  anchor=$(sed '/^$/d' <<< "$summons" | sort | awk -v start="$labeled" '$0 > start { print; exit }')
  if [[ -z "$anchor" ]]; then
    echo "✗ no @codex review by $login for the head of #$PR (${sha:0:10}) since the last" >&2
    echo "  codex-considered — nothing to resume; run without --resume to summon" >&2
    return 1
  fi
  echo "  anchor: summon at $anchor for head ${sha:0:10}" >&2
  echo "$anchor"
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
    local printed=0

    # Channel A — REVIEW BODIES. Independent of the inline channel: a finding can
    # arrive in a review body with no inline comment at all. Every channel the
    # branch condition COUNTS must also be PRINTED, or the reader is told findings
    # exist and shown a different set. (Incident: #1301.)
    #
    # Boilerplate-only bodies — the "Here are some automated review suggestions"
    # preamble plus the reviewed-commit line — strip to empty and are skipped, so
    # this section is silent unless Codex wrote something.
    local body_jq bodies
    body_jq='.[] | select(.user.login|test("codex";"i")) | select(.submitted_at > "'"$since"'")'
    body_jq+=' | . as $r | ($r.body'
    # Only the KNOWN boilerplate footer, identified by its summary line — never
    # an arbitrary <details>. Codex wraps supporting evidence in collapsible
    # sections, and stripping those would hide submitted content from the
    # operator, which is the defect this whole function exists to prevent. Same
    # marker .github/workflows/strip-codex-footer.yml matches on.
    body_jq+=' | gsub("(?s)<details>\\s*<summary>[^<]*About Codex in GitHub</summary>.*?</details>"; "")'
    body_jq+=' | gsub("### 💡 Codex Review"; "")'
    body_jq+=' | gsub("Here are some automated review suggestions for this pull request\\."; "")'
    body_jq+=' | gsub("\\*\\*Reviewed commit:\\*\\* `[0-9a-f]+`"; "")'
    body_jq+=' | sub("^\\s+"; "") | sub("\\s+$"; "")) as $b'
    body_jq+=' | select($b | length > 0)'
    body_jq+=' | "── review on " + ($r.commit_id[0:10]) + " ──\n" + $b'
    # rc 4, never an empty string: a failed lookup is not an empty result. Coercing
    # it would print "no findings" over a review that was counted but never read,
    # and invite the label on it. Same rule the count lookups above follow.
    bodies=$(gh_retry api "repos/$REPO/pulls/$PR/reviews?per_page=100" --jq "$body_jq" 2>/dev/null) || return 4
    if [[ -n "${bodies//[[:space:]]/}" ]]; then
      echo "── Codex FINDINGS (review body) ──"
      printf '%s\n' "$bodies"
      printed=1
    fi

    # Channel B — INLINE review comments.
    if (( inline > 0 )); then
      echo "── Codex FINDINGS (inline comments) ──"
      gh_retry api "repos/$REPO/pulls/$PR/comments?since=$since&per_page=100" \
        --jq ".[] | select(.user.login|test(\"codex\";\"i\")) | select(.created_at > \"$since\") | \"\(.path):\(.line // 0)\n\(.body)\n\"" || true
      printed=1
    fi

    # Never print an empty findings section: a review whose body is pure
    # boilerplate and which carries no inline comments is Codex saying nothing,
    # and silence dressed as "FINDINGS" sends the reader looking for content that
    # is not there. Still rc 2 — it needs a human read, and the label is never
    # applied without one.
    if (( printed == 0 )); then
      echo "── Codex submitted ${reviews} review(s) with no findings in body or inline ──"
      echo "   Nothing to address. Read the PR before applying the label."
    fi
    return 2
  fi
  # The status widget (see header) is excluded by its marker on both the count
  # and the body read below — the two must agree or the branch prints a
  # different set than it counted.
  comments=$(gh_retry api "repos/$REPO/issues/$PR/comments?since=$since&per_page=100" \
    --jq "[.[] | select(.user.login|test(\"codex\";\"i\")) | select(.created_at > \"$since\") | $widget] | length" \
    2>/dev/null) || return 4
  [[ "$comments" =~ ^[0-9]+$ ]] || return 4
  if (( comments > 0 )); then
    local body
    body=$(gh_retry api "repos/$REPO/issues/$PR/comments?since=$since&per_page=100" \
      --jq "[.[] | select(.user.login|test(\"codex\";\"i\")) | select(.created_at > \"$since\") | $widget | .body] | join(\"\n\")" || true)
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
# a verdict that lands in the gap is still seen — Codex P2 on #276); a resumed
# wait never re-nudges — its summon is on the PR already, and every re-run
# would otherwise add one more. Returns:
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
           if (( ! RESUME && ! resummoned && elapsed >= DEADLINE / 2 )); then
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

# Everything above is definitions. Sourcing the file (tests/unit/scripts/
# test_request_codex_review.py) stops here, so `check_verdict` can be exercised
# against a stubbed gh without summoning anybody. Executed directly, the flow
# below runs as normal.
[[ "${BASH_SOURCE[0]}" != "$0" ]] && return 0

if (( RESUME )); then
  echo "▶ resuming the wait for Codex on #$PR — no new summon"
  echo "  waiting up to ${DEADLINE}s more; re-run with --resume to keep waiting."
  SINCE=$(find_resume_anchor)
  [[ -n "$SINCE" ]] || exit 1
else
  echo "▶ summoning @codex review on #$PR"
  echo "  waiting up to ${DEADLINE}s — Codex on this repo has taken >13min; patience is in-script by design (portable across harnesses)."
  SINCE=$(summon)
  [[ -n "$SINCE" ]] || exit 1
fi

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
    echo "  Keep waiting WITHOUT a second summon: $0 $PR ${DEADLINE} --resume"
    echo "  (a plain re-run posts a new @codex review). Or check the PR shortly. Apply"
    echo "  codex-considered ONLY after reading a real verdict. If Codex is genuinely"
    echo "  down and you must proceed, that is a deliberate call — add a consideration"
    echo "  note saying so, then: $APPLY_CMD $PR"
    exit 3
    ;;
esac
