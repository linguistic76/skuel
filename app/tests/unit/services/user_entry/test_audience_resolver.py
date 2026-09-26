"""Tests for AudienceResolver — the one audience applier (ADR-088).

The three steps ``create_entry`` runs: ``validate`` (the pure rules),
``validate_references`` (every target authorised before the first write)
and ``resolve_and_share`` (the writes, of validated targets only).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.audience import AudienceSpec
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.user_entry.audience_resolver import (
    FEEDBACK_TARGET_FIELD,
    AudienceResolver,
    ResolvedAudience,
    ShareOutcome,
)
from core.utils.result_simplified import Errors, Result

USER = "user_1"


def _make_sharing_service(*, co_members: dict[str, str] | None = None, reachable=None) -> MagicMock:
    """A sharing service whose lookups answer from small tables.

    ``co_members`` maps username → uid for the co-members the owner may
    share with; ``reachable`` is the set of group uids the owner may share
    with or submit to (``None`` = every group named).
    """
    svc = MagicMock()
    svc.share = AsyncMock(return_value=Result.ok(True))
    svc.share_with_group = AsyncMock(return_value=Result.ok(True))
    # The feedback request; the bool is ``created`` (True = a new link).
    svc.submit_to_group = AsyncMock(return_value=Result.ok(True))
    table = co_members or {}

    async def _resolve(owner_uid: str, username: str) -> Result[str | None]:
        return Result.ok(table.get(username))

    async def _reachable(user_uid: str, group_uids: list[str]) -> Result[frozenset[str]]:
        if reachable is None:
            return Result.ok(frozenset(group_uids))
        return Result.ok(frozenset(g for g in group_uids if g in reachable))

    svc.resolve_co_member = AsyncMock(side_effect=_resolve)
    svc.reachable_groups = AsyncMock(side_effect=_reachable)
    backend = MagicMock()
    backend.query_exercise_groups_for_member = AsyncMock(return_value=Result.ok([]))
    backend.query_default_groups_for_curriculum_submission = AsyncMock(return_value=Result.ok([]))
    backend.query_user_can_use_exercise = AsyncMock(return_value=Result.ok(True))
    backend.query_entity_owner = AsyncMock(return_value=Result.ok(USER))
    svc.backend = backend
    return svc


def _make_group_service(groups=None) -> MagicMock:
    svc = MagicMock()
    svc.get_user_groups = AsyncMock(return_value=Result.ok(groups or []))
    return svc


def _group(uid: str) -> MagicMock:
    g = MagicMock()
    g.uid = uid
    return g


def _req(pipeline: Pipeline = Pipeline.NONE, audience=None, **kwargs) -> UserEntryCreateRequest:
    return UserEntryCreateRequest(title="x", pipeline=pipeline, audience=audience, **kwargs)


# =============================================================================
# 1. validate — the pure rules
# =============================================================================


class TestValidate:
    def setup_method(self):
        self.resolver = AudienceResolver(sharing_service=None, group_service=None)

    def test_none_pipeline_with_no_audience_is_ok(self):
        assert self.resolver.validate(_req()).is_ok

    def test_teacher_review_with_no_audience_is_ok_here(self):
        """An absent audience means ``teachers``; whether that reaches anyone
        is ``validate_references``' question."""
        assert self.resolver.validate(_req(Pipeline.TEACHER_REVIEW)).is_ok

    @pytest.mark.parametrize("audience", ["teachers", "teacher:g1", ["teachers", "group:g2"]])
    def test_teacher_review_with_a_feedback_target_passes(self, audience):
        assert self.resolver.validate(_req(Pipeline.TEACHER_REVIEW, audience)).is_ok

    @pytest.mark.parametrize("audience", ["group:g1", "user:bob", "public", "private"])
    def test_teacher_review_with_an_explicit_audience_naming_no_teacher_is_refused(self, audience):
        """A share puts the entry in no queue (R5): refused with guidance that
        names ``teacher:<group_uid>``, on a non-content field so the vault sync
        reports it as an error, not an ignored note."""
        result = self.resolver.validate(_req(Pipeline.TEACHER_REVIEW, audience))
        assert result.is_error
        error = result.expect_error()
        assert "teacher:<group_uid>" in error.message
        assert error.details["field"] == FEEDBACK_TARGET_FIELD

    @pytest.mark.parametrize("pipeline", [Pipeline.REFERENCE, Pipeline.TRANSCRIBE_AND_STRUCTURE])
    @pytest.mark.parametrize("audience", ["group:g1", "user:bob", "public"])
    def test_a_private_pipeline_refuses_every_share(self, pipeline, audience):
        result = self.resolver.validate(_req(pipeline, audience))
        assert result.is_error
        assert result.expect_error().details["field"] == "audience"
        assert "private" in result.expect_error().message

    @pytest.mark.parametrize("pipeline", [Pipeline.REFERENCE, Pipeline.TRANSCRIBE_AND_STRUCTURE])
    def test_a_private_pipeline_still_allows_a_feedback_request(self, pipeline):
        """Submit is not Share (ADR-088 §1); the request writes no link off
        TEACHER_REVIEW, but it is not refused."""
        assert self.resolver.validate(_req(pipeline, "teachers")).is_ok

    @pytest.mark.parametrize("audience", ["group:g1", "user:bob", "public"])
    def test_a_private_entry_cannot_be_shared(self, audience):
        """``private: true`` refuses Share (amends ADR-054 §5's orthogonality)."""
        result = self.resolver.validate(_req(Pipeline.NONE, audience, private=True))
        assert result.is_error
        assert "private" in result.expect_error().message

    @pytest.mark.parametrize("audience", ["teachers", "teacher:g1"])
    def test_a_private_entry_may_still_ask_for_feedback(self, audience):
        assert self.resolver.validate(_req(Pipeline.TEACHER_REVIEW, audience, private=True)).is_ok

    def test_a_request_and_a_share_side_by_side_are_valid(self):
        assert self.resolver.validate(
            _req(Pipeline.TEACHER_REVIEW, ["teacher:g_teacher", "group:g_class", "user:bob"])
        ).is_ok


