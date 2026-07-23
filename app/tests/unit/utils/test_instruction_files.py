"""Tests for the shared founder-local instruction file access (ADR-082 D1).

The containment guard + optional-override reader were lifted out of the
journal instruction_loader so the prompt registry can use them without a
core/prompts → core/services/journal dependency. Both consumers delegate
here; these tests pin the shared semantics directly. The journal-side
delegation is pinned by tests/unit/services/test_journal_instruction_home.py.
"""

from pathlib import Path

import pytest

from core.utils.instruction_files import (
    INSTRUCTIONS_DIR,
    load_optional_override,
    resolve_contained,
)


class TestResolveContained:
    def test_contained_filename_resolves(self, tmp_path: Path) -> None:
        (tmp_path / "askesis_stance.md").write_text("x", encoding="utf-8")
        assert (
            resolve_contained(tmp_path, "askesis_stance.md")
            == (tmp_path / "askesis_stance.md").resolve()
        )

    def test_relative_traversal_is_blocked(self, tmp_path: Path) -> None:
        inside = tmp_path / "instructions"
        inside.mkdir()
        (tmp_path / "outside.md").write_text("escaped content", encoding="utf-8")
        assert resolve_contained(inside, "../outside.md") is None

    def test_absolute_path_outside_is_blocked(self, tmp_path: Path) -> None:
        inside = tmp_path / "instructions"
        inside.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("escaped content", encoding="utf-8")
        assert resolve_contained(inside, str(outside)) is None

    def test_missing_file_still_resolves_path(self, tmp_path: Path) -> None:
        # Containment is about the path, not existence — callers check is_file().
        assert resolve_contained(tmp_path, "not-there.md") is not None


class TestLoadOptionalOverride:
    def test_absent_is_silent_none(self, tmp_path: Path) -> None:
        assert load_optional_override(tmp_path, "missing.md") is None

    def test_present_returns_content(self, tmp_path: Path) -> None:
        (tmp_path / "over.md").write_text("Authored words.", encoding="utf-8")
        assert load_optional_override(tmp_path, "over.md") == "Authored words."

    @pytest.mark.parametrize("blank", ["", "   \n\n\t  "])
    def test_blank_degrades_to_none(self, tmp_path: Path, blank: str) -> None:
        (tmp_path / "over.md").write_text(blank, encoding="utf-8")
        assert load_optional_override(tmp_path, "over.md") is None

    def test_traversal_is_none(self, tmp_path: Path) -> None:
        inside = tmp_path / "instructions"
        inside.mkdir()
        (tmp_path / "outside.md").write_text("escaped content", encoding="utf-8")
        assert load_optional_override(inside, "../outside.md") is None


def test_default_dir_is_data_instructions() -> None:
    assert INSTRUCTIONS_DIR.parts[-2:] == ("data", "instructions")
