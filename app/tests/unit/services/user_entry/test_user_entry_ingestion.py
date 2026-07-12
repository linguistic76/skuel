"""Tests for user_entry_ingestion (/upload → UserEntryService bridge)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_enums import UserRole
from core.models.user_entry.user_entry import UserEntry
from core.services.ingestion.user_entry_ingestion import (
    build_user_entry_request,
    ingest_user_entry,
)
from core.services.user_entry.audience_resolver import AudienceResolver, ShareOutcome
from core.utils.result_simplified import Result


def _resolver(teachers=None) -> AudienceResolver:
    resolver = AudienceResolver(sharing_service=None, group_service=None)
    resolver.resolve_default_teachers = AsyncMock(return_value=teachers or [])  # type: ignore[method-assign]
    return resolver


def _user_service_for_role(role: UserRole) -> MagicMock:
    """Build a user_service mock whose ``get_user`` returns a User with ``role``."""
    user = MagicMock()
    # Bound method from the real enum — hierarchy-aware, no hand-rolled lambdas.
    user.has_permission = role.has_permission
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


class TestBuildUserEntryRequest:
    @pytest.mark.asyncio
    async def test_missing_pipeline_rejected(self):
        result = await build_user_entry_request(
            data={"title": "x"},
            file_path=Path("reflection.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "pipeline" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_garbled_je_use_rejected(self):
        # A typo'd je_use is an authored scoping intent we can't honor — fail
        # loudly (mirrors the collection-level gate's fail-closed posture).
        result = await build_user_entry_request(
            data={"pipeline": "knowledge", "je_use": "exmplar"},
            file_path=Path("thought.md"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "je_use" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_valid_je_use_accepted(self):
        result = await build_user_entry_request(
            data={"pipeline": "knowledge", "je_use": "understanding", "title": "Me"},
            file_path=Path("thought.md"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_private_true_flows_to_request(self):
        result = await build_user_entry_request(
            data={"pipeline": "knowledge", "private": True, "title": "Secret"},
            file_path=Path("secret.md"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.private is True

    @pytest.mark.asyncio
    async def test_private_absent_defaults_retrievable(self):
        result = await build_user_entry_request(
            data={"pipeline": "knowledge", "title": "Open"},
            file_path=Path("open.md"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.private is False

    @pytest.mark.asyncio
    async def test_garbled_private_rejected(self):
        # A quoted "true" is a string, not a boolean — silently ignoring an
        # authored privacy intent is the one unacceptable failure mode here.
        result = await build_user_entry_request(
            data={"pipeline": "knowledge", "private": "true", "title": "Secret"},
            file_path=Path("secret.md"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "private" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_audio_pipeline_rejected(self):
        result = await build_user_entry_request(
            data={"pipeline": "transcribe_and_structure"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "audio" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_default_audience_expands_to_user_groups(self):
        resolver = _resolver(teachers=["g_a", "g_b"])
        result = await build_user_entry_request(
            data={"pipeline": "teacher_review", "title": "Essay"},
            file_path=Path("essay.yaml"),
            user_uid="user_1",
            audience_resolver=resolver,
        )
        assert result.is_ok
        req = result.value
        assert req.pipeline == Pipeline.TEACHER_REVIEW
        assert req.share_with_groups == ["g_a", "g_b"]
        resolver.resolve_default_teachers.assert_awaited_once_with("user_1")  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_explicit_group_audience(self):
        result = await build_user_entry_request(
            data={"pipeline": "teacher_review", "audience": "group:g_class"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.share_with_groups == ["g_class"]

    @pytest.mark.asyncio
    async def test_audience_group_without_uid_rejected(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "audience": "group:"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "group" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_public_audience_accepted_for_teacher(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "audience": "public"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
            user_service=_user_service_for_role(UserRole.TEACHER),
        )
        assert result.is_ok
        assert result.value.visibility == Visibility.PUBLIC
        assert result.value.share_with_groups == []

    @pytest.mark.asyncio
    async def test_public_audience_rejected_for_registered(self):
        """REGISTERED users cannot publish portfolio-visible content via YAML."""
        result = await build_user_entry_request(
            data={"pipeline": "none", "audience": "public"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
            user_service=_user_service_for_role(UserRole.REGISTERED),
        )
        assert result.is_error
        err = str(result.expect_error()).lower()
        assert "teacher" in err

    @pytest.mark.asyncio
    async def test_public_audience_fail_closed_without_user_service(self):
        """Without a user_service we cannot resolve role — reject rather than publish."""
        result = await build_user_entry_request(
            data={"pipeline": "none", "audience": "public"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
            user_service=None,
        )
        assert result.is_error
        assert "teacher" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_private_audience_no_shares_no_visibility(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "audience": "private"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        req = result.value
        assert req.share_with_groups == []
        assert req.visibility is None

    @pytest.mark.asyncio
    async def test_teacher_review_with_zero_groups_is_rejected_by_validator(self):
        """Student in no groups + TEACHER_REVIEW + no explicit audience →
        validator fails (ADR §3 — no silent no-audience turn-ins)."""
        result = await build_user_entry_request(
            data={"pipeline": "teacher_review"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(teachers=[]),
        )
        assert result.is_error
        assert "audience" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_title_defaults_from_filename(self):
        result = await build_user_entry_request(
            data={"pipeline": "none"},
            file_path=Path("my-deep-reflection.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.title == "My Deep Reflection"

    @pytest.mark.asyncio
    async def test_unknown_pipeline_rejected(self):
        result = await build_user_entry_request(
            data={"pipeline": "does_not_exist"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "pipeline" in str(result.expect_error()).lower()


class TestAuthoredStatusDescriptionOwnership:
    """The door must not silently drop authored frontmatter it understands."""

    @pytest.mark.asyncio
    async def test_authored_status_flows(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "status": "draft"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.status == EntityStatus.DRAFT

    @pytest.mark.asyncio
    async def test_status_alias_in_process_maps_to_active(self):
        """The live fixture's authored spelling — 'in process' → ACTIVE."""
        result = await build_user_entry_request(
            data={"pipeline": "knowledge", "status": "in process"},
            file_path=Path("nous topics.md"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.status == EntityStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_unrecognized_status_fails_loudly(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "status": "vibing"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
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
            result = await build_user_entry_request(
                data=data,
                file_path=Path("x.yaml"),
                user_uid="user_1",
                audience_resolver=_resolver(),
            )
            assert result.is_ok
            assert result.value.status is None

    @pytest.mark.asyncio
    async def test_description_flows(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "description": "Topics taxonomy"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.description == "Topics taxonomy"

    @pytest.mark.asyncio
    async def test_falsy_authored_description_preserved(self):
        """YAML `description: 0` / `description: false` are authored values —
        only a truly absent field maps to None."""
        for raw, expected in ((0, "0"), (False, "False")):
            result = await build_user_entry_request(
                data={"pipeline": "none", "description": raw},
                file_path=Path("x.yaml"),
                user_uid="user_1",
                audience_resolver=_resolver(),
            )
            assert result.is_ok
            assert result.value.description == expected

    @pytest.mark.asyncio
    async def test_missing_description_is_none(self):
        result = await build_user_entry_request(
            data={"pipeline": "none"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.description is None

    @pytest.mark.asyncio
    async def test_ownership_short_form_matches(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "ownership": "linguistic76"},
            file_path=Path("x.yaml"),
            user_uid="user_linguistic76",
            audience_resolver=_resolver(),
        )
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_ownership_canonical_form_matches(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "user_uid": "user_linguistic76"},
            file_path=Path("x.yaml"),
            user_uid="user_linguistic76",
            audience_resolver=_resolver(),
        )
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_ownership_mismatch_rejected(self):
        """A file declaring another owner must fail, never be silently
        claimed by the syncing user."""
        result = await build_user_entry_request(
            data={"pipeline": "none", "ownership": "someone_else"},
            file_path=Path("x.yaml"),
            user_uid="user_linguistic76",
            audience_resolver=_resolver(),
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
        outcome = ShareOutcome(shared_groups=("g_a",))

        service = MagicMock()
        service.audience_resolver = _resolver(teachers=["g_a"])
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
        assert payload["relationships_created"] == 1  # one shared group, no exercise
        assert payload["share_outcome"]["shared_groups"] == ["g_a"]
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
        service.audience_resolver = _resolver()
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
        service.audience_resolver = _resolver()
        service.create_entry = AsyncMock()

        result = await ingest_user_entry(
            data={"title": "no pipeline"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            user_entry_service=service,
        )

        assert result.is_error
        service.create_entry.assert_not_awaited()


def _channel_resolver() -> AudienceResolver:
    """Resolver whose reference guard passes (living channel declarations)."""
    resolver = _resolver()
    resolver.validate_references = AsyncMock(return_value=Result.ok(None))  # type: ignore[method-assign]
    return resolver


def _living_entry(uid: str = "ue.vault.tasks-list") -> UserEntry:
    return UserEntry(
        uid=uid,
        title="My task list",
        user_uid="user_1",
        pipeline=Pipeline.KNOWLEDGE,
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


def _living_file_data(status: str = "in process") -> dict:
    return {
        "pipeline": "knowledge",
        "title": "My task list",
        "uid": "ue:vault:tasks-list",
        "fulfills_exercise_uid": "ex_list_tasks",
        "status": status,
        "content": "- buy milk",
        "audience": "private",
    }


class TestVaultExerciseChannel:
    """The submit-signal branch (R2): living upsert + frozen-copy turn-in."""

    def _service(self, create_side_effects, latest=None) -> MagicMock:
        service = MagicMock()
        service.audience_resolver = _channel_resolver()
        service.create_entry = AsyncMock(side_effect=create_side_effects)
        service.get_latest_entry_for_exercise = AsyncMock(return_value=Result.ok(latest))
        service.delete_entry = AsyncMock(return_value=Result.ok(True))
        return service

    @pytest.mark.asyncio
    async def test_in_process_file_is_single_living_upsert(self):
        service = self._service([Result.ok((_living_entry(), ShareOutcome()))])
        result = await ingest_user_entry(
            data=_living_file_data("in process"),
            file_path=Path("tasks-list.md"),
            user_uid="user_1",
            user_entry_service=service,
        )
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 1
        request = service.create_entry.await_args.kwargs["request"]
        assert request.uid == "ue.vault.tasks-list"  # colon → dot normalization
        assert request.fulfills_exercise_uid == "ex_list_tasks"
        assert request.status == EntityStatus.ACTIVE
        assert result.value["submitted_copy_uid"] is None
        assert result.value["nodes_created"] == 1
        service.get_latest_entry_for_exercise.assert_not_called()

    @pytest.mark.asyncio
    async def test_submitted_flip_files_frozen_copy(self):
        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.ok((_copy_entry(), ShareOutcome(shared_groups=("g_teacher",)))),
            ],
            latest=None,  # first submission — no prior copy
        )
        result = await ingest_user_entry(
            data=_living_file_data("submitted"),
            file_path=Path("tasks-list.md"),
            user_uid="user_1",
            user_entry_service=service,
        )
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 2

        living_request = service.create_entry.await_args_list[0].kwargs["request"]
        # The living entry is NOT itself in teacher review — it stays active
        # while the file says submitted; the copy carries the truthful status.
        assert living_request.status == EntityStatus.ACTIVE
        assert living_request.uid == "ue.vault.tasks-list"

        copy_request = service.create_entry.await_args_list[1].args[0]
        assert copy_request.uid is None  # fresh turn-in path
        assert copy_request.pipeline == Pipeline.TEACHER_REVIEW
        assert copy_request.status is None  # service stamps truthful SUBMITTED
        assert copy_request.fulfills_exercise_uid == "ex_list_tasks"
        assert copy_request.content == "- buy milk"
        assert copy_request.metadata == {"submitted_from_entry": "ue.vault.tasks-list"}

        assert result.value["submitted_copy_uid"] == "ue_copy_1"
        assert result.value["nodes_created"] == 2
        assert result.value["relationships_created"] == 1  # the copy's edge

    @pytest.mark.asyncio
    async def test_idle_resync_while_submitted_files_nothing(self):
        service = self._service(
            [Result.ok((_living_entry(), ShareOutcome()))],
            latest={"uid": "ue_copy_1", "content": "- buy milk", "revision": 1},
        )
        result = await ingest_user_entry(
            data=_living_file_data("submitted"),
            file_path=Path("tasks-list.md"),
            user_uid="user_1",
            user_entry_service=service,
        )
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 1  # living upsert only
        assert result.value["submitted_copy_uid"] is None
        assert result.value["nodes_created"] == 1

    @pytest.mark.asyncio
    async def test_edit_while_submitted_files_new_revision_copy(self):
        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.ok((_copy_entry("ue_copy_2"), ShareOutcome(shared_groups=("g_t",)))),
            ],
            latest={"uid": "ue_copy_1", "content": "- OLD content", "revision": 1},
        )
        result = await ingest_user_entry(
            data=_living_file_data("submitted"),
            file_path=Path("tasks-list.md"),
            user_uid="user_1",
            user_entry_service=service,
        )
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 2
        assert result.value["submitted_copy_uid"] == "ue_copy_2"

    @pytest.mark.asyncio
    async def test_unreachable_teacher_compensates_and_fails(self):
        """A copy with zero successful shares is deleted and surfaced as a
        sync error — never a silent unreviewable turn-in (Mike's invariant)."""
        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.ok((_copy_entry(), ShareOutcome())),  # no shares landed
            ],
            latest=None,
        )
        result = await ingest_user_entry(
            data=_living_file_data("submitted"),
            file_path=Path("tasks-list.md"),
            user_uid="user_1",
            user_entry_service=service,
        )
        assert result.is_error
        err = str(result.expect_error())
        assert "no teacher" in err.lower() or "reached no" in err.lower()
        service.delete_entry.assert_awaited_once_with("ue_copy_1", "user_1")

    @pytest.mark.asyncio
    async def test_copy_create_failure_propagates(self):
        from core.utils.result_simplified import Errors

        service = self._service(
            [
                Result.ok((_living_entry(), ShareOutcome())),
                Result.fail(Errors.validation("no audience was reached", field="audience")),
            ],
            latest=None,
        )
        result = await ingest_user_entry(
            data=_living_file_data("submitted"),
            file_path=Path("tasks-list.md"),
            user_uid="user_1",
            user_entry_service=service,
        )
        assert result.is_error

    @pytest.mark.asyncio
    async def test_submitted_without_uid_is_not_the_channel(self):
        """No deterministic uid → plain turn-in door; no coercion, no copy."""
        entry = _copy_entry()
        service = self._service([Result.ok((entry, ShareOutcome(shared_groups=("g_t",))))])
        data = _living_file_data("submitted")
        del data["uid"]
        data["pipeline"] = "teacher_review"
        result = await ingest_user_entry(
            data=data,
            file_path=Path("tasks-list.md"),
            user_uid="user_1",
            user_entry_service=service,
        )
        assert result.is_ok, result.expect_error()
        assert service.create_entry.await_count == 1
        request = service.create_entry.await_args.kwargs["request"]
        assert request.status == EntityStatus.SUBMITTED  # authored status flows
        service.get_latest_entry_for_exercise.assert_not_called()
