"""Tests for user_entry_ingestion (vault ingest → UserEntryService bridge)."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.audience import AudienceSpec
from core.models.user_entry.submitted_copy import SubmittedCopy, submission_fingerprint
from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.ingestion.user_entry_ingestion import (
    SUBMISSION_FIELD,
    build_user_entry_request,
    ingest_user_entry,
)
from core.services.user_entry.audience_resolver import ShareOutcome
from core.utils.result_simplified import Result


class TestBuildUserEntryRequest:
    @pytest.mark.asyncio
    async def test_missing_pipeline_rejected(self):
        result = build_user_entry_request(
            data={"title": "x"},
            file_path=Path("reflection.yaml"),
            user_uid="user_1",
        )
        assert result.is_error
        assert "pipeline" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_garbled_je_use_rejected(self):
        # A typo'd je_use is an authored scoping intent we can't honor — fail
        # loudly (mirrors the collection-level gate's fail-closed posture).
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "je_use": "exmplar"},
            file_path=Path("thought.md"),
            user_uid="user_1",
        )
        assert result.is_error
        assert "je_use" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_valid_je_use_accepted(self):
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "je_use": "understanding", "title": "Me"},
            file_path=Path("thought.md"),
            user_uid="user_1",
        )
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_private_true_flows_to_request(self):
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "private": True, "title": "Secret"},
            file_path=Path("secret.md"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.private is True

    @pytest.mark.asyncio
    async def test_private_absent_defaults_retrievable(self):
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "title": "Open"},
            file_path=Path("open.md"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.private is False

    @pytest.mark.asyncio
    async def test_garbled_private_rejected(self):
        # A quoted "true" is a string, not a boolean — silently ignoring an
        # authored privacy intent is the one unacceptable failure mode here.
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "private": "true", "title": "Secret"},
            file_path=Path("secret.md"),
            user_uid="user_1",
        )
        assert result.is_error
        assert "private" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_audio_pipeline_rejected(self):
        result = build_user_entry_request(
            data={"pipeline": "transcribe_and_structure"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_error
        assert "audio" in str(result.expect_error()).lower()

    def test_teacher_review_on_a_vault_note_is_refused_with_guidance(self):
        """A vault note is a draft (R9): the feedback request is its frozen
        copy. Refused on the ``pipeline`` content field, naming the remedy."""
        result = build_user_entry_request(
            data={"pipeline": "teacher_review", "title": "Essay"},
            file_path=Path("/vault/essays/essay.md"),
            user_uid="user_1",
        )
        assert result.is_error
        error = result.expect_error()
        assert error.details["field"] == "pipeline"
        assert "status: submitted" in error.message

    def test_a_vault_note_is_never_offered_teacher_review(self):
        """The accepted-values list a vault author sees omits the refused value."""
        result = build_user_entry_request(
            data={"pipeline": "bogus"},
            file_path=Path("/vault/essays/essay.md"),
            user_uid="user_1",
        )
        assert result.is_error
        assert "teacher_review" not in result.expect_error().message

    def test_teacher_review_from_a_script_still_parses(self):
        """Relative paths come only from scripts and tests, which file a
        submission directly — the vault gate is on the absolute path."""
        result = build_user_entry_request(
            data={"pipeline": "teacher_review", "title": "Essay"},
            file_path=Path("essay.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.pipeline == Pipeline.TEACHER_REVIEW

    def test_absent_audience_is_the_empty_spec(self):
        """Absent means nobody was named: on ``teacher_review`` ``create_entry``
        reads that as ``teachers``; on every other pipeline as no links.
        Nothing is expanded here — the builder is pure."""
        for pipeline in ("teacher_review", "none", "knowledge", "extract_activities"):
            result = build_user_entry_request(
                data={"pipeline": pipeline, "title": "Essay"},
                file_path=Path("essay.yaml"),
                user_uid="user_1",
            )
            assert result.is_ok, pipeline
            assert result.value.audience == AudienceSpec(), pipeline

    def test_the_vocabulary_parses_as_a_list_preserving_case(self):
        result = build_user_entry_request(
            data={
                "pipeline": "teacher_review",
                "audience": ["teachers", "teacher:G_math", "group:g_class", "user:Alice"],
            },
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.audience == AudienceSpec(
            teachers=True,
            teacher_groups=("G_math",),
            share_groups=("g_class",),
            share_users=("Alice",),
        )

    def test_a_single_value_parses_too(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "audience": "group:g_class"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.audience == AudienceSpec(share_groups=("g_class",))

    def test_group_on_teacher_review_stays_a_share_here(self):
        """``group:`` is always a share (ADR-088 §8); whether a teacher_review
        note may carry only a share is ``create_entry``'s refusal, with
        guidance naming ``teacher:<group_uid>``."""
        result = build_user_entry_request(
            data={"pipeline": "teacher_review", "audience": "group:g_class"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.audience == AudienceSpec(share_groups=("g_class",))

    def test_audience_group_without_uid_rejected(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "audience": "group:"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_error
        assert result.expect_error().details["field"] == "audience"

    def test_unknown_audience_rejected_on_the_audience_field(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "audience": "everyone"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_error
        assert result.expect_error().details["field"] == "audience"

    def test_private_combined_with_another_value_rejected(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "audience": ["private", "user:bob"]},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_error
        assert "combines with no other value" in result.expect_error().message

    def test_public_audience_rides_on_the_spec(self):
        """``audience: public`` is a request value; its TEACHER gate is
        ``create_entry``'s (one gate for every door), not the builder's."""
        result = build_user_entry_request(
            data={"pipeline": "none", "audience": "public"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.audience == AudienceSpec(public=True)

    def test_private_audience_is_explicit(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "audience": "private"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.audience == AudienceSpec(private=True)

    def test_a_share_on_a_private_pipeline_is_not_coerced_here(self):
        """The refusal is ``AudienceResolver.validate``'s, at ``create_entry``
        — the builder carries the authored value through unchanged."""
        result = build_user_entry_request(
            data={"pipeline": "reference", "audience": "group:g1"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.audience == AudienceSpec(share_groups=("g1",))

    @pytest.mark.asyncio
    async def test_title_defaults_from_filename(self):
        result = build_user_entry_request(
            data={"pipeline": "none"},
            file_path=Path("my-deep-reflection.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.title == "My Deep Reflection"

    @pytest.mark.asyncio
    async def test_unknown_pipeline_rejected(self):
        result = build_user_entry_request(
            data={"pipeline": "does_not_exist"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_error
        assert "pipeline" in str(result.expect_error()).lower()


class TestPriorUidReuse:
    """Path-keyed identity: the tracker's prior uid gives uid-less vault notes a
    stable identity so they upsert in place instead of orphaning the old node.
    Contract: docs/roadmap/done/uidless-vault-entry-identity-upsert.md."""

    @pytest.mark.asyncio
    async def test_uidless_knowledge_note_reuses_prior_uid(self):
        """A uid-less knowledge note on an absolute (vault) path adopts the
        prior uid → routes to the MERGE-on-uid living-entry channel."""
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "title": "Nous"},
            file_path=Path("/vault/knowledge/nous.md"),
            user_uid="user_1",
            prior_uid="ue_prior_abc",
        )
        assert result.is_ok
        assert result.value.uid == "ue_prior_abc"

    @pytest.mark.asyncio
    async def test_first_sync_mints_a_living_uid(self):
        """First sync (no tracker row) → the door mints the uid, so the note is
        a living draft from sync one (R9) and the tracker records it."""
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "title": "Nous"},
            file_path=Path("/vault/knowledge/nous.md"),
            user_uid="user_1",
            prior_uid=None,
        )
        assert result.is_ok
        assert result.value.uid is not None
        assert result.value.uid.startswith("ue_")

    @pytest.mark.asyncio
    async def test_an_empty_authored_uid_is_no_uid(self):
        """``uid: ""`` names nothing: the note keeps its tracked identity
        instead of minting a fresh node every sync."""
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "title": "Nous", "uid": ""},
            file_path=Path("/vault/knowledge/nous.md"),
            user_uid="user_1",
            prior_uid="ue_prior_abc",
        )
        assert result.is_ok
        assert result.value.uid == "ue_prior_abc"

    @pytest.mark.asyncio
    async def test_authored_uid_wins_over_prior_uid(self):
        """An authored ``uid:`` is identity — never overridden by the tracker."""
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "title": "Nous", "uid": "ku.mine.nous"},
            file_path=Path("/vault/knowledge/nous.md"),
            user_uid="user_1",
            prior_uid="ue_prior_abc",
        )
        assert result.is_ok
        # Authored = stored, verbatim; prior uid ignored.
        assert result.value.uid == "ku.mine.nous"

    @pytest.mark.asyncio
    async def test_authored_colon_uid_is_rejected_loudly(self):
        """The retired colon spelling must fail, not upsert — forwarding
        ``moc:worldview`` verbatim would split identity against a note
        previously stored as ``moc.worldview`` (Codex P1 #1054). Derived
        periodic ``ue:…`` uids are unaffected — they are built, not authored."""
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "title": "Worldview", "uid": "moc:worldview"},
            file_path=Path("/vault/knowledge/worldview.md"),
            user_uid="user_1",
        )
        assert result.is_error
        error = result.expect_error()
        assert error.details.get("field") == "uid"
        assert "moc.worldview" in error.message  # remedy names the dot form

    @pytest.mark.asyncio
    async def test_a_declared_exercise_keeps_the_note_living(self):
        """A vault note declaring an exercise is a draft too (R9): it reuses
        its tracked uid, so it never enters the turn-in branch — its frozen
        copy does."""
        result = build_user_entry_request(
            data={
                "pipeline": "knowledge",
                "title": "Turn-in",
                "fulfills_exercise_uid": "ex_1",
            },
            file_path=Path("/vault/knowledge/turnin.md"),
            user_uid="user_1",
            prior_uid="ue_prior_abc",
        )
        assert result.is_ok
        assert result.value.uid == "ue_prior_abc"
        assert result.value.fulfills_exercise_uid == "ex_1"

    @pytest.mark.asyncio
    async def test_a_declared_exercise_on_first_sync_is_living_too(self):
        """The first sync is the case the prior uid never covered: without the
        minted uid ``create_entry`` would file the note itself as a turn-in."""
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "title": "T", "fulfills_exercise_uid": "ex_1"},
            file_path=Path("/vault/knowledge/turnin.md"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.uid is not None

    @pytest.mark.asyncio
    async def test_non_absolute_path_blocks_reuse(self):
        """Uploads pass a temp/relative path — they must keep minting fresh
        uids, never adopt a vault tracker row."""
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "title": "Upload"},
            file_path=Path("upload.md"),
            user_uid="user_1",
            prior_uid="ue_prior_abc",
        )
        assert result.is_ok
        assert result.value.uid is None


class TestAuthoredStatusDescriptionOwnership:
    """The door must not silently drop authored frontmatter it understands."""

    @pytest.mark.asyncio
    async def test_authored_status_flows(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "status": "draft"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.status == EntityStatus.DRAFT

    @pytest.mark.asyncio
    async def test_status_alias_in_process_maps_to_active(self):
        """The live fixture's authored spelling — 'in process' → ACTIVE."""
        result = build_user_entry_request(
            data={"pipeline": "knowledge", "status": "in process"},
            file_path=Path("nous topics.md"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.status == EntityStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_unrecognized_status_fails_loudly(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "status": "vibing"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_error
        err = str(result.expect_error())
        assert "vibing" in err
        assert "active" in err  # accepted values listed

    @pytest.mark.asyncio
    async def test_absent_or_empty_status_is_none(self):
        """None → the service applies its pipeline default; bare `status:`
        parses as YAML None and must behave the same as absent."""
        for data in ({"pipeline": "none"}, {"pipeline": "none", "status": None}):
            result = build_user_entry_request(
                data=data,
                file_path=Path("x.yaml"),
                user_uid="user_1",
            )
            assert result.is_ok
            assert result.value.status is None

    @pytest.mark.asyncio
    async def test_description_flows(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "description": "Topics taxonomy"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.description == "Topics taxonomy"

    @pytest.mark.asyncio
    async def test_falsy_authored_description_preserved(self):
        """YAML `description: 0` / `description: false` are authored values —
        only a truly absent field maps to None."""
        for raw, expected in ((0, "0"), (False, "False")):
            result = build_user_entry_request(
                data={"pipeline": "none", "description": raw},
                file_path=Path("x.yaml"),
                user_uid="user_1",
            )
            assert result.is_ok
            assert result.value.description == expected

    @pytest.mark.asyncio
    async def test_missing_description_is_none(self):
        result = build_user_entry_request(
            data={"pipeline": "none"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
        )
        assert result.is_ok
        assert result.value.description is None

    @pytest.mark.asyncio
    async def test_ownership_short_form_matches(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "ownership": "linguistic76"},
            file_path=Path("x.yaml"),
            user_uid="user_linguistic76",
        )
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_ownership_canonical_form_matches(self):
        result = build_user_entry_request(
            data={"pipeline": "none", "user_uid": "user_linguistic76"},
            file_path=Path("x.yaml"),
            user_uid="user_linguistic76",
        )
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_ownership_mismatch_rejected(self):
        """A file declaring another owner must fail, never be silently
        claimed by the syncing user."""
        result = build_user_entry_request(
            data={"pipeline": "none", "ownership": "someone_else"},
            file_path=Path("x.yaml"),
            user_uid="user_linguistic76",
        )
        assert result.is_error
        err = str(result.expect_error())
        assert "someone_else" in err
        assert "user_linguistic76" in err


class TestIngestUserEntry:
    @pytest.mark.asyncio
    async def test_delegates_to_create_entry(self):
        entry = UserEntry(
            uid="ue_1",
            title="Essay",
            user_uid="user_1",
            pipeline=Pipeline.TEACHER_REVIEW,
        )
        outcome = ShareOutcome(submitted_groups=("g_a",), newly_submitted_groups=("g_a",))

        service = MagicMock()
        service.create_entry = AsyncMock(return_value=Result.ok((entry, outcome)))

        result = await ingest_user_entry(
            data={"pipeline": "teacher_review", "title": "Essay"},
            file_path=Path("essay.yaml"),
            user_uid="user_1",
            user_entry_service=service,
        )

        assert result.is_ok
        payload = result.value
        assert payload["uid"] == "ue_1"
        assert payload["entity_type"] == "user_entry"
        assert payload["success"] is True
        assert payload["relationships_created"] == 1  # one new feedback request, no exercise
        assert payload["share_outcome"]["submitted_groups"] == ["g_a"]
        assert payload["share_outcome"]["shared_groups"] == []
        # The ingest_file USER_ENTRY branch keys the chunk substrate on these
        # two flags (canon P3) — they must ride the result dict.
        assert payload["pipeline"] == "teacher_review"
        assert payload["private"] is False

    @pytest.mark.asyncio
    async def test_result_dict_carries_private_flag(self):
        entry = UserEntry(
            uid="ue_secret",
            title="Secret",
            user_uid="user_1",
            pipeline=Pipeline.KNOWLEDGE,
            private=True,
        )
        service = MagicMock()
        service.create_entry = AsyncMock(return_value=Result.ok((entry, ShareOutcome())))

        result = await ingest_user_entry(
            data={"pipeline": "knowledge", "private": True, "title": "Secret"},
            file_path=Path("secret.md"),
            user_uid="user_1",
            user_entry_service=service,
        )

        assert result.is_ok
        assert result.value["pipeline"] == "knowledge"
        assert result.value["private"] is True

    @pytest.mark.asyncio
    async def test_validation_error_short_circuits(self):
        service = MagicMock()
        service.create_entry = AsyncMock()

        result = await ingest_user_entry(
            data={"title": "no pipeline"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            user_entry_service=service,
        )

        assert result.is_error
        service.create_entry.assert_not_awaited()


NOTE_UID = "ue.vault.tasks-list"
VAULT_PATH = Path("/vault/exercises/tasks-list.md")


def _living_entry(uid: str = NOTE_UID, pipeline: Pipeline = Pipeline.KNOWLEDGE) -> UserEntry:
    return UserEntry(
        uid=uid,
        title="My task list",
        user_uid="user_1",
        pipeline=pipeline,
        fulfills_exercise_uid="ex_list_tasks",
    )


def _copy_entry(uid: str = "ue_copy_1") -> UserEntry:
    return UserEntry(
        uid=uid,
        title="My task list",
        user_uid="user_1",
        pipeline=Pipeline.TEACHER_REVIEW,
        fulfills_exercise_uid="ex_list_tasks",
    )


def _note(status: str = "in process", **fields: object) -> dict:
    data: dict = {
        "pipeline": "knowledge",
        "title": "My task list",
        "uid": NOTE_UID,
        "fulfills_exercise_uid": "ex_list_tasks",
        "status": status,
        "content": "- buy milk",
    }
    data.update(fields)
    return {k: v for k, v in data.items() if v is not None}


def _copy_fingerprint(audience: object = "teachers", **overrides: object) -> str:
    """The fingerprint of the copy the default note files, with ``overrides``."""
    fields: dict = {
        "title": "My task list",
        "content": "- buy milk",
        "tags": [],
        "private": False,
        "status": EntityStatus.SUBMITTED,
        "pipeline": Pipeline.TEACHER_REVIEW,
        "fulfills_exercise_uid": "ex_list_tasks",
        "audience": audience,
    }
    fields.update(overrides)
    return submission_fingerprint(UserEntryCreateRequest(**fields))


class TestVaultNotesAreDrafts:
    """R9: a vault note is one living draft; ``status: submitted`` files a frozen copy."""

    def _service(self, create_side_effects, latest=None) -> MagicMock:
        service = MagicMock()
        service.create_entry = AsyncMock(side_effect=create_side_effects)
        service.get_latest_copy_of_note = AsyncMock(return_value=Result.ok(latest))
        service.delete_entry = AsyncMock(return_value=Result.ok(True))
        return service

    async def _ingest(self, service: MagicMock, data: dict, path: Path = VAULT_PATH):
        return await ingest_user_entry(
            data=data, file_path=path, user_uid="user_1", user_entry_service=service
        )

    @staticmethod
    def _copy_call(service: MagicMock):
        call = service.create_entry.await_args_list[1]
        return call.args[0], call.kwargs["copy_of"]

    @pytest.mark.asyncio
    async def test_a_draft_is_one_living_upsert_that_names_no_audience(self):
        service = self._service([Result.ok((_living_entry(), ShareOutcome()))])
        result = await self._ingest(service, _note("in process", audience="teachers"))
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 1
        request = service.create_entry.await_args.kwargs["request"]
        assert request.uid == NOTE_UID  # authored = stored, verbatim
        assert request.fulfills_exercise_uid == "ex_list_tasks"
        assert request.status == EntityStatus.ACTIVE
        assert request.audience == AudienceSpec()  # a draft is never shared
        assert result.value["submitted_copy_uid"] is None
        assert result.value["nodes_created"] == 1
        service.get_latest_copy_of_note.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_draft_that_declares_an_audience_warns(self):
        """The audience does nothing until submission — said, never silent."""
        service = self._service([Result.ok((_living_entry(), ShareOutcome()))])
        result = await self._ingest(service, _note("in process", audience=["group:g1"]))
        assert result.is_ok, result.expect_error()
        assert any("does nothing on a draft" in w for w in result.value["warnings"])

    @pytest.mark.asyncio
    async def test_a_private_draft_does_not_warn(self):
        service = self._service([Result.ok((_living_entry(), ShareOutcome()))])
        result = await self._ingest(service, _note("in process", audience="private"))
        assert result.is_ok, result.expect_error()
        assert result.value["warnings"] == []

    @pytest.mark.asyncio
    async def test_submitted_files_a_frozen_copy_to_teachers_by_default(self):
        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.ok(
                    (
                        _copy_entry(),
                        ShareOutcome(
                            submitted_groups=("g_teacher",),
                            newly_submitted_groups=("g_teacher",),
                        ),
                    )
                ),
            ]
        )
        result = await self._ingest(service, _note("submitted"))
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 2

        living_request = service.create_entry.await_args_list[0].kwargs["request"]
        # The note is NOT itself submitted — it stays active while the file
        # says submitted; the copy carries the truthful status.
        assert living_request.status == EntityStatus.ACTIVE
        assert living_request.uid == NOTE_UID

        copy_request, copy_of = self._copy_call(service)
        assert copy_request.uid is None  # a fresh node
        assert copy_request.pipeline == Pipeline.TEACHER_REVIEW
        assert copy_request.status == EntityStatus.SUBMITTED
        assert copy_request.audience == AudienceSpec(teachers=True)
        assert copy_request.fulfills_exercise_uid == "ex_list_tasks"
        assert copy_request.content == "- buy milk"
        assert copy_request.metadata == {}  # no vault_file_path: invisible to write-back
        assert copy_of == SubmittedCopy(
            submitted_from_uid=NOTE_UID, fingerprint=_copy_fingerprint()
        )

        assert result.value["submitted_copy_uid"] == "ue_copy_1"
        assert result.value["nodes_created"] == 2
        assert result.value["relationships_created"] == 2  # the request + the exercise edge
        assert result.value["share_outcome"]["newly_submitted_groups"] == ["g_teacher"]

    @pytest.mark.asyncio
    async def test_a_note_without_an_exercise_is_submitted_the_same_way(self):
        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.ok((_copy_entry(), ShareOutcome(submitted_groups=("g_t",)))),
            ]
        )
        result = await self._ingest(service, _note("submitted", fulfills_exercise_uid=None))
        assert result.is_ok, result.expect_error()
        copy_request, _ = self._copy_call(service)
        assert copy_request.fulfills_exercise_uid is None
        assert copy_request.pipeline == Pipeline.TEACHER_REVIEW
        assert result.value["relationships_created"] == 0  # no newly created link, no edge

    @pytest.mark.asyncio
    async def test_a_share_only_audience_files_a_none_copy_stamped_submitted(self):
        """No feedback target → pipeline none (AI is never sync-triggered);
        the copy still says ``submitted``."""
        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.ok((_copy_entry(), ShareOutcome(shared_users=("user_bob",)))),
            ]
        )
        result = await self._ingest(service, _note("submitted", audience=["user:Bob"]))
        assert result.is_ok, result.expect_error()
        copy_request, _ = self._copy_call(service)
        assert copy_request.pipeline == Pipeline.NONE
        assert copy_request.status == EntityStatus.SUBMITTED
        assert copy_request.audience.share_users == ("Bob",)

    @pytest.mark.asyncio
    async def test_an_idle_resync_while_submitted_files_nothing(self):
        service = self._service(
            [Result.ok((_living_entry(), ShareOutcome()))],
            latest={"uid": "ue_copy_1", "submission_fingerprint": _copy_fingerprint()},
        )
        result = await self._ingest(service, _note("submitted"))
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 1  # the living upsert only
        service.get_latest_copy_of_note.assert_awaited_once_with("user_1", NOTE_UID)
        assert result.value["submitted_copy_uid"] is None
        assert result.value["nodes_created"] == 1
        assert result.value["share_outcome"]["newly_submitted_groups"] == []

    @pytest.mark.parametrize(
        "change",
        [
            {"content": "- buy oat milk"},
            {"audience": ["teachers", "user:Bob"]},
            {"fulfills_exercise_uid": "ex_other"},
            {"private": True},
            {"tags": ["draft"]},
        ],
    )
    @pytest.mark.asyncio
    async def test_any_authored_change_while_submitted_files_a_new_copy(self, change):
        """The whole snapshot is compared, not the content alone: a new
        audience or exercise target is a new submission (a filed copy is frozen)."""
        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.ok((_copy_entry("ue_copy_2"), ShareOutcome(submitted_groups=("g_t",)))),
            ],
            latest={"uid": "ue_copy_1", "submission_fingerprint": _copy_fingerprint()},
        )
        result = await self._ingest(service, _note("submitted", **change))
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 2
        assert result.value["submitted_copy_uid"] == "ue_copy_2"

    @pytest.mark.asyncio
    async def test_the_same_audience_in_another_order_is_the_same_submission(self):
        latest_fp = _copy_fingerprint(audience=["teachers", "user:Bob"])
        service = self._service(
            [Result.ok((_living_entry(), ShareOutcome()))],
            latest={"uid": "ue_copy_1", "submission_fingerprint": latest_fp},
        )
        result = await self._ingest(service, _note("submitted", audience=["user:Bob", "teachers"]))
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 1

    @pytest.mark.asyncio
    async def test_the_private_flag_rides_on_the_copy(self):
        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.ok((_copy_entry(), ShareOutcome(submitted_groups=("g_t",)))),
            ]
        )
        result = await self._ingest(service, _note("submitted", private=True))
        assert result.is_ok, result.expect_error()
        copy_request, copy_of = self._copy_call(service)
        assert copy_request.private is True
        assert copy_of.fingerprint == _copy_fingerprint(private=True)

    @pytest.mark.asyncio
    async def test_submitted_with_audience_private_has_nothing_to_submit_to(self):
        """An error on the non-content ``submission`` field: the note synced,
        the copy did not — the sync reports it and retries."""
        service = self._service([Result.ok((_living_entry(), ShareOutcome()))])
        result = await self._ingest(service, _note("submitted", audience="private"))
        assert result.is_error
        error = result.expect_error()
        assert error.details["field"] == SUBMISSION_FIELD
        assert "nothing to" in error.message
        assert service.create_entry.await_count == 1  # the note still synced
        service.get_latest_copy_of_note.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_private_pipeline_note_cannot_be_shared_through_its_copy(self):
        """The note's pipeline privacy travels with its words — the copy's own
        pipeline would otherwise let a ``reference`` note be shared."""
        service = self._service(
            [Result.ok((_living_entry(pipeline=Pipeline.REFERENCE), ShareOutcome()))]
        )
        result = await self._ingest(
            service, _note("submitted", pipeline="reference", audience=["group:g1"])
        )
        assert result.is_error
        assert result.expect_error().details["field"] == SUBMISSION_FIELD
        assert service.create_entry.await_count == 1

    @pytest.mark.asyncio
    async def test_a_refused_copy_is_reported_on_the_submission_field(self):
        """``create_entry``'s own validation refusals (zero reach, a share on a
        private entry) are re-fielded: never classified as an ignored note."""
        from core.utils.result_simplified import Errors

        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.fail(
                    Errors.validation("Submission reached no teacher", field="feedback_target")
                ),
            ]
        )
        result = await self._ingest(service, _note("submitted"))
        assert result.is_error
        error = result.expect_error()
        assert error.details["field"] == SUBMISSION_FIELD
        assert "reached no teacher" in error.message
        service.delete_entry.assert_not_awaited()  # compensation is create_entry's

    @pytest.mark.asyncio
    async def test_a_non_validation_copy_failure_passes_through(self):
        from core.utils.result_simplified import ErrorCategory, Errors

        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.fail(Errors.forbidden(action="submit for exercise", reason="not yours")),
            ]
        )
        result = await self._ingest(service, _note("submitted"))
        assert result.is_error
        assert result.expect_error().category == ErrorCategory.FORBIDDEN

    @pytest.mark.asyncio
    async def test_a_vault_note_with_an_exercise_never_enters_the_turn_in_branch(self):
        """First sync, no authored uid: the door mints one, so ``create_entry``
        upserts a living draft instead of filing the note itself."""
        service = self._service([Result.ok((_living_entry(), ShareOutcome()))])
        result = await self._ingest(service, _note("in process", uid=None))
        assert result.is_ok, result.expect_error()
        request = service.create_entry.await_args.kwargs["request"]
        assert request.uid is not None
        assert request.fulfills_exercise_uid == "ex_list_tasks"

    @pytest.mark.asyncio
    async def test_a_script_submission_without_uid_is_filed_directly(self):
        """A relative path (scripts, tests) with no uid is no living note: the
        entry itself is the submission — no copy, the authored status flows."""
        service = self._service(
            [Result.ok((_copy_entry(), ShareOutcome(submitted_groups=("g_t",))))]
        )
        data = _note("submitted", uid=None, pipeline="teacher_review")
        result = await self._ingest(service, data, path=Path("tasks-list.md"))
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 1
        request = service.create_entry.await_args.kwargs["request"]
        assert request.status == EntityStatus.SUBMITTED
        service.get_latest_copy_of_note.assert_not_called()


