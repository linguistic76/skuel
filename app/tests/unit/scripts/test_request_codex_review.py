"""Tests for scripts/request_codex_review.sh — the Codex verdict reader.

The invariant these pin
-----------------------
Codex delivers findings on two independent surfaces: inline (line-anchored)
review comments, and the body of the review object itself. One review can carry
both, or only the body. So:

1. Every channel the verdict COUNTS is also PRINTED. Counting one and printing
   another announces findings the reader cannot see, which is worse than not
   reading the channel at all — there is no signal that anything is missing.
2. A failed lookup is not an empty result. An unreadable channel returns rc 4 so
   polling continues; coercing it to "" would report "no findings" over a review
   nobody read, and invite the label on it.
3. A review with nothing in either surface says so, and still returns rc 2. An
   unread review is not a clean verdict, and the label needs one.

(Incident that motivated 1 and 2: #1301.)

Approach follows test_pre_merge_check.py: a stub `gh` on PATH returns the POST-jq
value each query would yield, and the real script is sourced so `check_verdict`
runs unmodified. That covers the bash state machine — which channel is counted,
which is printed, what the exit code is — which is the layer these invariants
live in. Fidelity of the embedded jq programs is out of scope here; the
body-strip program is anchored to API responses measured on #1301, where 8 of 9
review bodies were pure boilerplate and stripped to empty while the 1 substantive
body survived.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = APP_ROOT / "scripts" / "request_codex_review.sh"

# Dispatch mirrors the script's distinct gh invocations. Order matters: the
# body-extraction jq also contains the word "length" (`select($b | length > 0)`),
# so it is matched on its own marker BEFORE the counting queries. The issue-channel
# BODY read is told apart from its COUNT by `join(` — both of those programs name
# `.body` (the status-widget filter), so `.body` is not a separator.
GH_STUB = """#!/usr/bin/env bash
args="$*"
# STUB_FAIL_MATCH names a substring of the invocation that must fail after
# retries, so an unreadable channel can be distinguished from an empty one.
if [[ -n "${STUB_FAIL_MATCH:-}" && "$args" == *"${STUB_FAIL_MATCH}"* ]]; then
  echo "stub: simulated API failure" >&2
  exit 1
fi
# Every POST (a summon, a consideration note) is recorded, so a test can assert
# what the script wrote to the PR — a resumed wait must write no summon.
if [[ "$args" == *"-f body="* ]]; then
  printf '%s\n' "$args" >> "${STUB_POST_LOG:-/dev/null}"
  echo "https://example.invalid/comment"
  exit 0
fi
case "$args" in
  *"auth token"*)        echo "stub-token" ;;
  *"api user"*)          echo "${STUB_LOGIN:-linguistic76}" ;;
  # The resume anchor's whole-history reads: the head commit's date, the last
  # codex-considered labeling, the summons by the user.
  *pulls*commits*)       printf '%s' "${STUB_HEAD_DATE}" ;;
  *issues*events*)       printf '%s' "${STUB_LABELED}" ;;
  *'test("@codex review")'*) printf '%s' "${STUB_SUMMONS}" ;;
  *"review on"*)         printf '%s' "${STUB_REVIEW_BODIES}" ;;
  *reviews*)             echo "${STUB_REVIEW_COUNT}" ;;
  *pulls*comments*.path*) printf '%s' "${STUB_INLINE_TEXT}" ;;
  *pulls*comments*)      echo "${STUB_INLINE_COUNT}" ;;
  *issues*comments*join*) printf '%s' "${STUB_ISSUE_BODY}" ;;
  *issues*comments*)     echo "${STUB_ISSUE_COUNT}" ;;
  *) echo "gh stub: unexpected invocation: $args" >&2; exit 64 ;;
esac
"""

SINCE = "2026-09-08T18:35:00Z"


def _stub_env(
    tmp_path: Path,
    *,
    review_count: str = "0",
    review_bodies: str = "",
    inline_count: str = "0",
    inline_text: str = "",
    issue_count: str = "0",
    issue_body: str = "",
    fail_match: str = "",
    summons: str = "",
    head_date: str = "",
    labeled: str = "",
) -> dict[str, str]:
    """Install the gh stub on PATH and describe one PR state to it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(GH_STUB)
    gh.chmod(0o755)
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "STUB_REVIEW_COUNT": review_count,
        "STUB_REVIEW_BODIES": review_bodies,
        "STUB_INLINE_COUNT": inline_count,
        "STUB_INLINE_TEXT": inline_text,
        "STUB_ISSUE_COUNT": issue_count,
        "STUB_ISSUE_BODY": issue_body,
        "STUB_FAIL_MATCH": fail_match,
        "STUB_SUMMONS": summons,
        "STUB_HEAD_DATE": head_date,
        "STUB_LABELED": labeled,
        "STUB_POST_LOG": str(tmp_path / "posts.log"),
    }


