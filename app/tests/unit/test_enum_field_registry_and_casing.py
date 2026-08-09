"""
Enum field registry + ingestion casing normalization (PR #513 residue).

The registry (core/models/enum_field_registry.py) is THE single source of
truth for field→Enum associations; DTOs slice it via ``enum_fields_for`` and
the ingestion preparer normalizes authored casing against the full map.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models.enum_field_registry import ENUM_FIELD_TYPES, enum_fields_for
from core.models.enums import LearningLevel, SELCategory
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.services.ingestion.preparer import normalize_enum_casing, prepare_entity_data


class TestEnumFieldsFor:
    def test_slices_registry(self) -> None:
        sliced = enum_fields_for("status", "sel_category")
        assert sliced == {"status": EntityStatus, "sel_category": SELCategory}

    def test_unknown_field_is_a_real_bug(self) -> None:
        with pytest.raises(KeyError):
            enum_fields_for("status", "not_a_registered_field")

    def test_registry_values_are_enums(self) -> None:
        for field_name, enum_cls in ENUM_FIELD_TYPES.items():
            assert isinstance(field_name, str)
            assert all(isinstance(m.value, str) for m in enum_cls), (
                f"{field_name}: casing normalization assumes str-valued members"
            )


class TestNormalizeEnumCasing:
    def test_uppercase_rewritten_to_canonical(self) -> None:
        data = {"learning_level": "BEGINNER", "sel_category": "RESPONSIBLE_DECISION_MAKING"}
        normalize_enum_casing(data)
        assert data["learning_level"] == LearningLevel.BEGINNER.value
        assert data["sel_category"] == "responsible_decision_making"

    def test_valid_values_untouched(self) -> None:
        data = {"status": "active", "sel_category": "self_awareness"}
        normalize_enum_casing(data)
        assert data == {"status": "active", "sel_category": "self_awareness"}

    def test_event_type_is_registered_and_canonicalized(self) -> None:
        # event_type joined the registry when EventType became a lowercase
        # StrEnum (2026-08): authored/legacy UPPERCASE casing is rewritten to
        # the canonical member value at ingestion.
        data = {"event_type": "PERSONAL"}
        normalize_enum_casing(data)
        assert data["event_type"] == "personal"

    def test_unregistered_field_untouched(self) -> None:
        # A field with no registry entry is never rewritten, whatever its case.
        data = {"location": "Conference Room A", "meeting_url": "HTTPS://X.example"}
        normalize_enum_casing(data)
        assert data == {"location": "Conference Room A", "meeting_url": "HTTPS://X.example"}

    def test_invalid_value_left_for_validator(self) -> None:
        # Casing-only fix: a value that is wrong even lowercased is not our
        # problem — the validator/DTO boundary rejects it with a real error.
        data = {"learning_level": "GRANDMASTER"}
        normalize_enum_casing(data)
        assert data["learning_level"] == "GRANDMASTER"

    def test_non_string_values_untouched(self) -> None:
        data = {"status": None, "learning_level": 3}
        normalize_enum_casing(data)
        assert data == {"status": None, "learning_level": 3}


class TestPrepareEntityDataNormalizesCasing:
    def test_uppercase_exercise_frontmatter_stored_canonical(self) -> None:
        prepared = prepare_entity_data(
            EntityType.EXERCISE,
            {
                "uid": "ex:casing-check",
                "title": "Casing check",
                "instructions": "Do the thing.",
                "scope": "CURRICULUM",
                "learning_level": "BEGINNER",
                "sel_category": "SELF_AWARENESS",
            },
            body="Body.",
            file_path=Path("/tmp/casing-check.md"),
        )
        assert prepared["scope"] == "curriculum"
        assert prepared["learning_level"] == "beginner"
        assert prepared["sel_category"] == "self_awareness"
