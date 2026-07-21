"""Tests for UID generation utilities (core/utils/uid_generator.py).

Locks the semantics of the consolidated slugify: the former
hierarchy_parser copy stripped markdown links before slugging and the
UIDGenerator copy did not — the merge deliberately adopted link
stripping (plain text is unaffected; links slug to their link text).
"""

from __future__ import annotations

from core.utils.uid_generator import UIDGenerator


class TestSlugify:
    def test_plain_text(self):
        assert UIDGenerator.slugify("Meditation Basics") == "meditation-basics"

    def test_special_characters_removed(self):
        assert UIDGenerator.slugify("What's Next? (Part 2)") == "whats-next-part-2"

    def test_whitespace_and_hyphen_runs_collapse(self):
        assert UIDGenerator.slugify("  a  --  b  ") == "a-b"

    def test_markdown_link_slugs_to_link_text(self):
        """Adopted from hierarchy_parser: URL characters never leak into the slug."""
        assert UIDGenerator.slugify("[Foo Bar](https://example.com/x)") == "foo-bar"

    def test_markdown_link_inline_with_text(self):
        assert UIDGenerator.slugify("See [the docs](https://d.io) here") == "see-the-docs-here"

    def test_empty_string(self):
        assert UIDGenerator.slugify("") == ""


class TestGenerateUid:
    def test_semantic_uid_uses_slug(self):
        uid = UIDGenerator.generate_uid("task", "Implement Auth!")
        assert uid.startswith("task_implement-auth_")
        assert len(uid.rsplit("_", 1)[1]) == 8

    def test_random_uid_without_name(self):
        uid = UIDGenerator.generate_uid("er")
        prefix, suffix = uid.split("_", 1)
        assert prefix == "er"
        assert len(suffix) == 8
