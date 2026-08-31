"""
Tests for scripts/pre_merge_check.sh (the ./dev pre-merge gate)
===============================================================

First shell-script test in the repo — merge-gating logic previously had zero
coverage, and a gate that stops gating fails silently by construction.

Approach: a stub `gh` on PATH returns the POST-jq value each query would
yield, keyed on the invocation's arguments; the real script runs unmodified
via subprocess. That covers the bash state machine (which conclusion clears
which check, exit codes, message truth) — the one place the clean-Kody-run
defect lived. Fidelity of the embedded jq programs themselves is out of
scope here; those are anchored to API responses measured 2026-08-31
(provenance: PR #1203's description):

- Kody ran clean  → check-run `Kody Code Review` conclusion `success`,
  app.slug `kody-ai`, and NO review object posted.
- never summoned  → same check-run, conclusion `skipped`.
"""

import os
import subprocess
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = APP_ROOT / "scripts" / "pre_merge_check.sh"

# Dispatch mirrors the script's five distinct gh invocations. Order matters:
# both check-run queries share an endpoint, so the CI Gate jq text is matched
# before the generic check-runs fallback (the Kody app.slug query).
GH_STUB = """#!/usr/bin/env bash
args="$*"
case "$args" in
  *headRefOid*)     echo "${STUB_SHA}" ;;
  *"--json labels"*)  echo "${STUB_LABELS}" ;;
  *"--json reviews"*) echo "${STUB_KODY_REVIEW}" ;;
  *"per_page=100"*)   echo "${STUB_KODY_REVIEW}" ;;
  *"CI Gate"*)        echo "${STUB_CI_GATE}" ;;
  *check-runs*)       echo "${STUB_KODY_RUN}" ;;
  *statuses*)         echo "${STUB_CODEX_GATE}" ;;
  *) echo "gh stub: unexpected invocation: $args" >&2; exit 64 ;;
esac
"""


def run_pre_merge(
    tmp_path: Path,
    *,
    kody_run: str,
    kody_review: str = "NOT_SUMMONED",
    labels: str = "",
    ci_gate: str = "success",
    codex_gate: str = "success",
) -> subprocess.CompletedProcess[str]:
    """Run the real script with a stubbed gh describing one PR state."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(GH_STUB)
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "STUB_SHA": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "STUB_LABELS": labels,
        "STUB_KODY_REVIEW": kody_review,
        "STUB_CI_GATE": ci_gate,
        "STUB_KODY_RUN": kody_run,
        "STUB_CODEX_GATE": codex_gate,
    }
    return subprocess.run(
        ["bash", str(SCRIPT), "999"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_clean_kody_run_without_label_passes(tmp_path: Path) -> None:
    """The previously-impossible case: check-run success + no review + no
    label must exit 0, with check 3 naming the Kody verdict (acceptance 1)."""
    result = run_pre_merge(tmp_path, kody_run="success")
    assert result.returncode == 0, result.stdout
    assert "Kody ran clean on the current head" in result.stdout
    assert "not yet summoned" not in result.stdout
    assert "Ready to merge" in result.stdout


def test_skipped_check_run_still_fails(tmp_path: Path) -> None:
    """RED check for the inversion trap: `skipped` means never summoned and
    must NOT clear check 3 (acceptance 2)."""
    result = run_pre_merge(tmp_path, kody_run="skipped")
    assert result.returncode == 1, result.stdout
    assert "neither codex-considered nor a Kody verdict" in result.stdout
    assert "Kody not yet summoned" in result.stdout


def test_changes_requested_still_blocks(tmp_path: Path) -> None:
    """A blocking review keeps failing check 4 even though the review object
    itself satisfies check 3's verdict question (acceptance 3)."""
    result = run_pre_merge(tmp_path, kody_run="success", kody_review="CHANGES_REQUESTED")
    assert result.returncode == 1, result.stdout
    assert "Kody has CHANGES_REQUESTED" in result.stdout
    # The verdict WAS obtained — check 3 must not be the failing check.
    assert "neither codex-considered nor a Kody verdict" not in result.stdout


@pytest.mark.parametrize("conclusion", ["failure", "ABSENT", "PENDING", "UNKNOWN"])
def test_non_success_conclusions_are_not_verdicts(tmp_path: Path, conclusion: str) -> None:
    """Kody's own error / absence / an unconcluded run must not read as
    "considered" (plan trap 4)."""
    result = run_pre_merge(tmp_path, kody_run=conclusion)
    assert result.returncode == 1, result.stdout
    assert "neither codex-considered nor a Kody verdict" in result.stdout


def test_codex_considered_label_clears_check_3(tmp_path: Path) -> None:
    """The label branch is untouched: it clears check 3 by itself, and check
    4's not-summoned state stays a cosmetic warning, not a failure."""
    result = run_pre_merge(tmp_path, kody_run="skipped", labels="codex-considered")
    assert result.returncode == 0, result.stdout
    assert "codex-considered label is set" in result.stdout
    assert "Kody not yet summoned" in result.stdout
