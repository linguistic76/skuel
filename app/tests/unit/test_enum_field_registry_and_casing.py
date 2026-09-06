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
from core.models.enums.entity_enums import EntityStatus, EntityType, NonKuDomain
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
        # it. Sampled on Choice, not Event: the alias resolves the same way
        # for every type (the registry is flat), but DRAFT is not in
        # ``EVENT.valid_statuses()``, so on Event the file is admitted by
        # THIS gate and then refused by the status-legality gate below —
        # which would make this test assert the wrong door.
        file_path = Path("choice_sample.md")
        prepared = prepare_entity_data(
            EntityType.CHOICE, {"title": "C", "status": "pending"}, None, file_path
        )
        assert prepared["status"] == "draft"
        assert validate_entity_data(EntityType.CHOICE, prepared, file_path).is_ok

    def test_alias_still_canonicalized_on_a_type_that_forbids_the_target(self) -> None:
        # The canonicalization half is type-blind and stays that way — the
        # legality verdict is the next gate's job, not this one's.
        prepared = self._prepared_event(status="pending")
        assert prepared["status"] == "draft"

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


class TestStatusLegalityGateAtTheDoor:
    """validate_entity_data's status-legality gate — membership is not legality.

    ``status: completed`` is a real ``EntityStatus`` and still meaningless on a
    Principle. The Activity update chokepoints refuse it at the write (ADR-087);
    the bulk vault upsert bypasses that write, so the file door asks the same
    question pre-persist through the same helper.
    """

    _FILE = Path("sample.md")

    def test_completed_principle_refused_with_the_legal_set(self) -> None:
        data = {"title": "P", "statement": "S", "status": "completed"}
        result = validate_entity_data(EntityType.PRINCIPLE, data, self._FILE)
        assert result.is_error
        error = result.expect_error()
        assert error.details["field"] == "status"
        message = str(error.message)
        assert "principle" in message
        # the author is told what IS legal, not merely that this is not
        assert "active" in message and "paused" in message and "archived" in message

    def test_completed_task_still_passes(self) -> None:
        data = {"title": "T", "status": "completed"}
        assert validate_entity_data(EntityType.TASK, data, self._FILE).is_ok

    def test_draft_event_refused(self) -> None:
        # The hole this gate closes on a type that actually appears in the
        # vault: DRAFT is a member of EntityStatus but not of
        # EVENT.valid_statuses(), and the vocabulary gate cannot see that.
        data = {"title": "E", "status": "draft"}
        result = validate_entity_data(EntityType.EVENT, data, self._FILE)
        assert result.is_error
        assert result.expect_error().details["field"] == "status"

    def test_user_entry_stays_exempt(self) -> None:
        # ACTIVE is NOT in USER_ENTRY.valid_statuses(), and a real vault file
        # carries it — the ADR-054 door owns that frontmatter, so this gate
        # must not adjudicate it (same carve-out as the vocabulary gate).
        assert EntityStatus.ACTIVE not in EntityType.USER_ENTRY.valid_statuses()
        data = {"title": "Living note", "status": "active"}
        assert validate_entity_data(EntityType.USER_ENTRY, data, self._FILE).is_ok

    def test_non_ku_domain_is_skipped_not_crashed(self) -> None:
        # NonKuDomain has no valid_statuses(); the gate must step over it.
        data = {"name": "G", "status": "completed"}
        result = validate_entity_data(NonKuDomain.GROUP, data, self._FILE)
        assert not (result.is_error and result.expect_error().details.get("field") == "status")

    def test_null_status_is_absence_not_an_illegal_value(self) -> None:
        # The authored ``none`` marker and an empty ``status:`` line both
        # prepare to a PRESENT key holding None. The vocabulary gate reads
        # that as absent; a legality check that tests key membership instead
        # would refuse a file both gates admit (Codex #1289).
        for authored in ("none", None):
            prepared = prepare_entity_data(
                EntityType.TASK, {"title": "T", "status": authored}, None, self._FILE
            )
            assert prepared["status"] is None
            assert validate_entity_data(EntityType.TASK, prepared, self._FILE).is_ok, (
                f"status: {authored!r} must be admitted as absence"
            )

    def test_absent_status_is_not_a_verdict(self) -> None:
        assert validate_entity_data(
            EntityType.PRINCIPLE, {"title": "P", "statement": "S"}, self._FILE
        ).is_ok

    def test_non_member_value_belongs_to_the_vocabulary_gate(self) -> None:
        # Order matters: a non-word gets the "must be one of" vocabulary
        # message, not a legality message that would list a set it was never
        # a candidate for.
        result = validate_entity_data(EntityType.PRINCIPLE, {"status": "banana"}, self._FILE)
        assert result.is_error
        assert "must be one of" in str(result.expect_error().message)

    def test_verdict_matches_valid_statuses_for_every_type(self) -> None:
        # The derivation: the door's verdict IS EntityType.valid_statuses(),
        # so the two cannot drift. USER_ENTRY is exempt by ruling.
        for entity_type in EntityType:
            if entity_type is EntityType.USER_ENTRY:
                continue
            for status in EntityStatus:
                result = validate_entity_data(entity_type, {"status": status.value}, self._FILE)
                refused_on_status = (
                    result.is_error and result.expect_error().details.get("field") == "status"
                )
                assert refused_on_status is (status not in entity_type.valid_statuses()), (
                    f"{entity_type.value}/{status.value}: door and valid_statuses() disagree"
                )

    def test_every_ingestible_config_default_is_legal(self) -> None:
        # An illegal default would refuse EVERY file of its type — the
        # legality analogue of test_config_default_values_are_members.
        for entity_type, config in ENTITY_CONFIGS.items():
            default = (config.default_values or {}).get("status")
            if default is None or not isinstance(entity_type, EntityType):
                continue
            assert EntityStatus(default) in entity_type.valid_statuses(), (
                f"{entity_type.value}: default status {default!r} is not legal for it"
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
