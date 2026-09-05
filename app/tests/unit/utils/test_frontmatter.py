"""Tests for the shared YAML frontmatter parser (core/utils/frontmatter.py)."""

from __future__ import annotations

from core.utils.frontmatter import parse_frontmatter, split_frontmatter
from core.utils.result_simplified import ErrorCategory


def _ok(content: str) -> tuple[dict, str]:
    """Unwrap the success path — parse_frontmatter returns Result now."""
    result = parse_frontmatter(content)
    assert result.is_ok, result.expect_error().display_message
    return result.value


class TestParseFrontmatter:
    def test_frontmatter_with_body(self):
        fm, body = _ok("---\ntitle: t\ntags: [a]\n---\nbody text")
        assert fm == {"title": "t", "tags": ["a"]}
        assert body == "body text"

    def test_frontmatter_only_ending_at_eof(self):
        """Frontmatter-only file with NO trailing newline after the closing fence.

        The natural shape for `action: approve` teacher report files (Codex #650
        P3) — the closing `---` at EOF must still terminate the block.
        """
        fm, body = _ok("---\nsubmission_uid: x\naction: approve\n---")
        assert fm == {"submission_uid": "x", "action": "approve"}
        assert body == ""

    def test_frontmatter_only_with_trailing_newline(self):
        fm, body = _ok("---\nsubmission_uid: x\n---\n")
        assert fm == {"submission_uid": "x"}
        assert body == ""

    def test_no_frontmatter_passes_through(self):
        fm, body = _ok("just body")
        assert fm == {}
        assert body == "just body"

    def test_horizontal_rule_in_body_not_consumed(self):
        fm, body = _ok("---\ntitle: t\n---\nabove\n\n---\n\nbelow")
        assert fm == {"title": "t"}
        assert body == "above\n\n---\n\nbelow"

    def test_a_broken_fence_fails_instead_of_returning_empty(self):
        """The bug this contract removes: a broken fence used to be
        indistinguishable from a plain note, so callers reported a wrong reason
        for it and mutating scripts rewrote over it."""
        result = parse_frontmatter("---\n: [unclosed\n---\nbody")
        assert result.is_error
        assert result.expect_error().category is ErrorCategory.VALIDATION

    def test_the_failure_names_the_author_s_line_not_yaml_s_offset(self):
        # File line 4 is `- stray`; YAML alone would say 3, never having seen
        # the opening fence.
        result = parse_frontmatter("---\ncontent: |\n\n- stray\n\n  body\n---\nb")
        assert "line 4" in result.expect_error().display_message

    def test_no_fence_is_still_a_plain_note_not_an_error(self):
        result = parse_frontmatter("# just a note\n\nno frontmatter")
        assert result.is_ok
        assert result.value[0] == {}


class TestSplitFrontmatter:
    def test_returns_raw_yaml_text(self):
        raw, body = split_frontmatter("---\ntitle: t\n---\nbody")
        assert raw == "title: t"
        assert body == "body"

    def test_no_frontmatter_returns_none(self):
        raw, body = split_frontmatter("plain content")
        assert raw is None
        assert body == "plain content"
