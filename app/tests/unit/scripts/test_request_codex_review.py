"""Tests for scripts/request_codex_review.sh — the Codex verdict reader.

Why this file exists
--------------------
Codex delivers findings on two independent surfaces: inline review comments, and
the body of the review object itself. `check_verdict` counted BOTH when deciding
that findings exist, then printed only the inline ones. So a finding that arrived
in a review body was announced as "FINDINGS" and never shown.

That is not hypothetical. On PR #1301 a P1 — the push-time scan was blind to
parentless commits, `git diff-tree` emitting zero bytes without `--root` — lived
only in the body of the review on `a139169db9`, alongside three unrelated inline
comments that printed normally. The reader saw three findings and had no way to
know a fourth existed; it was found later by querying the API by hand. Measured
on that PR: 20 inline comments and 1 body-only finding, across 9 reviews of which
8 carried nothing but boilerplate.

Approach follows test_pre_merge_check.py: a stub `gh` on PATH returns the POST-jq
value each query would yield, and the real script is sourced so `check_verdict`
runs unmodified. That covers the bash state machine — which channel is counted,
which is printed, what the exit code is — which is exactly where this defect
lived. Fidelity of the embedded jq programs is out of scope here; the body-strip
program was verified against the live API responses on #1301 (8 boilerplate
bodies strip to empty, the 1 substantive body survives).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = APP_ROOT / "scripts" / "request_codex_review.sh"

# Dispatch mirrors the script's distinct gh invocations. Order matters: the
# body-extraction jq also contains the word "length" (`select($b | length > 0)`),
# so it is matched on its own marker BEFORE the counting queries.
GH_STUB = """#!/usr/bin/env bash
args="$*"
case "$args" in
  *"auth token"*)        echo "stub-token" ;;
  *"review on"*)         printf '%s' "${STUB_REVIEW_BODIES}" ;;
  *reviews*)             echo "${STUB_REVIEW_COUNT}" ;;
  *pulls*comments*.path*) printf '%s' "${STUB_INLINE_TEXT}" ;;
  *pulls*comments*)      echo "${STUB_INLINE_COUNT}" ;;
  *issues*comments*.body*) printf '%s' "${STUB_ISSUE_BODY}" ;;
  *issues*comments*)     echo "${STUB_ISSUE_COUNT}" ;;
  *) echo "gh stub: unexpected invocation: $args" >&2; exit 64 ;;
esac
"""

SINCE = "2026-09-08T18:35:00Z"


def run_check_verdict(
    tmp_path: Path,
    *,
    review_count: str = "0",
    review_bodies: str = "",
    inline_count: str = "0",
    inline_text: str = "",
    issue_count: str = "0",
    issue_body: str = "",
) -> subprocess.CompletedProcess[str]:
    """Source the real script and run check_verdict against one stubbed PR state."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(GH_STUB)
    gh.chmod(0o755)

    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "STUB_REVIEW_COUNT": review_count,
        "STUB_REVIEW_BODIES": review_bodies,
        "STUB_INLINE_COUNT": inline_count,
        "STUB_INLINE_TEXT": inline_text,
        "STUB_ISSUE_COUNT": issue_count,
        "STUB_ISSUE_BODY": issue_body,
    }
    program = f'source "{SCRIPT}" 1301\ncheck_verdict "{SINCE}"\nexit $?\n'
    return subprocess.run(
        ["bash", "-c", program], capture_output=True, text=True, env=env, check=False
    )


BODY_FINDING = (
    "── review on a139169db9 ──\n"
    "**P1  Include root commits in the push diff**\n"
    "diff-tree emits no patch for a parentless commit without --root."
)
INLINE_FINDING = "app/scripts/git-hooks/secret-scan.sh:106\n**P1  Some inline finding**\n"


