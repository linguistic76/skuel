"""Tests for the shared YAML frontmatter parser (core/utils/frontmatter.py)."""

from __future__ import annotations

from core.utils.frontmatter import parse_frontmatter, split_frontmatter


class TestParseFrontmatter:
    def test_frontmatter_with_body(self):
        fm, body = parse_frontmatter("---\ntitle: t\ntags: [a]\n---\nbody text")
        assert fm == {"title": "t", "tags": ["a"]}
        assert body == "body text"

    def test_frontmatter_only_ending_at_eof(self):
        """Frontmatter-only file with NO trailing newline after the closing fence.

        The natural shape for `action: approve` teacher report files (Codex #650
        P3) — the closing `---` at EOF must still terminate the block.
        """
        fm, body = parse_frontmatter("---\nsubmission_uid: x\naction: approve\n---")
        assert fm == {"submission_uid": "x", "action": "approve"}
        assert body == ""

    def test_frontmatter_only_with_trailing_newline(self):
        fm, body = parse_frontmatter("---\nsubmission_uid: x\n---\n")
        assert fm == {"submission_uid": "x"}
        assert body == ""

    def test_no_frontmatter_passes_through(self):
        fm, body = parse_frontmatter("just body")
        assert fm == {}
        assert body == "just body"

    def test_horizontal_rule_in_body_not_consumed(self):
        fm, body = parse_frontmatter("---\ntitle: t\n---\nabove\n\n---\n\nbelow")
        assert fm == {"title": "t"}
        assert body == "above\n\n---\n\nbelow"

    def test_yaml_error_returns_whole_content(self):
        content = "---\n: [unclosed\n---\nbody"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == content


class TestSplitFrontmatter:
    def test_returns_raw_yaml_text(self):
        raw, body = split_frontmatter("---\ntitle: t\n---\nbody")
        assert raw == "title: t"
        assert body == "body"

    def test_no_frontmatter_returns_none(self):
        raw, body = split_frontmatter("plain content")
        assert raw is None
        assert body == "plain content"