# =============================================================================
# 2. validate_references — every target authorised before the first write
# =============================================================================


class TestValidateReferencesAudience:
    @pytest.mark.asyncio
    async def test_a_co_member_username_resolves_to_its_uid(self):
        sharing = _make_sharing_service(co_members={"Alice": "user_alice"})
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(USER, _req(audience="user:Alice"))

        assert result.is_ok
        assert result.value.share_users == (("Alice", "user_alice"),)
        sharing.resolve_co_member.assert_awaited_once_with(USER, "Alice")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("username", ["nobody", "stranger"])
    async def test_unknown_and_non_co_member_get_one_uniform_not_found(self, username):
        """The door discloses nothing about who exists (ADR-088 §7)."""
        sharing = _make_sharing_service(co_members={"Alice": "user_alice"})
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(USER, _req(audience=f"user:{username}"))

        assert result.is_error
        error = result.expect_error()
        assert error.category.value == "not_found"
        assert f"user:{username}" in str(error)

    @pytest.mark.asyncio
    async def test_the_owner_is_never_a_recipient(self):
        sharing = _make_sharing_service(co_members={"me": USER})
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(USER, _req(audience="user:me"))

        assert result.is_error
        assert "not shared with its owner" in result.expect_error().message

    @pytest.mark.asyncio
    async def test_a_mixed_list_refuses_as_a_whole_before_any_write(self):
        sharing = _make_sharing_service(co_members={"Alice": "user_alice"})
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(
            USER, _req(audience=["user:Alice", "user:nobody"])
        )

        assert result.is_error
        sharing.share.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("audience", ["group:g_far", "teacher:g_far"])
    async def test_an_unreachable_group_is_not_found(self, audience):
        sharing = _make_sharing_service(reachable={"g_near"})
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(
            USER,
            _req(Pipeline.TEACHER_REVIEW if "teacher" in audience else Pipeline.NONE, audience),
        )

        assert result.is_error
        assert result.expect_error().category.value == "not_found"
        assert "g_far" in str(result.expect_error())

    @pytest.mark.asyncio
    async def test_reachable_groups_are_checked_in_one_read_across_both_verbs(self):
        sharing = _make_sharing_service(reachable={"g_t", "g_s"})
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(
            USER, _req(Pipeline.TEACHER_REVIEW, ["teacher:g_t", "group:g_s"])
        )

        assert result.is_ok
        assert result.value.teacher_groups == ("g_t",)
        assert result.value.share_groups == ("g_s",)
        sharing.reachable_groups.assert_awaited_once_with(USER, ["g_t", "g_s"])

    @pytest.mark.asyncio
    async def test_public_rides_through(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        result = await resolver.validate_references(USER, _req(audience="public"))
        assert result.is_ok
        assert result.value.public is True

    @pytest.mark.asyncio
    async def test_without_a_sharing_service_a_lookup_audience_fails_closed(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        result = await resolver.validate_references(USER, _req(audience="user:alice"))
        assert result.is_error
        assert result.expect_error().category.value == "forbidden"

    @pytest.mark.asyncio
    async def test_without_a_sharing_service_no_audience_is_ok(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        result = await resolver.validate_references(USER, _req())
        assert result.is_ok
        assert result.value == ResolvedAudience()


class TestValidateReferencesTeachers:
    """``teachers`` — explicit or the TEACHER_REVIEW default — expanded before the write."""

    @pytest.mark.asyncio
    async def test_absent_audience_on_teacher_review_means_teachers(self):
        sharing = _make_sharing_service()
        groups = _make_group_service([_group("g_math"), _group("g_science")])
        resolver = AudienceResolver(sharing_service=sharing, group_service=groups)

        result = await resolver.validate_references(USER, _req(Pipeline.TEACHER_REVIEW))

        assert result.is_ok
        assert result.value.teachers_groups == ("g_math", "g_science")
        assert result.value.submit_groups == ("g_math", "g_science")
        groups.get_user_groups.assert_awaited_once_with(USER, role="student")

    @pytest.mark.asyncio
    async def test_with_an_exercise_teachers_is_the_member_intersection(self):
        sharing = _make_sharing_service()
        sharing.backend.query_exercise_groups_for_member = AsyncMock(
            return_value=Result.ok([{"group_uid": "g_a"}, {"group_uid": "g_b"}])
        )
        groups = _make_group_service([_group("g_other")])
        resolver = AudienceResolver(sharing_service=sharing, group_service=groups)

        result = await resolver.validate_references(
            USER, _req(Pipeline.TEACHER_REVIEW, "teachers", fulfills_exercise_uid="ex_1")
        )

        assert result.is_ok
        assert result.value.submit_groups == ("g_a", "g_b")
        groups.get_user_groups.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_curriculum_exercise_falls_back_to_the_default_group(self):
        """Ruled 2026-07-04, kept: the curriculum turn-in reaches the default
        group's owner (never its members, under SUBMITTED_TO_GROUP)."""
        sharing = _make_sharing_service()
        sharing.backend.query_default_groups_for_curriculum_submission = AsyncMock(
            return_value=Result.ok([{"group_uid": "group_default_admin"}])
        )
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.validate_references(
            USER, _req(Pipeline.TEACHER_REVIEW, fulfills_exercise_uid="ex_curriculum")
        )

        assert result.is_ok
        assert result.value.submit_groups == ("group_default_admin",)

    @pytest.mark.asyncio
    async def test_a_request_reaching_no_teacher_is_refused_before_the_write(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=_make_group_service([]))

        result = await resolver.validate_references(USER, _req(Pipeline.TEACHER_REVIEW))

        assert result.is_error
        error = result.expect_error()
        assert "reached no teacher" in error.message
        assert error.details["field"] == FEEDBACK_TARGET_FIELD

    @pytest.mark.asyncio
    async def test_an_explicit_teacher_group_beside_an_empty_expansion_is_enough(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=_make_group_service([]))

        result = await resolver.validate_references(
            USER, _req(Pipeline.TEACHER_REVIEW, ["teachers", "teacher:g_one"])
        )

        assert result.is_ok
        assert result.value.submit_groups == ("g_one",)

    @pytest.mark.asyncio
    async def test_an_explicit_teacher_group_alone_does_not_expand_teachers(self):
        """A multi-class student who names one teacher is not also filed with
        every other group."""
        sharing = _make_sharing_service()
        groups = _make_group_service([_group("g_other")])
        resolver = AudienceResolver(sharing_service=sharing, group_service=groups)

        result = await resolver.validate_references(
            USER, _req(Pipeline.TEACHER_REVIEW, "teacher:g_one")
        )

        assert result.is_ok
        assert result.value.submit_groups == ("g_one",)
        groups.get_user_groups.assert_not_called()

    @pytest.mark.asyncio
    async def test_teachers_off_pipeline_is_not_expanded_but_explicit_targets_survive(self):
        """On any pipeline but TEACHER_REVIEW ``teachers`` is not expanded (it
        would write no link — PR 1's pipeline-gap contract); an explicit
        ``teacher:`` target is still validated and kept, so a living note can
        hold it for its frozen copy."""
        sharing = _make_sharing_service()
        groups = _make_group_service([_group("g_math")])
        resolver = AudienceResolver(sharing_service=sharing, group_service=groups)

        result = await resolver.validate_references(
            USER, _req(Pipeline.NONE, ["teachers", "teacher:g_one"])
        )

        assert result.is_ok
        assert result.value.teachers_groups == ()
        assert result.value.teacher_groups == ("g_one",)
        groups.get_user_groups.assert_not_called()

    @pytest.mark.asyncio
    async def test_absent_audience_off_pipeline_is_nobody(self):
        sharing = _make_sharing_service()
        groups = _make_group_service([_group("g_math")])
        resolver = AudienceResolver(sharing_service=sharing, group_service=groups)

        result = await resolver.validate_references(USER, _req(Pipeline.LLM_SUMMARY))

        assert result.is_ok
        assert result.value == ResolvedAudience()
        groups.get_user_groups.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_failed_group_lookup_is_returned_not_swallowed(self):
        sharing = _make_sharing_service()
        groups = MagicMock()
        groups.get_user_groups = AsyncMock(
            return_value=Result.fail(Errors.database("lookup", "boom"))
        )
        resolver = AudienceResolver(sharing_service=sharing, group_service=groups)

        result = await resolver.validate_references(USER, _req(Pipeline.TEACHER_REVIEW))

        assert result.is_error
        assert result.expect_error().category.value == "database"


class TestValidateReferencesClaims:
    @pytest.mark.asyncio
    async def test_no_references_is_ok(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        assert (await resolver.validate_references(USER, _req())).is_ok

    @pytest.mark.asyncio
    async def test_exercise_the_user_may_use_passes(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        result = await resolver.validate_references(USER, _req(fulfills_exercise_uid="ex_ok"))
        assert result.is_ok
        sharing.backend.query_user_can_use_exercise.assert_awaited_once_with(
            exercise_uid="ex_ok", user_uid=USER
        )

    @pytest.mark.asyncio
    async def test_exercise_the_user_may_not_use_is_forbidden(self):
        sharing = _make_sharing_service()
        sharing.backend.query_user_can_use_exercise = AsyncMock(return_value=Result.ok(False))
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        result = await resolver.validate_references(USER, _req(fulfills_exercise_uid="ex_no"))
        assert result.is_error
        assert result.expect_error().category.value == "forbidden"

    @pytest.mark.asyncio
    async def test_predecessor_owned_by_another_user_is_forbidden(self):
        sharing = _make_sharing_service()
        sharing.backend.query_entity_owner = AsyncMock(return_value=Result.ok("user_other"))
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        result = await resolver.validate_references(USER, _req(transforms_of_uid="ue_prev"))
        assert result.is_error
        assert result.expect_error().category.value == "forbidden"

    @pytest.mark.asyncio
    async def test_missing_predecessor_is_not_found(self):
        sharing = _make_sharing_service()
        sharing.backend.query_entity_owner = AsyncMock(return_value=Result.ok(None))
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)
        result = await resolver.validate_references(USER, _req(transforms_of_uid="ue_gone"))
        assert result.is_error
        assert result.expect_error().category.value == "not_found"

    @pytest.mark.asyncio
    async def test_without_a_sharing_service_a_reference_fails_closed(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        result = await resolver.validate_references(USER, _req(fulfills_exercise_uid="ex"))
        assert result.is_error
        assert result.expect_error().category.value == "forbidden"


# =============================================================================
# 3. resolve_and_share — the writes
# =============================================================================


class TestResolveAndShare:
    @pytest.mark.asyncio
    async def test_no_sharing_service_returns_empty_outcome(self):
        resolver = AudienceResolver(sharing_service=None, group_service=None)
        result = await resolver.resolve_and_share(
            "ue_1", USER, Pipeline.NONE, ResolvedAudience(share_groups=("g1",))
        )
        assert result.is_ok
        assert result.value == ShareOutcome()

    @pytest.mark.asyncio
    async def test_submit_groups_on_teacher_review_file_feedback_requests(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.resolve_and_share(
            "ue_1",
            USER,
            Pipeline.TEACHER_REVIEW,
            ResolvedAudience(teacher_groups=("g1",), teachers_groups=("g2", "g1")),
        )

        outcome = result.value
        assert outcome.submitted_groups == ("g1", "g2")
        assert outcome.newly_submitted_groups == ("g1", "g2")
        assert outcome.shared_groups == ()
        assert sharing.submit_to_group.await_count == 2
        sharing.share_with_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_share_and_a_request_keep_their_verbs(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.resolve_and_share(
            "ue_1",
            USER,
            Pipeline.TEACHER_REVIEW,
            ResolvedAudience(
                teacher_groups=("g_teacher",),
                share_groups=("g_class",),
                share_users=(("Alice", "user_alice"),),
            ),
        )

        outcome = result.value
        assert outcome.submitted_groups == ("g_teacher",)
        assert outcome.shared_groups == ("g_class",)
        assert outcome.shared_users == ("user_alice",)
        assert sharing.submit_to_group.await_args.kwargs["group_uid"] == "g_teacher"
        assert sharing.share_with_group.await_args.kwargs["group_uid"] == "g_class"
        assert sharing.share.await_args.kwargs["recipient_uid"] == "user_alice"

    @pytest.mark.asyncio
    async def test_only_a_created_person_share_is_newly_shared(self):
        """R10: the bell rings once per new link — a share that already stood is a success, not new."""
        sharing = _make_sharing_service()
        sharing.share = AsyncMock(side_effect=[Result.ok(False), Result.ok(True)])
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.resolve_and_share(
            "ue_1",
            USER,
            Pipeline.NONE,
            ResolvedAudience(share_users=(("Alice", "user_alice"), ("Bob", "user_bob"))),
        )

        outcome = result.value
        assert outcome.shared_users == ("user_alice", "user_bob")
        assert outcome.newly_shared_users == ("user_bob",)
        assert outcome.to_payload()["newly_shared_users"] == ["user_bob"]

    @pytest.mark.asyncio
    async def test_a_matched_request_is_a_success_and_only_a_created_one_is_new(self):
        sharing = _make_sharing_service()
        sharing.submit_to_group = AsyncMock(side_effect=[Result.ok(False), Result.ok(True)])
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.resolve_and_share(
            "ue_1",
            USER,
            Pipeline.TEACHER_REVIEW,
            ResolvedAudience(teacher_groups=("g_existing", "g_new")),
        )

        assert result.value.submitted_groups == ("g_existing", "g_new")
        assert result.value.newly_submitted_groups == ("g_new",)

    @pytest.mark.asyncio
    async def test_submit_groups_are_never_written_off_pipeline(self):
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.resolve_and_share(
            "ue_1", USER, Pipeline.NONE, ResolvedAudience(teacher_groups=("g1",))
        )

        assert result.value.submitted_groups == ()
        assert result.value.withheld == ()
        sharing.submit_to_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_living_note_withholds_teacher_targets_on_any_pipeline(self):
        """A knowledge draft naming ``teacher:g1`` keeps it for the frozen copy
        (R9): reported as withheld, never written, never silently lost."""
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.resolve_and_share(
            "ue_living",
            USER,
            Pipeline.KNOWLEDGE,
            ResolvedAudience(teacher_groups=("g1",), share_groups=("g_class",)),
            living=True,
        )

        outcome = result.value
        assert outcome.withheld == ("teacher:g1",)
        assert outcome.shared_groups == ("g_class",)
        sharing.submit_to_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_refused_write_is_collected_with_the_vocabulary_target(self):
        sharing = _make_sharing_service()
        sharing.share = AsyncMock(return_value=Result.fail(Errors.not_found("User", "user_x")))
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.resolve_and_share(
            "ue_1", USER, Pipeline.NONE, ResolvedAudience(share_users=(("x", "user_x"),))
        )

        outcome = result.value
        assert outcome.shared_users == ()
        assert outcome.any_failure
        assert outcome.failed[0][0] == "user:x"

    @pytest.mark.asyncio
    async def test_a_living_note_withholds_user_and_explicit_teacher_targets(self):
        """R9's window until PR 8: a draft's user: / teacher: targets are
        reported, not applied; group: and the teachers expansion still apply."""
        sharing = _make_sharing_service()
        resolver = AudienceResolver(sharing_service=sharing, group_service=None)

        result = await resolver.resolve_and_share(
            "ue_living",
            USER,
            Pipeline.TEACHER_REVIEW,
            ResolvedAudience(
                teacher_groups=("g_named",),
                teachers_groups=("g_expanded",),
                share_groups=("g_class",),
                share_users=(("Alice", "user_alice"),),
            ),
            living=True,
        )

        outcome = result.value
        assert outcome.withheld == ("user:Alice", "teacher:g_named")
        assert outcome.shared_users == ()
        assert outcome.submitted_groups == ("g_expanded",)
        assert outcome.shared_groups == ("g_class",)
        assert not outcome.any_failure
        sharing.share.assert_not_called()
        assert sharing.submit_to_group.await_args.kwargs["group_uid"] == "g_expanded"


class TestShareOutcome:
    def test_to_payload_shape(self):
        outcome = ShareOutcome(
            submitted_groups=("g1",),
            newly_submitted_groups=("g1",),
            shared_groups=("g2",),
            shared_users=("u1",),
            failed=(("g3", "boom"),),
            withheld=("user:bob",),
        )
        assert outcome.to_payload() == {
            "submitted_groups": ["g1"],
            "newly_submitted_groups": ["g1"],
            "shared_groups": ["g2"],
            "shared_users": ["u1"],
            "newly_shared_users": [],
            "failed": [{"target": "g3", "reason": "boom"}],
            "withheld": ["user:bob"],
        }

    def test_default_outcome_is_empty(self):
        outcome = ShareOutcome()
        assert not outcome.any_success
        assert not outcome.any_failure
        assert outcome.withheld == ()

    def test_a_feedback_request_alone_is_a_success(self):
        assert ShareOutcome(submitted_groups=("g1",)).any_success

    def test_a_withheld_target_is_neither_success_nor_failure(self):
        outcome = ShareOutcome(withheld=("teacher:g1",))
        assert not outcome.any_success
        assert not outcome.any_failure


class TestResolvedAudience:
    def test_submit_groups_are_explicit_first_without_repeats(self):
        resolved = ResolvedAudience(teacher_groups=("g1", "g2"), teachers_groups=("g2", "g3"))
        assert resolved.submit_groups == ("g1", "g2", "g3")

    def test_the_request_model_parses_the_vocabulary(self):
        req = _req(audience=["teachers", "user:Alice"])
        assert req.audience == AudienceSpec(teachers=True, share_users=("Alice",))
