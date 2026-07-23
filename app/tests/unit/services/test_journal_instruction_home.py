"""Tests for the Journals authored instruction home (ADR-081 D1).

The conversational bases (discussion / follow-up) are a committed default
FLOOR keyed by JournalMode, with an optional founder-local override file
(``journals.discussion.{mode}.md`` / ``journals.follow_up.{mode}.md``) in
``INSTRUCTIONS_DIR``. These tests pin the floor-when-absent regression
guarantee, override resolution, blank-override degradation, and the shared
traversal-containment guard.
"""

from pathlib import Path

import pytest

from core.models.enums.user_enums import JournalMode
from core.services.journal import instruction_loader
from core.services.journal.instruction_loader import (
    _DISCUSSION_BASE_DEFAULTS,
    _FOLLOW_UP_BASE_DEFAULTS,
    _discussion_base,
    _follow_up_base,
    _load_optional_override,
    discussion_system_prompt,
    follow_up_system_prompt,
    load_named_instruction,
)


@pytest.fixture
def instructions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate the loader from the real founder-local data/instructions/."""
    monkeypatch.setattr(instruction_loader, "INSTRUCTIONS_DIR", tmp_path)
    return tmp_path


class TestFloorCoverage:
    def test_every_mode_has_a_floor_entry_in_both_dicts(self) -> None:
        for mode in JournalMode:
            assert mode.value in _DISCUSSION_BASE_DEFAULTS
            assert mode.value in _FOLLOW_UP_BASE_DEFAULTS
            assert _DISCUSSION_BASE_DEFAULTS[mode.value].strip()
            assert _FOLLOW_UP_BASE_DEFAULTS[mode.value].strip()

    def test_floors_are_mode_distinct(self) -> None:
        assert len(set(_DISCUSSION_BASE_DEFAULTS.values())) == len(JournalMode)
        assert len(set(_FOLLOW_UP_BASE_DEFAULTS.values())) == len(JournalMode)


class TestFloorWhenAbsent:
    def test_bases_return_floor_from_empty_dir(self, instructions_dir: Path) -> None:
        for mode in JournalMode:
            assert _discussion_base(mode) == _DISCUSSION_BASE_DEFAULTS[mode.value]
            assert _follow_up_base(mode) == _FOLLOW_UP_BASE_DEFAULTS[mode.value]

    def test_public_prompts_emit_floor_unchanged(self, instructions_dir: Path) -> None:
        """With no override and no context blocks, the prompt IS the floor text."""
        for mode in JournalMode:
            assert discussion_system_prompt("", mode=mode) == _DISCUSSION_BASE_DEFAULTS[mode.value]
            assert follow_up_system_prompt("", mode=mode) == _FOLLOW_UP_BASE_DEFAULTS[mode.value]

    def test_none_mode_resolves_to_default_floor(self, instructions_dir: Path) -> None:
        default = JournalMode.default()
        assert discussion_system_prompt("") == _DISCUSSION_BASE_DEFAULTS[default.value]
        assert follow_up_system_prompt("") == _FOLLOW_UP_BASE_DEFAULTS[default.value]


class TestOverrideWhenPresent:
    def test_discussion_override_replaces_floor(self, instructions_dir: Path) -> None:
        (instructions_dir / "journals.discussion.scribe.md").write_text(
            "Authored scribe opening.", encoding="utf-8"
        )
        assert discussion_system_prompt("", mode=JournalMode.SCRIBE) == "Authored scribe opening."
        # Other modes keep their committed floor.
        assert (
            discussion_system_prompt("", mode=JournalMode.THOUGHT_PARTNER)
            == _DISCUSSION_BASE_DEFAULTS["thought_partner"]
        )

    def test_follow_up_override_replaces_floor(self, instructions_dir: Path) -> None:
        (instructions_dir / "journals.follow_up.thought_partner.md").write_text(
            "Authored partner follow-up.", encoding="utf-8"
        )
        assert (
            follow_up_system_prompt("", mode=JournalMode.THOUGHT_PARTNER)
            == "Authored partner follow-up."
        )
        # The discussion base is untouched by a follow-up override.
        assert (
            discussion_system_prompt("", mode=JournalMode.THOUGHT_PARTNER)
            == _DISCUSSION_BASE_DEFAULTS["thought_partner"]
        )

    def test_context_blocks_still_append_after_override(self, instructions_dir: Path) -> None:
        (instructions_dir / "journals.discussion.what_is_related.md").write_text(
            "Authored connector opening.", encoding="utf-8"
        )
        prompt = discussion_system_prompt("Active goal: ship PR1", mode=JournalMode.WHAT_IS_RELATED)
        assert prompt.startswith("Authored connector opening.")
        assert "## User's Active Context" in prompt
        assert "Active goal: ship PR1" in prompt


class TestBlankOverrideDegradation:
    @pytest.mark.parametrize("blank", ["", "   \n\n\t  "])
    def test_blank_override_falls_back_to_floor(self, instructions_dir: Path, blank: str) -> None:
        (instructions_dir / "journals.discussion.scribe.md").write_text(blank, encoding="utf-8")
        (instructions_dir / "journals.follow_up.scribe.md").write_text(blank, encoding="utf-8")
        assert _discussion_base(JournalMode.SCRIBE) == _DISCUSSION_BASE_DEFAULTS["scribe"]
        assert _follow_up_base(JournalMode.SCRIBE) == _FOLLOW_UP_BASE_DEFAULTS["scribe"]


class TestTraversalContainment:
    def test_optional_override_blocks_traversal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inside = tmp_path / "instructions"
        inside.mkdir()
        (tmp_path / "outside.md").write_text("escaped content", encoding="utf-8")
        monkeypatch.setattr(instruction_loader, "INSTRUCTIONS_DIR", inside)
        assert _load_optional_override("../outside.md") is None

    def test_named_loader_still_blocks_traversal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inside = tmp_path / "instructions"
        inside.mkdir()
        (tmp_path / "outside.md").write_text("escaped content", encoding="utf-8")
        monkeypatch.setattr(instruction_loader, "INSTRUCTIONS_DIR", inside)
        assert load_named_instruction("../outside.md") is None

    def test_optional_override_miss_is_silent_none(self, instructions_dir: Path) -> None:
        assert _load_optional_override("journals.discussion.scribe.md") is None
