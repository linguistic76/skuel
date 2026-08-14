"""Content-fault classification fixes (2026-07-23 ruling).

Files with improper/missing YAML frontmatter are ignored-with-reason, never
sync errors. That requires the two empty-value crashes to classify cleanly:

1. ``detect_entity_type`` — an empty ``type:`` line parses to None; the old
   ``data.get("type", "").lower()`` crashed with AttributeError (stage
   "unknown" → misclassified as a system fault). Now it raises the same
   clean ValueError as a missing type.
2. ``prepare_entity_data`` — an empty ``uid:`` line satisfied
   ``"uid" in entity_data`` then crashed downstream (historically in the
   since-deleted ``normalize_uid``). Now it raises a clear reason; it must
   NOT silently fall back to a generated UID (guessing an identity invites
   a split on the fix-up sync).

Plus the batch parse path (``parse_file_sync``) tagging both with
content-fault stages, which is what ``_merge_ingest_stats`` classifies on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.services.ingestion.batch import classify_user_entry_failure, parse_file_sync
from core.services.ingestion.detector import detect_entity_type, is_edge_type
from core.services.ingestion.preparer import prepare_entity_data
from core.services.vault.vault_reconciler import _CONTENT_FAULT_STAGES
from core.utils.result_simplified import Errors

_MD = Path("note.md")


class TestDetectorEmptyValues:
    def test_empty_type_raises_clean_valueerror_not_attributeerror(self):
        with pytest.raises(ValueError, match="present but empty"):
            detect_entity_type({"type": None}, _MD)

    def test_missing_type_names_the_absence(self):
        with pytest.raises(ValueError, match="no 'type:' field"):
            detect_entity_type({"title": "just a note"}, _MD)

    def test_missing_type_hint_covers_more_than_ps_and_ku(self):
        """The old message said "Add 'type: PathStep' or 'type: Ku'" — but
        TYPE_MAPPING accepts far more. The hint must show the breadth."""
        with pytest.raises(ValueError) as exc:
            detect_entity_type({}, _MD)
        for accepted in ("resource", "user_entry", "task", "exercise"):
            assert accepted in str(exc.value)

    def test_unknown_declared_type_is_not_reported_as_missing(self):
        with pytest.raises(ValueError, match="unknown type 'foobar'"):
            detect_entity_type({"type": "foobar"}, _MD)

    def test_non_string_type_does_not_crash(self):
        with pytest.raises(ValueError, match="unknown type '5'"):
            detect_entity_type({"type": 5}, _MD)

    def test_moc_flag_still_rescues_missing_type(self):
        assert detect_entity_type({"moc": True}, _MD) is EntityType.PATH_STEP

    def test_is_edge_type_survives_empty_type(self):
        assert is_edge_type({"type": None}) is False
        assert is_edge_type({"type": "edge"}) is True


class TestPreparerEmptyUid:
    def test_empty_uid_line_raises_with_reason(self):
        with pytest.raises(ValueError, match="present but empty"):
            prepare_entity_data(EntityType.KU, {"uid": None, "title": "t"}, None, Path("k.md"))

    def test_whitespace_uid_raises_with_reason(self):
        with pytest.raises(ValueError, match="present but empty"):
            prepare_entity_data(EntityType.KU, {"uid": "  ", "title": "t"}, None, Path("k.md"))

    def test_empty_uid_never_silently_generates(self):
        """The failure mode this guards: an authored-but-empty ``uid:``
        falling back to the filename-generated UID behind the author's back."""
        with pytest.raises(ValueError):
            prepare_entity_data(EntityType.KU, {"uid": "", "title": "t"}, None, Path("k.md"))

    def test_absent_uid_still_generates_from_filename(self):
        prepared = prepare_entity_data(EntityType.KU, {"title": "t"}, None, Path("my-concept.md"))
        assert prepared["uid"] == "ku.my-concept"

    def test_non_string_uid_is_stringified_not_crashed(self):
        # YAML can parse a bare uid value to a non-string (e.g. ``uid: 5``);
        # the preparer stringifies rather than crashing. No rewrite happens —
        # authored = stored (colon input alias deleted 2026-08-14).
        prepared = prepare_entity_data(EntityType.KU, {"uid": 5, "title": "t"}, None, _MD)
        assert prepared["uid"] == "5"


