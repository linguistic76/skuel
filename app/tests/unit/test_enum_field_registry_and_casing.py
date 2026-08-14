"""
Enum field registry + ingestion casing normalization (PR #513 residue).

The registry (core/models/enum_field_registry.py) is THE single source of
truth for field→Enum associations; DTOs slice it via ``enum_fields_for`` and
the ingestion preparer canonicalizes authored values against the full map
(casing, each enum's ``from_string`` aliases, the ``none`` absence marker —
mirroring the ``parse_enum_field`` read tolerances); the ingestion
validator's vocabulary gate rejects what remains non-member.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models.enum_field_registry import ENUM_FIELD_TYPES, enum_fields_for
from core.models.enums import LearningLevel, SELCategory
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.ingestion.preparer import canonicalize_enum_values, prepare_entity_data
from core.services.ingestion.validator import validate_entity_data


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


class TestCanonicalizeEnumValues:
    def test_uppercase_rewritten_to_canonical(self) -> None:
        data = {"learning_level": "BEGINNER", "sel_category": "RESPONSIBLE_DECISION_MAKING"}
        canonicalize_enum_values(data)
        assert data["learning_level"] == LearningLevel.BEGINNER.value
        assert data["sel_category"] == "responsible_decision_making"

    def test_valid_values_untouched(self) -> None:
        data = {"status": "active", "sel_category": "self_awareness"}
        canonicalize_enum_values(data)
        assert data == {"status": "active", "sel_category": "self_awareness"}

    def test_event_type_is_registered_and_canonicalized(self) -> None:
        # event_type joined the registry when EventType became a lowercase
        # StrEnum (2026-08): authored/legacy UPPERCASE casing is rewritten to
        # the canonical member value at ingestion.
        data = {"event_type": "PERSONAL"}
        canonicalize_enum_values(data)
        assert data["event_type"] == "personal"

    def test_unregistered_field_untouched(self) -> None:
        # A field with no registry entry is never rewritten, whatever its case.
        data = {"location": "Conference Room A", "meeting_url": "HTTPS://X.example"}
        canonicalize_enum_values(data)
        assert data == {"location": "Conference Room A", "meeting_url": "HTTPS://X.example"}

    def test_invalid_value_left_for_validator(self) -> None:
        # Casing-only fix: a value that is wrong even lowercased is not our
        # problem — validate_entity_data's vocabulary gate rejects it at the
        # door (TestEnumMembershipGateAtTheDoor).
        data = {"learning_level": "GRANDMASTER"}
        canonicalize_enum_values(data)
        assert data["learning_level"] == "GRANDMASTER"

    def test_non_string_values_untouched(self) -> None:
        data = {"status": None, "learning_level": 3}
        canonicalize_enum_values(data)
        assert data == {"status": None, "learning_level": 3}

    def test_from_string_alias_stores_canonical(self) -> None:
        # The guide's Task example authors ``status: pending`` — resolved by
        # EntityStatus.from_string (Codex #1003 round 2). The GRAPH stores
        # the canonical member, never the alias (emission rule).
        data = {"status": "pending"}
        canonicalize_enum_values(data)
        assert data["status"] == EntityStatus.DRAFT.value
        data = {"status": "In Process"}
        canonicalize_enum_values(data)
        assert data["status"] == EntityStatus.ACTIVE.value

    def test_none_marker_becomes_absent(self) -> None:
        # ``sel_category: none`` is the authored absence marker the READ
        # boundary sanctions (rawness principle, PR #536) — the write door
        # mirrors it: value None, so the bulk upsert drops the property.
        data = {"sel_category": "none"}
        canonicalize_enum_values(data)
        assert data["sel_category"] is None
        data = {"sel_category": "NONE"}
        canonicalize_enum_values(data)
        assert data["sel_category"] is None

    def test_none_spelling_on_enum_with_none_member_stays_member(self) -> None:
        # Pipeline HAS a NONE member — there "none" is vocabulary, not the
        # absence marker; the casing tier resolves it first.
        data = {"pipeline": "NONE"}
        canonicalize_enum_values(data)
        assert data["pipeline"] == "none"


class TestEnumMembershipGateAtTheDoor:
    """validate_entity_data's vocabulary gate — the write-door half of the
    enum contract (the READ side deliberately keeps ``str`` so persisted
    strays load). A non-member value in ANY registered field rejects the file
    in every vault; casing-only problems were already fixed by the preparer.
    """

    _FILE = Path("event_sample.md")

    def _prepared_event(self, **fields: object) -> dict[str, object]:
        data: dict[str, object] = {"title": "Sample event", **fields}
        return prepare_entity_data(EntityType.EVENT, data, None, self._FILE)

    def test_non_member_value_rejected(self) -> None:
        # The proven 2026-08-09 gap: ``event_type: PRACTICE`` upserted
        # silently ("practice" is not an EventType member, so the casing
        # pass could not launder it — and nothing rejected it).
        prepared = self._prepared_event(event_type="PRACTICE")
        result = validate_entity_data(EntityType.EVENT, prepared, self._FILE)
        assert result.is_error
        message = str(result.expect_error().message)
        assert "event_type" in message
        assert "'PRACTICE'" in message
        assert "meeting" in message  # the vocabulary is listed for the author

    def test_casing_only_value_admitted(self) -> None:
        # prepare rewrites MEETING → meeting, so the gate never sees it.
        prepared = self._prepared_event(event_type="MEETING")
        assert prepared["event_type"] == "meeting"
        assert validate_entity_data(EntityType.EVENT, prepared, self._FILE).is_ok

    def test_member_and_absent_values_admitted(self) -> None:
        assert validate_entity_data(
            EntityType.EVENT, self._prepared_event(event_type="workshop"), self._FILE
        ).is_ok
        assert validate_entity_data(EntityType.EVENT, self._prepared_event(), self._FILE).is_ok

    def test_none_is_absence_not_a_violation(self) -> None:
        prepared = self._prepared_event()
        prepared["event_type"] = None
        assert validate_entity_data(EntityType.EVENT, prepared, self._FILE).is_ok

    def test_non_string_value_rejected(self) -> None:
        prepared = self._prepared_event(event_type=3)
        result = validate_entity_data(EntityType.EVENT, prepared, self._FILE)
        assert result.is_error
        assert "got 3" in str(result.expect_error().message)

    def test_multiple_violations_reported_together(self) -> None:
        prepared = self._prepared_event(event_type="PRACTICE", learning_level="GRANDMASTER")
        result = validate_entity_data(EntityType.EVENT, prepared, self._FILE)
        assert result.is_error
        message = str(result.expect_error().message)
        assert "event_type" in message
        assert "learning_level" in message

    def test_exercise_scope_keeps_its_door_policy_message(self) -> None:
        # 'personal' IS vocabulary — the gate admits it; the ingestion-door
        # policy (scope must be curriculum) still rejects with its own message.
        file_path = Path("exercise_sample.md")
        prepared = prepare_entity_data(
            EntityType.EXERCISE,
            {"title": "S", "instructions": "Do.", "scope": "personal"},
            None,
            file_path,
        )
        result = validate_entity_data(EntityType.EXERCISE, prepared, file_path)
        assert result.is_error
        assert "curriculum" in str(result.expect_error().message)

    def test_exercise_scope_non_word_gets_vocabulary_message(self) -> None:
        # A non-member scope is a vocabulary fault, not door policy — the
        # gate fires first, so the "app-created only" claim (true only of
        # real scopes) never fires on a non-word.
        file_path = Path("exercise_sample.md")
        prepared = prepare_entity_data(
            EntityType.EXERCISE,
            {"title": "S", "instructions": "Do.", "scope": "banana"},
            None,
            file_path,
        )
        result = validate_entity_data(EntityType.EXERCISE, prepared, file_path)
        assert result.is_error
        message = str(result.expect_error().message)
        assert "must be one of" in message
        assert "'banana'" in message

    def test_sanctioned_alias_admitted_through_the_full_path(self) -> None:
        # prepare canonicalizes ``pending`` → ``draft`` (Codex #1003 round
        # 2), so the gate never sees the alias — and the graph never stores
        # it.
        prepared = self._prepared_event(status="pending")
        assert prepared["status"] == "draft"
        assert validate_entity_data(EntityType.EVENT, prepared, self._FILE).is_ok

    def test_none_absence_marker_admitted_through_the_full_path(self) -> None:
        prepared = self._prepared_event(sel_category="none")
        assert prepared["sel_category"] is None
        assert validate_entity_data(EntityType.EVENT, prepared, self._FILE).is_ok

    def test_unsanctioned_status_still_rejected(self) -> None:
        # from_string returns None for a non-alias — the gate still fires.
        prepared = self._prepared_event(status="banana")
        result = validate_entity_data(EntityType.EVENT, prepared, self._FILE)
        assert result.is_error
        assert "'banana'" in str(result.expect_error().message)

    def test_user_entry_exempt_alias_statuses_reach_their_own_door(self) -> None:
        # Codex #1003: the batch door runs this validator on user_entry files
        # BEFORE routing them to the ADR-054 branch, whose _parse_status is
        # alias-aware ("in process" → active). The gate must not reject on
        # the batch path what single-file UserEntry ingestion accepts.
        file_path = Path("note.md")
        ue_data = {"title": "Living note", "status": "in process"}
        assert validate_entity_data(EntityType.USER_ENTRY, ue_data, file_path).is_ok
        # Control: on a gated type the same UNPREPARED spelling is a
        # violation — a gated door admits it only via prepare's
        # canonicalization, while USER_ENTRY is exempt outright.
        event_data = {"title": "E", "status": "in process"}
        assert validate_entity_data(EntityType.EVENT, event_data, file_path).is_error

    def test_config_default_values_are_members(self) -> None:
        # A non-member config default would reject EVERY file of its type —
        # a code bug this suite must catch, not the sync report.
        for entity_type, config in ENTITY_CONFIGS.items():
            for field_name, default in (config.default_values or {}).items():
                enum_cls = ENUM_FIELD_TYPES.get(field_name)
                if enum_cls is None:
                    continue
                assert default in {m.value for m in enum_cls}, (
                    f"{entity_type}: default {field_name}={default!r} is not a member"
                )


class TestPrepareEntityDataNormalizesCasing:
    def test_uppercase_exercise_frontmatter_stored_canonical(self) -> None:
        prepared = prepare_entity_data(
            EntityType.EXERCISE,
            {
                "uid": "ex.casing-check",
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
