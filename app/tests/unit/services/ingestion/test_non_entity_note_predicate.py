"""``declares_entity_type`` / ``is_non_entity_note`` — the no-type verdict, once.

The vault sync preview excludes loose untyped notes from its would-ingest
figures by asking the detector's OWN predicate, so this file pins two things:
what the predicate says, and that it agrees with ``detect_entity_type``'s raise
— the verdict the real sync reports as "treated as a non-entity note". A drift
between the two would make preview and sync disagree about the same file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.services.ingestion.detector import (
    declares_entity_type,
    detect_entity_type,
    is_non_entity_note,
)

UNDECLARED = [
    {},
    {"title": "just a note"},
    {"type": ""},
    {"type": None},
    {"type": "   "},
    {"moc": False},
    {"moc": "true"},  # the convention is the boolean, not the string
]
DECLARED = [
    {"type": "ku"},
    {"type": "Ku"},
    {"type": "edge"},
    {"type": "knowlege"},  # unknown — a typo the sync must report, not a non-entity note
    {"type": 5},
    {"moc": True},
    {"type": "", "moc": True},
]


class TestDeclaresEntityType:
    @pytest.mark.parametrize("data", UNDECLARED)
    def test_undeclared(self, data: dict) -> None:
        assert declares_entity_type(data) is False

    @pytest.mark.parametrize("data", DECLARED)
    def test_declared(self, data: dict) -> None:
        assert declares_entity_type(data) is True

    @pytest.mark.parametrize("data", UNDECLARED)
    def test_detector_raises_the_non_entity_verdict_exactly_when_undeclared(
        self, data: dict
    ) -> None:
        with pytest.raises(ValueError, match="treated as a non-entity note"):
            detect_entity_type(data, Path("note.md"))

    @pytest.mark.parametrize("data", DECLARED)
    def test_detector_never_calls_a_declared_file_a_non_entity_note(self, data: dict) -> None:
        try:
            detected = detect_entity_type(data, Path("note.md"))
        except ValueError as exc:
            assert "treated as a non-entity note" not in str(exc)
        else:
            assert detected is not None

    def test_moc_without_type_is_a_path_step(self) -> None:
        assert detect_entity_type({"moc": True}, Path("moc.md")) is EntityType.PATH_STEP


class TestIsNonEntityNote:
    @pytest.mark.parametrize(
        ("name", "text"),
        [
            ("bare.md", "# just a note\n\nno frontmatter at all"),
            ("untyped.md", "---\ntitle: draft\ntags: [x]\n---\nbody"),
            ("empty-type.md", "---\ntype:\n---\nhalf-finished opt-in"),
            ("untyped.yaml", "title: something\nnotes: []\n"),
        ],
    )
    def test_true_for_the_files_ingestion_sets_aside(
        self, tmp_path: Path, name: str, text: str
    ) -> None:
        path = tmp_path / name
        path.write_text(text)
        assert is_non_entity_note(path) is True

    @pytest.mark.parametrize(
        ("name", "text"),
        [
            ("ku.md", "---\ntype: ku\nuid: ku.test.one\n---\nbody"),
            ("typo.md", "---\ntype: knowlege\n---\nbody"),  # unknown type: sync reports it
            # A fence that does not parse is an authoring error, not a loose
            # note: parse_markdown fails VALIDATION, so the predicate must say
            # False and let sync report it — otherwise a broken file is filed
            # under "set aside" and its entity goes stale unseen.
            ("broken-frontmatter.md", "---\ntype: [unclosed\n---\nbody"),
            ("broken-block-scalar.md", "---\ncontent: |\n\n- stray\n\n  body\n---\nb"),
            ("moc.md", "---\nmoc: true\n---\n[[a]] [[b]]"),
            ("ku.yaml", "type: Ku\nuid: ku.test.two\ntitle: Two\n"),
            ("edge.yaml", "type: edge\nfrom: ku.a\nto: ku.b\nrelationship: ORGANIZES\n"),
        ],
    )
    def test_false_for_declared_files(self, tmp_path: Path, name: str, text: str) -> None:
        path = tmp_path / name
        path.write_text(text)
        assert is_non_entity_note(path) is False

    @pytest.mark.parametrize(
        ("name", "text"),
        [
            (
                "broken.yaml",
                "type: [unclosed\n",
            ),  # a YAML *file* that fails to parse → sync reports it
            ("list.md", "---\n- a\n- b\n---\nbody"),  # non-mapping frontmatter → validation
            ("empty.yaml", ""),  # empty document → parse error
            ("image.png", "not markdown"),  # unsupported extension → never collected
        ],
    )
    def test_false_for_everything_that_is_not_the_no_type_verdict(
        self, tmp_path: Path, name: str, text: str
    ) -> None:
        """Only the one verdict is set aside; every other outcome stays counted."""
        path = tmp_path / name
        path.write_text(text)
        assert is_non_entity_note(path) is False

    def test_false_for_a_missing_file(self, tmp_path: Path) -> None:
        assert is_non_entity_note(tmp_path / "gone.md") is False
