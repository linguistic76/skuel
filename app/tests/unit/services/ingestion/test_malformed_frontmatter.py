"""A frontmatter fence that does not parse is an authoring error, not a loose note.

``parse_markdown`` used to swallow ``yaml.YAMLError`` into empty frontmatter and
return ok, which made a broken file indistinguishable from a deliberate untyped
note: the ingest gate set it aside as "no ``type:`` field", the entity behind it
went stale unreported, and a later rename deleted that entity because no
collectible file claimed its uid any more. These tests pin the distinction that
resolves it — absence of a fence vs. a fence that is broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.services.ingestion.detector import is_non_entity_note
from core.services.ingestion.parser import parse_markdown, parse_yaml
from core.utils.result_simplified import ErrorCategory

# The shape that actually occurred in the content vault: a column-0 line inside a
# `content: |` block scalar breaks out of the block, and YAML then reads a bare
# sequence item at mapping level.
BROKEN_BLOCK_SCALAR = (
    "---\n"
    "type: PathStep\n"
    "uid: ps.sel.example\n"
    "content: |\n"
    "\n"
    "- stray note at column 0\n"
    "\n"
    "  ## Real body\n"
    "---\n"
    "body\n"
)


class TestNoFenceStillSucceeds:
    """Absence of a fence is a loose note — the behaviour that must NOT change."""

    def test_no_frontmatter_parses_to_empty_and_succeeds(self, tmp_path: Path) -> None:
        path = tmp_path / "loose.md"
        path.write_text("# just a note\n\nno frontmatter at all\n")
        result = parse_markdown(path)
        assert result.is_ok
        frontmatter, body = result.value
        assert frontmatter == {}
        assert "just a note" in body

    def test_a_loose_note_is_still_set_aside(self, tmp_path: Path) -> None:
        path = tmp_path / "loose.md"
        path.write_text("# just a note\n")
        assert is_non_entity_note(path) is True

    def test_a_parsing_fence_without_type_is_still_set_aside(self, tmp_path: Path) -> None:
        path = tmp_path / "untyped.md"
        path.write_text("---\ntitle: draft\n---\nbody\n")
        assert is_non_entity_note(path) is True


class TestBrokenFenceIsAnError:
    @pytest.mark.parametrize(
        ("name", "text"),
        [
            ("unclosed-flow.md", "---\ntype: [unclosed\n---\nbody\n"),
            ("bad-indent.md", "---\ntype: ku\n  bad: [unclosed\n---\nbody\n"),
            ("block-scalar.md", BROKEN_BLOCK_SCALAR),
        ],
    )
    def test_a_fence_that_does_not_parse_fails_validation(
        self, tmp_path: Path, name: str, text: str
    ) -> None:
        path = tmp_path / name
        path.write_text(text)
        result = parse_markdown(path)
        assert result.is_error
        # VALIDATION is what routes it to batch.py's `parsing` stage — a SYSTEM
        # category would file it under file_io as if the disk were at fault.
        assert result.expect_error().category is ErrorCategory.VALIDATION

    def test_the_error_carries_the_line_so_the_author_can_find_it(self, tmp_path: Path) -> None:
        path = tmp_path / "block-scalar.md"
        path.write_text(BROKEN_BLOCK_SCALAR)
        message = parse_markdown(path).expect_error().display_message
        # File line 6 is the stray column-0 line; YAML alone would say 5,
        # because it never sees the opening `---`.
        assert "line 6" in message, message

    def test_it_is_not_a_non_entity_note(self, tmp_path: Path) -> None:
        """The consequence that mattered: it must not hide in the set-aside count."""
        path = tmp_path / "block-scalar.md"
        path.write_text(BROKEN_BLOCK_SCALAR)
        assert is_non_entity_note(path) is False

    def test_both_doors_report_a_broken_document_the_same_way(self, tmp_path: Path) -> None:
        """Markdown and YAML no longer disagree about what a broken file is."""
        md = tmp_path / "broken.md"
        md.write_text("---\ntype: [unclosed\n---\nbody\n")
        yml = tmp_path / "broken.yaml"
        yml.write_text("type: [unclosed\n")
        md_error = parse_markdown(md).expect_error()
        yml_error = parse_yaml(yml).expect_error()
        assert md_error.category is yml_error.category is ErrorCategory.VALIDATION
