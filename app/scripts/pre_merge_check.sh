#!/usr/bin/env bash
# Verify a PR is ready to merge: CI Gate green + Codex Review Gate green +
# a review verdict considered on the current head (codex-considered label, or
# a Kody verdict — a review object OR a clean check-run; a clean Kody run
# posts no review object) + no Kody CHANGES_REQUESTED.
#
# Usage: ./dev pre-merge <PR#>
#
# Exit codes: 0 all checks passed | 1 one or more checks failed

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PR="${1:-}"
if [[ -z "$PR" || ! "$PR" =~ ^[0-9]+$ ]]; then
  echo "Usage: ./dev pre-merge <PR#>" >&2
  exit 1
fi

REPO="linguistic76/skuel"
failed=0

echo ""
echo "Pre-merge check: PR #${PR}"
echo "=============================="

SHA=$(gh pr view "$PR" --json headRefOid -q '.headRefOid' 2>/dev/null || echo "")
if [[ -z "$SHA" ]]; then
  echo -e "${RED}✗ Could not fetch PR #${PR} — is it open?${NC}" >&2
  exit 1
fi

# 1. CI Gate (check-run, required)
echo ""
echo "1. CI Gate..."
CI_GATE=$(gh api "repos/${REPO}/commits/${SHA}/check-runs" \
  --jq '[.check_runs[] | select(.name == "CI Gate")] | first | .conclusion // "pending"' \
  2>/dev/null || echo "error")
if [[ "$CI_GATE" == "success" ]]; then
  echo -e "   ${GREEN}✓ CI Gate: success${NC}"
elif [[ "$CI_GATE" == "pending" || "$CI_GATE" == "null" ]]; then
  echo -e "   ${YELLOW}⚠ CI Gate: still running${NC}"
  failed=1
else
  echo -e "   ${RED}✗ CI Gate: ${CI_GATE}${NC}"
  failed=1
fi

# 2. Codex Review Gate (commit status, required)
echo ""
echo "2. Codex Review Gate..."
CODEX_GATE=$(gh api "repos/${REPO}/commits/${SHA}/statuses" \
  --jq '[.[] | select(.context == "Codex Review Gate")] | first | .state // "pending"' \
  2>/dev/null || echo "error")
if [[ "$CODEX_GATE" == "success" ]]; then
  echo -e "   ${GREEN}✓ Codex Review Gate: success${NC}"
elif [[ "$CODEX_GATE" == "failure" ]]; then
  # Distinguish "not summoned on Python PR" from "summoned but not considered"
  LABELS=$(gh pr view "$PR" --json labels -q '[.labels[].name] | join(",")' 2>/dev/null || echo "")
  if echo "$LABELS" | grep -q "codex-considered"; then
    echo -e "   ${YELLOW}⚠ Codex Review Gate: failure but codex-considered is set (label may be stale)${NC}"
    failed=1
  else
    echo -e "   ${RED}✗ Codex Review Gate: failure — run: scripts/request_codex_review.sh ${PR}${NC}"
    failed=1
  fi
else
  echo -e "   ${YELLOW}⚠ Codex Review Gate: ${CODEX_GATE}${NC}"
  failed=1
fi

# Kody's completion signal, anchored to the current head like checks 1-2.
# A CLEAN Kody run posts NO review object — its check-run conclusion is the
# only completion evidence (measured 2026-08-31: ran clean = `success`,
# never summoned = `skipped`). Matched on app.slug, the identity that cannot
# drift with a display-name rename; ABSENT = no kody-ai check-run on this
# commit at all; PENDING = run exists but has not concluded.
KODY_RUN=$(gh api "repos/${REPO}/commits/${SHA}/check-runs" \
  --jq '[.check_runs[] | select(.app.slug == "kody-ai")] | if length == 0 then "ABSENT" else (last | .conclusion // "PENDING") end' \
  2>/dev/null || echo "UNKNOWN")

