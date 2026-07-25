#!/usr/bin/env bash
# Verify a PR is ready to merge: CI Gate green + Codex Review Gate green +
# codex-considered label set + no Kody CHANGES_REQUESTED.
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

# 3. codex-considered label
echo ""
echo "3. codex-considered label..."
LABELS=$(gh pr view "$PR" --json labels -q '[.labels[].name] | join(",")' 2>/dev/null || echo "")
if echo "$LABELS" | grep -q "codex-considered"; then
  echo -e "   ${GREEN}✓ codex-considered label is set${NC}"
else
  echo -e "   ${RED}✗ codex-considered label missing — run: scripts/request_codex_review.sh ${PR}${NC}"
  failed=1
fi

# 4. Kody review state (no CHANGES_REQUESTED)
echo ""
echo "4. Kody review..."
KODY_STATE=$(gh pr view "$PR" --json reviews \
  -q '[.reviews[] | select(.author.login | test("kody";"i"))] | last | .state // "NOT_SUMMONED"' \
  2>/dev/null || echo "UNKNOWN")
if [[ "$KODY_STATE" == "CHANGES_REQUESTED" ]]; then
  echo -e "   ${RED}✗ Kody has CHANGES_REQUESTED — address findings, then re-summon: @kody start-review${NC}"
  failed=1
elif [[ "$KODY_STATE" == "NOT_SUMMONED" ]]; then
  echo -e "   ${YELLOW}⚠ Kody not yet summoned — post @kody start-review for non-trivial PRs${NC}"
else
  echo -e "   ${GREEN}✓ Kody: ${KODY_STATE}${NC}"
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