class TestPeriodicUidDerivation:
    """Vault frontmatter → the derived ``ue:{kind}:{user}:{period_key}`` uid.

    One frontmatter field per kind is the authoring contract
    (``docs/patterns/UNIFIED_INGESTION_GUIDE.md``); the derived uid must match
    the one ``UserEntryService.ensure_periodic_note`` mints for the same period,
    or the vault note and the in-app note become two nodes.
    """

    @staticmethod
    async def _uid(data: dict[str, object], kind: str) -> str | None:
        result = build_user_entry_request(
            data={"pipeline": "extract_activities", "metadata": {"entry_kind": kind}, **data},
            file_path=Path(f"/vault/periodic_notes/{kind}.md"),
            user_uid="user_1",
        )
        assert result.is_ok
        return result.value.uid

    @pytest.mark.asyncio
    async def test_quarterly_derives_from_quarter_of(self):
        assert await self._uid({"quarter_of": "2026-Q3"}, "quarterly") == (
            "ue:quarterly:user_1:2026-Q3"
        )

    @pytest.mark.asyncio
    async def test_yearly_derives_from_year_of_however_yaml_typed_it(self):
        """``year_of: 2026`` parses as an int; ``"2026"`` as a str. One year."""
        assert await self._uid({"year_of": 2026}, "yearly") == "ue:yearly:user_1:2026"
        assert await self._uid({"year_of": "2026"}, "yearly") == "ue:yearly:user_1:2026"

    @pytest.mark.asyncio
    async def test_yearly_normalizes_a_date_typed_year(self):
        """A bare ``year_of: 2026-01-01`` coerces to a date — take its year."""
        assert await self._uid({"year_of": date(2026, 1, 1)}, "yearly") == "ue:yearly:user_1:2026"

    @pytest.mark.asyncio
    async def test_ride_along_daily_weekly_monthly_still_derive(self):
        """The three kinds this change extends keep their existing contracts."""
        assert await self._uid({"date": date(2026, 8, 4)}, "daily") == "ue:daily:user_1:2026-08-04"
        assert await self._uid({"week_of": "2026-W32"}, "weekly") == "ue:weekly:user_1:2026-W32"
        # ``month_of: 2026-08`` coerces to a date; truncated back to YYYY-MM.
        assert await self._uid({"month_of": date(2026, 8, 1)}, "monthly") == (
            "ue:monthly:user_1:2026-08"
        )

    @pytest.mark.asyncio
    async def test_missing_period_field_mints_fresh_rather_than_guessing(self):
        """No ``quarter_of``/``year_of`` → no derived identity, never a guess
        at "the current quarter" (which would fuse two periods' notes): the
        note is a plain living draft on a minted uid."""
        for kind in ("quarterly", "yearly"):
            uid = await self._uid({}, kind)
            assert uid is not None and uid.startswith("ue_"), kind