# 3. Review considered: codex-considered label OR a Kody verdict. Merge-policy
#    condition 2 (PR_WORKFLOW.md § Merge policy) accepts either reviewer; the
#    Codex Review Gate (check 2) still hard-requires Codex on Python-touching
#    PRs, so the Kody alternative only ever clears docs/tooling-only PRs.
echo ""
echo "3. Review considered (codex-considered label or Kody verdict)..."
LABELS=$(gh pr view "$PR" --json labels -q '[.labels[].name] | join(",")' 2>/dev/null || echo "")
if echo "$LABELS" | grep -q "codex-considered"; then
  echo -e "   ${GREEN}✓ codex-considered label is set${NC}"
else
  # Exact bot identity + anchored to the current head: a review from any other
  # account, or from before the latest push, must not clear the alternative.
  # per_page=100: the reviews endpoint pages at 30 ascending and has no `since`,
  # so a fresh verdict on a review-heavy PR can sit beyond page 1 (same
  # constraint documented in request_codex_review.sh).
  ALT_KODY=$(gh api "repos/${REPO}/pulls/${PR}/reviews?per_page=100" \
    --jq "[.[] | select(.user.login == \"kody-ai[bot]\") | select(.commit_id == \"${SHA}\")] | last | .state // \"NOT_SUMMONED\"" \
    2>/dev/null || echo "UNKNOWN")
  if [[ "$ALT_KODY" != "NOT_SUMMONED" && "$ALT_KODY" != "UNKNOWN" ]]; then
    echo -e "   ${GREEN}✓ no codex-considered, but a Kody verdict on the current head exists (${ALT_KODY}) — accepted per the Codex-or-Kody policy${NC}"
  elif [[ "$KODY_RUN" == "success" ]]; then
    # No review object, but the check-run passed: Kody ran and had nothing
    # blocking. That IS the verdict. Only `success` clears — `skipped` means
    # never summoned, and `failure` is Kody's own error, not a verdict.
    echo -e "   ${GREEN}✓ no codex-considered, but Kody ran clean on the current head (check-run success; a clean run posts no review object) — accepted per the Codex-or-Kody policy${NC}"
  else
    echo -e "   ${RED}✗ neither codex-considered nor a Kody verdict — run scripts/request_codex_review.sh ${PR} or post @kody start-review${NC}"
    failed=1
  fi
fi

# 4. Kody review state (no CHANGES_REQUESTED). Blocking is review-only; when
#    no review object exists, the check-run (fetched above) distinguishes
#    "ran clean" from "never summoned" — a clean run posts no review.
echo ""
echo "4. Kody review..."
KODY_STATE=$(gh pr view "$PR" --json reviews \
  -q '[.reviews[] | select(.author.login | test("kody";"i"))] | last | .state // "NOT_SUMMONED"' \
  2>/dev/null || echo "UNKNOWN")
if [[ "$KODY_STATE" == "CHANGES_REQUESTED" ]]; then
  echo -e "   ${RED}✗ Kody has CHANGES_REQUESTED — address findings, then re-summon: @kody start-review${NC}"
  failed=1
elif [[ "$KODY_STATE" != "NOT_SUMMONED" && "$KODY_STATE" != "UNKNOWN" ]]; then
  echo -e "   ${GREEN}✓ Kody: ${KODY_STATE}${NC}"
elif [[ "$KODY_RUN" == "success" ]]; then
  echo -e "   ${GREEN}✓ Kody ran clean on the current head (check-run success; a clean run posts no review object)${NC}"
elif [[ "$KODY_RUN" == "PENDING" ]]; then
  echo -e "   ${YELLOW}⚠ Kody review in progress on the current head${NC}"
elif [[ "$KODY_RUN" == "skipped" || "$KODY_RUN" == "ABSENT" ]]; then
  echo -e "   ${YELLOW}⚠ Kody not yet summoned — post @kody start-review for non-trivial PRs${NC}"
else
  echo -e "   ${YELLOW}⚠ Kody signal unclear (check-run: ${KODY_RUN}, review: ${KODY_STATE}) — verify manually${NC}"
fi

echo ""
echo "=============================="
if [[ $failed -eq 1 ]]; then
  echo -e "${RED}✗ Not ready to merge. Resolve the failures above first.${NC}"
  exit 1
else
  echo -e "${GREEN}✓ Ready to merge:${NC}"
  echo "  gh pr merge ${PR} --squash --delete-branch"
  exit 0
fi