class TestParseFileSyncStageTagging:
    """The stages parse_file_sync stamps are the classification contract —
    every content-caused failure must land in _CONTENT_FAULT_STAGES."""

    def _parse(self, tmp_path: Path, content: str) -> dict:
        file_path = tmp_path / "note.md"
        file_path.write_text(content)
        entity_type, entity_data, error = parse_file_sync(file_path)
        assert entity_type is None and entity_data is None
        assert error is not None
        return error

    def test_missing_type_tags_type_detection(self, tmp_path: Path):
        error = self._parse(tmp_path, "---\ntitle: plain note\n---\nbody\n")
        assert error["stage"] == "type_detection"
        assert error["stage"] in _CONTENT_FAULT_STAGES

    def test_empty_type_tags_type_detection(self, tmp_path: Path):
        error = self._parse(tmp_path, "---\ntype:\ntitle: half opt-in\n---\nbody\n")
        assert error["stage"] == "type_detection"
        assert "present but empty" in error["error"]

    def test_empty_uid_tags_preparation_with_entity_type(self, tmp_path: Path):
        error = self._parse(tmp_path, "---\ntype: ku\nuid:\ntitle: t\nnous: n\n---\nbody\n")
        assert error["stage"] == "preparation"
        assert error["stage"] in _CONTENT_FAULT_STAGES
        assert error["entity_type"] == "ku"
        assert "present but empty" in error["error"]

    def test_broken_yaml_tags_parsing(self, tmp_path: Path):
        error = self._parse(tmp_path, "---\ntype: ku\n  bad: [unclosed\n---\nbody\n")
        assert error["stage"] in _CONTENT_FAULT_STAGES

    def test_unreadable_file_tags_file_io_not_parsing(self, tmp_path: Path):
        """Codex #788 P2: the parsers catch IO exceptions internally and
        return SYSTEM-category Results — an unreadable file is not the
        file's content and must never classify as ignored."""
        file_path = tmp_path / "locked.md"
        file_path.write_text("---\ntype: ku\n---\nbody\n")
        file_path.chmod(0o000)
        try:
            _, _, error = parse_file_sync(file_path)
        finally:
            file_path.chmod(0o644)
        assert error is not None
        assert error["stage"] == "file_io"
        assert error["stage"] not in _CONTENT_FAULT_STAGES


class TestUserEntryFailureClassification:
    """Codex #788 P1: VALIDATION category alone is too broad — the
    unreachable-reviewer compensation is Errors.validation too, and a
    dropped turn-in must stay a sync error, never an ignorable note."""

    def test_frontmatter_field_faults_are_content(self):
        for field in ("pipeline", "status", "je_use", "private", "audience", "metadata"):
            stage, error_type = classify_user_entry_failure(
                Errors.validation(f"bad {field}", field=field)
            )
            assert (stage, error_type) == ("validation", "validation")

    def test_unreachable_reviewer_stays_pipeline_error(self):
        # The exact shape _file_submission_copy returns when a submitted
        # copy reaches no teacher/group (compensated + must be retried).
        error = Errors.validation(
            "Submission for exercise ex_1 reached no teacher or group",
            field="fulfills_exercise_uid",
        )
        assert classify_user_entry_failure(error) == ("user_entry_pipeline", "service")

    def test_fieldless_validation_stays_pipeline_error(self):
        error = Errors.validation("pipeline=TEACHER_REVIEW requires an audience")
        assert classify_user_entry_failure(error) == ("user_entry_pipeline", "service")

    def test_non_validation_categories_stay_pipeline_errors(self):
        for error in (
            Errors.forbidden(action="ingest", reason="ownership mismatch"),
            Errors.database(operation="create_entry", message="neo4j down"),
        ):
            assert classify_user_entry_failure(error) == ("user_entry_pipeline", "service")