class TestReviewBodyChannel:
    """The regression: a finding in a review body must be printed, not just counted."""

    def test_a_body_only_finding_is_printed(self, tmp_path: Path) -> None:
        result = run_check_verdict(
            tmp_path, review_count="1", review_bodies=BODY_FINDING, inline_count="0"
        )
        assert result.returncode == 2, result.stderr
        assert "Include root commits in the push diff" in result.stdout, (
            "a finding delivered in the review body was counted but never shown — "
            f"stdout was:\n{result.stdout}"
        )

    def test_a_body_finding_prints_alongside_inline_ones(self, tmp_path: Path) -> None:
        """The real shape on #1301: one body finding, three inline ones."""
        result = run_check_verdict(
            tmp_path,
            review_count="1",
            review_bodies=BODY_FINDING,
            inline_count="3",
            inline_text=INLINE_FINDING,
        )
        assert result.returncode == 2, result.stderr
        assert "Include root commits in the push diff" in result.stdout
        assert "Some inline finding" in result.stdout

    def test_inline_only_still_prints(self, tmp_path: Path) -> None:
        result = run_check_verdict(
            tmp_path, review_count="0", inline_count="2", inline_text=INLINE_FINDING
        )
        assert result.returncode == 2, result.stderr
        assert "Some inline finding" in result.stdout


class TestNoEmptyFindingsSection:
    """A review carrying nothing must not be announced as findings-with-no-content."""

    def test_boilerplate_only_review_says_so(self, tmp_path: Path) -> None:
        # 8 of 9 reviews on #1301 were this: body strips to empty, no inline comments.
        result = run_check_verdict(tmp_path, review_count="1", review_bodies="", inline_count="0")
        assert result.returncode == 2, result.stderr
        assert "no findings in body or inline" in result.stdout
        assert "── Codex FINDINGS (review body) ──" not in result.stdout
        assert "── Codex FINDINGS (inline comments) ──" not in result.stdout

    def test_whitespace_only_body_counts_as_empty(self, tmp_path: Path) -> None:
        result = run_check_verdict(
            tmp_path, review_count="1", review_bodies="\n  \n", inline_count="0"
        )
        assert result.returncode == 2, result.stderr
        assert "no findings in body or inline" in result.stdout


class TestOtherChannels:
    """The paths this change must not have disturbed."""

    def test_clean_signature_on_the_issue_channel(self, tmp_path: Path) -> None:
        result = run_check_verdict(
            tmp_path,
            issue_count="1",
            issue_body="I didn't find any major issues in this PR.",
        )
        assert result.returncode == 0, result.stderr
        assert "CLEAN" in result.stdout

    def test_an_unrecognized_comment_must_be_read_not_auto_labeled(self, tmp_path: Path) -> None:
        result = run_check_verdict(
            tmp_path,
            issue_count="1",
            issue_body="Committed the changes as `11ed274` and opened a follow-up PR.",
        )
        assert result.returncode == 2, result.stderr
        assert "UNRECOGNIZED" in result.stdout

    def test_nothing_yet_is_pending_not_a_verdict(self, tmp_path: Path) -> None:
        result = run_check_verdict(tmp_path)
        assert result.returncode == 1, result.stderr


class TestScriptShape:
    def test_the_script_is_sourceable_without_summoning(self, tmp_path: Path) -> None:
        """The tests above depend on it, and an accidental removal would summon Codex."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        gh = bin_dir / "gh"
        gh.write_text(GH_STUB)
        gh.chmod(0o755)
        result = subprocess.run(
            ["bash", "-c", f'source "{SCRIPT}" 1301; echo SOURCED-OK'],
            capture_output=True,
            text=True,
            env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
            check=False,
        )
        assert "SOURCED-OK" in result.stdout, result.stderr
        assert "summoning" not in result.stdout

    @pytest.mark.parametrize("channel", ["reviews", "comments"])
    def test_both_verdict_channels_are_read(self, channel: str) -> None:
        """Counting a channel without printing it is the defect this file pins."""
        source = SCRIPT.read_text()
        assert f"pulls/$PR/{channel}" in source