def run_check_verdict(
    tmp_path: Path,
    *,
    review_count: str = "0",
    review_bodies: str = "",
    inline_count: str = "0",
    inline_text: str = "",
    issue_count: str = "0",
    issue_body: str = "",
    fail_match: str = "",
) -> subprocess.CompletedProcess[str]:
    """Source the real script and run check_verdict against one stubbed PR state."""
    env = _stub_env(
        tmp_path,
        review_count=review_count,
        review_bodies=review_bodies,
        inline_count=inline_count,
        inline_text=inline_text,
        issue_count=issue_count,
        issue_body=issue_body,
        fail_match=fail_match,
    )
    program = f'source "{SCRIPT}" 1301\ncheck_verdict "{SINCE}"\nexit $?\n'
    return subprocess.run(
        ["bash", "-c", program], capture_output=True, text=True, env=env, check=False
    )


def run_find_resume_anchor(
    tmp_path: Path,
    *,
    summons: str,
    head_date: str = "",
    labeled: str = "",
) -> subprocess.CompletedProcess[str]:
    """Source the real script and run find_resume_anchor against one stubbed PR history."""
    env = _stub_env(tmp_path, summons=summons, head_date=head_date, labeled=labeled)
    program = f'source "{SCRIPT}" 1301\nfind_resume_anchor\nexit $?\n'
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


class TestUnreadableChannelIsNotEmpty:
    """rc 4, so the caller keeps polling — never "no findings" over an unread review."""

    def test_a_failed_review_body_fetch_returns_rc4(self, tmp_path: Path) -> None:
        result = run_check_verdict(
            tmp_path,
            review_count="1",
            review_bodies=BODY_FINDING,
            inline_count="0",
            fail_match="review on",  # only the body-extraction call fails
        )
        assert result.returncode == 4, (
            "an unreadable review-body channel was treated as empty — the operator "
            f"would be told there is nothing to address:\n{result.stdout}"
        )
        assert "no findings in body or inline" not in result.stdout

    def test_a_failed_count_lookup_still_returns_rc4(self, tmp_path: Path) -> None:
        """The pre-existing guard on the counting queries, unchanged by this file."""
        result = run_check_verdict(tmp_path, fail_match="reviews?per_page")
        assert result.returncode == 4, result.stdout


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


class TestBoilerplateStripIsTargeted:
    """Only the known footer may be stripped from a review body.

    Source-level, deliberately: the strip lives in a jq program that `gh` runs,
    and there is no jq engine on the machine to drive it offline — a Python
    reimplementation would test a different regex engine and prove nothing. The
    behaviour that IS reachable was verified against the live API (8 boilerplate
    bodies on #1301 strip to empty, the 1 substantive body survives); what this
    pins is the property that makes the strip safe in general.
    """

    def test_only_the_named_footer_is_stripped(self) -> None:
        source = SCRIPT.read_text()
        assert "About Codex in GitHub</summary>" in source, (
            "the <details> strip must identify the boilerplate footer by its summary "
            "line — the same marker .github/workflows/strip-codex-footer.yml uses"
        )
        assert 'gsub("(?s)<details>.*?</details>"' not in source, (
            "an unrestricted <details> strip deletes any collapsible section Codex "
            "wrote, including supporting evidence — hiding submitted content is the "
            "defect this function exists to prevent."
        )


class TestStatusWidgetIsNeverAVerdict:
    """Codex's review-status widget is pending, never a verdict.

    Source-level for the same reason as the strip test: the filter lives in the
    jq programs `gh` runs. What it pins is the shape that makes the rule safe —
    the widget is excluded by its marker from BOTH the issue-channel count and
    the body read, because a channel counted on one set and printed on another
    is the #1301 defect in a new coat.
    """

    MARKER = "codex-pull-request-review-summary"

    def test_widget_is_filtered_from_count_and_body_alike(self) -> None:
        source = SCRIPT.read_text()
        assert f'select(.body|test("{self.MARKER}")|not)' in source, (
            "the widget must be excluded by its HTML-comment marker, not by its "
            "wording — the table text changes as the review runs"
        )
        lines = source.splitlines()
        # Each read is a two-line statement: the URL line, then its `--jq` continuation.
        reads = [
            f"{lines[i].strip()} {lines[i + 1].strip()}"
            for i, line in enumerate(lines)
            if "issues/$PR/comments?since=" in line
        ]
        assert len(reads) == 2, reads
        for statement in reads:
            assert "$widget" in statement, (
                f"the widget filter must sit on every issue-channel read: {statement}"
            )


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


HEAD_1 = "2026-09-17T13:50:00Z"
SUMMON_1 = "2026-09-17T14:00:00Z"
RENUDGE_1 = "2026-09-17T14:10:00Z"
OLD_SUMMON = "2026-09-16T09:00:00Z"
OLD_LABELED = "2026-09-16T09:20:00Z"


class TestResumeAnchor:
    """A resumed wait anchors at the oldest summon of the current cycle — and posts no new one."""

    def test_one_summon_is_the_anchor(self, tmp_path: Path) -> None:
        result = run_find_resume_anchor(tmp_path, summons=SUMMON_1, head_date=HEAD_1)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == SUMMON_1
        assert f"cycle began {HEAD_1}" in result.stderr

    def test_the_first_summon_wins_over_its_renudge(self, tmp_path: Path) -> None:
        """The verdict lands on whichever summon Codex answers — after the summon,
        after the re-nudge, or between the two. Only the oldest anchor reads all three;
        the killed wait's history can be summon → verdict → re-nudge, and an anchor at
        the re-nudge would filter that verdict out of every resumed poll."""
        result = run_find_resume_anchor(
            tmp_path, summons=f"{RENUDGE_1}\n{SUMMON_1}\n", head_date=HEAD_1
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == SUMMON_1

    def test_a_previous_cycle_is_closed_by_its_label(self, tmp_path: Path) -> None:
        result = run_find_resume_anchor(
            tmp_path,
            summons=f"{OLD_SUMMON}\n{SUMMON_1}\n",
            head_date="2026-09-15T08:00:00Z",
            labeled=OLD_LABELED,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == SUMMON_1

    def test_a_previous_cycle_is_closed_by_a_push(self, tmp_path: Path) -> None:
        """The gate strips the label on every push: a summon older than the head
        reviewed other code and is not this cycle's."""
        result = run_find_resume_anchor(
            tmp_path, summons=f"{OLD_SUMMON}\n{SUMMON_1}\n", head_date=HEAD_1
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == SUMMON_1

    def test_a_considered_cycle_has_nothing_to_resume(self, tmp_path: Path) -> None:
        result = run_find_resume_anchor(
            tmp_path, summons=SUMMON_1, head_date=HEAD_1, labeled="2026-09-17T14:30:00Z"
        )
        assert result.returncode == 1
        assert result.stdout.strip() == ""
        assert "nothing to resume" in result.stderr

    def test_a_summon_older_than_the_head_has_nothing_to_resume(self, tmp_path: Path) -> None:
        result = run_find_resume_anchor(tmp_path, summons=OLD_SUMMON, head_date=HEAD_1)
        assert result.returncode == 1
        assert "nothing to resume" in result.stderr

    def test_no_summon_is_an_error_not_a_summon(self, tmp_path: Path) -> None:
        result = run_find_resume_anchor(tmp_path, summons="", head_date=HEAD_1)
        assert result.returncode == 1
        assert result.stdout.strip() == ""
        assert "nothing to resume" in result.stderr
        assert not (tmp_path / "posts.log").exists(), "a missing anchor must never summon"


class TestResumedRun:
    """The whole flow with --resume: no summon is posted, the verdict is read."""

    def _run(self, tmp_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        env = {**env, "CODEX_POLL_INTERVAL": "1"}
        return subprocess.run(
            ["bash", str(SCRIPT), "1301", "2", "--resume"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_a_resumed_wait_posts_no_summon_and_reads_the_findings(self, tmp_path: Path) -> None:
        env = _stub_env(
            tmp_path,
            summons=SUMMON_1,
            head_date=HEAD_1,
            review_count="1",
            review_bodies=BODY_FINDING,
        )
        result = self._run(tmp_path, env)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "Include root commits in the push diff" in result.stdout
        assert "resuming the wait" in result.stdout
        assert not (tmp_path / "posts.log").exists(), (
            f"a resumed wait posted to the PR: {(tmp_path / 'posts.log').read_text()}"
        )

    def test_a_resumed_wait_never_renudges(self, tmp_path: Path) -> None:
        """A 2 s deadline with a 1 s poll passes the halfway mark; a plain run would nudge."""
        env = _stub_env(tmp_path, summons=SUMMON_1, head_date=HEAD_1)
        result = self._run(tmp_path, env)
        assert result.returncode == 3, result.stdout + result.stderr
        assert not (tmp_path / "posts.log").exists(), "the resumed wait re-summoned"
        assert "--resume" in result.stdout, "the timeout message must name the resume path"

    def test_a_plain_run_still_summons_and_renudges(self, tmp_path: Path) -> None:
        """The control: without --resume the flow posts the summon (and its nudge)."""
        env = {**_stub_env(tmp_path), "CODEX_POLL_INTERVAL": "1"}
        result = subprocess.run(
            ["bash", str(SCRIPT), "1301", "2"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert result.returncode == 3, result.stdout + result.stderr
        posts = (tmp_path / "posts.log").read_text().splitlines()
        assert len(posts) == 2, posts
        assert all("@codex review" in post for post in posts)
