"""Tests for FormSubmissionService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus
from core.models.forms.form_submission import FormSubmission
from core.models.forms.form_template import FormTemplate
from core.services.forms.form_submission_service import FormSubmissionService
from core.utils.result_simplified import ErrorCategory, Errors, Result


def _make_template(**kwargs):
    defaults = {
        "uid": "ft_test_123",
        "title": "Feedback Form",
        "form_schema": (
            {"name": "q1", "type": "text", "label": "Q1", "required": True},
            {"name": "q2", "type": "select", "label": "Q2", "options": ["a", "b"]},
        ),
    }
    defaults.update(kwargs)
    return FormTemplate(**defaults)


def _make_submission(**kwargs):
    defaults = {
        "uid": "fs_test_123",
        "title": "My Response",
        "user_uid": "user_1",
        "form_template_uid": "ft_test_123",
        "form_data": {"q1": "answer", "q2": "a"},
        "status": EntityStatus.COMPLETED,
    }
    defaults.update(kwargs)
    return FormSubmission(**defaults)


def _make_service(backend=None, event_bus=None, sharing_service=None, template_service=None):
    backend = backend or MagicMock()
    template_service = template_service or MagicMock()
    # submit_form awaits this whenever no explicit audience is given. A bare
    # MagicMock attribute is not awaitable, so default it here rather than in
    # every test that only cares about some other part of submit.
    if not isinstance(backend.share_with_default_audience, AsyncMock):
        backend.share_with_default_audience = AsyncMock(return_value=Result.ok([]))
    return FormSubmissionService(
        backend=backend,
        form_template_service=template_service,
        event_bus=event_bus,
        sharing_service=sharing_service,
    )


class TestSubmitForm:
    @pytest.mark.asyncio
    async def test_submit_success(self):
        template = _make_template()
        template_service = MagicMock()
        template_service.get = AsyncMock(return_value=Result.ok(template))

        submission = _make_submission()
        backend = MagicMock()
        backend.create_with_relationships = AsyncMock(return_value=Result.ok(submission))

        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()

        service = _make_service(
            backend=backend,
            event_bus=event_bus,
            template_service=template_service,
        )

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
        )

        assert result.is_ok
        assert result.value.form_data == {"q1": "answer", "q2": "a"}
        assert result.value.status == EntityStatus.COMPLETED
        backend.create_with_relationships.assert_awaited_once()
        # Sharer attribution (arc 2 C4): the submission crosses the boundary
        # stamped with its submitting user as creator.
        created = backend.create_with_relationships.call_args[0][0]
        assert created.created_by == "user_1"

    @pytest.mark.asyncio
    async def test_submit_template_not_found(self):
        template_service = MagicMock()
        template_service.get = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="FormTemplate", identifier="ft_x"))
        )
        service = _make_service(template_service=template_service)

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_x",
            form_data={"q1": "answer"},
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_submit_validation_fails_missing_required(self):
        """Submission rejected when required field is missing."""
        template = _make_template()
        template_service = MagicMock()
        template_service.get = AsyncMock(return_value=Result.ok(template))

        service = _make_service(template_service=template_service)

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q2": "a"},  # q1 is required but missing
        )

        assert result.is_error
        assert "validation failed" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_submit_validation_fails_invalid_select(self):
        """Submission rejected when select value not in options."""
        template = _make_template()
        template_service = MagicMock()
        template_service.get = AsyncMock(return_value=Result.ok(template))

        service = _make_service(template_service=template_service)

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "invalid_option"},
        )

        assert result.is_error
        assert "not in allowed options" in str(result.error)

    @pytest.mark.asyncio
    async def test_submit_validation_fails_unknown_field(self):
        """Submission rejected when unknown fields are included."""
        template = _make_template()
        template_service = MagicMock()
        template_service.get = AsyncMock(return_value=Result.ok(template))

        service = _make_service(template_service=template_service)

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a", "hacker_field": "injected"},
        )

        assert result.is_error
        assert "Unknown field" in str(result.error)

    @pytest.mark.asyncio
    async def test_submit_publishes_event(self):
        template = _make_template()
        template_service = MagicMock()
        template_service.get = AsyncMock(return_value=Result.ok(template))

        submission = _make_submission()
        backend = MagicMock()
        backend.create_with_relationships = AsyncMock(return_value=Result.ok(submission))

        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()

        service = _make_service(
            backend=backend,
            event_bus=event_bus,
            template_service=template_service,
        )

        await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
        )

        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert event.event_type == "form.submitted"
        assert event.user_uid == "user_1"
        assert event.template_uid == "ft_test_123"

    @pytest.mark.asyncio
    async def test_submit_with_custom_title(self):
        template = _make_template()
        template_service = MagicMock()
        template_service.get = AsyncMock(return_value=Result.ok(template))

        submission = _make_submission(title="My Custom Title")
        backend = MagicMock()
        backend.create_with_relationships = AsyncMock(return_value=Result.ok(submission))

        service = _make_service(backend=backend, template_service=template_service)

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
            title="My Custom Title",
        )

        assert result.is_ok
        assert result.value.title == "My Custom Title"

    @pytest.mark.asyncio
    async def test_submit_stores_schema_hash(self):
        """Verify template_schema_hash is a 64-char hex string on the submission."""
        template = _make_template()
        template_service = MagicMock()
        template_service.get = AsyncMock(return_value=Result.ok(template))

        # Return the submission passed to create_with_relationships
        async def capture_create(sub, _user_uid, _ft_uid):
            return Result.ok(sub)

        backend = MagicMock()
        backend.create_with_relationships = AsyncMock(side_effect=capture_create)

        service = _make_service(backend=backend, template_service=template_service)

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
        )

        assert result.is_ok
        assert result.value.template_schema_hash is not None
        assert len(result.value.template_schema_hash) == 64
        assert all(c in "0123456789abcdef" for c in result.value.template_schema_hash)

    @pytest.mark.asyncio
    async def test_atomic_create_failure_returns_error(self):
        """When create_with_relationships fails, submit_form returns the error."""
        template = _make_template()
        template_service = MagicMock()
        template_service.get = AsyncMock(return_value=Result.ok(template))

        backend = MagicMock()
        backend.create_with_relationships = AsyncMock(
            return_value=Result.fail(Errors.database("create_with_relationships", "User not found"))
        )

        service = _make_service(backend=backend, template_service=template_service)

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
        )

        assert result.is_error


class TestGetSubmission:
    @pytest.mark.asyncio
    async def test_get_success(self):
        submission = _make_submission()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(submission))
        service = _make_service(backend=backend)

        result = await service.get_submission("fs_test_123", "user_1")

        assert result.is_ok
        assert result.value.uid == "fs_test_123"

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.get_submission("fs_nonexistent", "user_1")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_get_wrong_owner_returns_not_found(self):
        """Ownership check returns 404 (not 403) per SKUEL pattern."""
        submission = _make_submission(user_uid="user_1")
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(submission))
        service = _make_service(backend=backend)

        result = await service.get_submission("fs_test_123", "other_user")

        assert result.is_error


class TestDeleteSubmission:
    @pytest.mark.asyncio
    async def test_delete_success(self):
        submission = _make_submission()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(submission))
        backend.delete = AsyncMock(return_value=Result.ok(True))

        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()

        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.delete_submission("fs_test_123", "user_1")

        assert result.is_ok
        backend.delete.assert_awaited_once()
        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert event.event_type == "form_submission.deleted"

    @pytest.mark.asyncio
    async def test_delete_wrong_owner_blocked(self):
        submission = _make_submission(user_uid="user_1")
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(submission))
        backend.delete = AsyncMock()
        service = _make_service(backend=backend)

        result = await service.delete_submission("fs_test_123", "other_user")

        assert result.is_error
        backend.delete.assert_not_awaited()


class TestShareSubmission:
    @pytest.mark.asyncio
    async def test_share_with_group(self):
        submission = _make_submission()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(submission))

        sharing_service = MagicMock()
        sharing_service.share_with_group = AsyncMock(return_value=Result.ok(True))

        service = _make_service(backend=backend, sharing_service=sharing_service)

        result = await service.share_submission(
            uid="fs_test_123",
            user_uid="user_1",
            group_uid="group_1",
        )

        assert result.is_ok
        sharing_service.share_with_group.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_share_with_recipients(self):
        submission = _make_submission()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(submission))

        sharing_service = MagicMock()
        sharing_service.share = AsyncMock(return_value=Result.ok(True))

        service = _make_service(backend=backend, sharing_service=sharing_service)

        result = await service.share_submission(
            uid="fs_test_123",
            user_uid="user_1",
            recipient_uids=["user_2", "user_3"],
        )

        assert result.is_ok
        assert sharing_service.share.await_count == 2

    @pytest.mark.asyncio
    async def test_share_with_admin(self):
        submission = _make_submission()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(submission))
        backend.find_admin_user_uid = AsyncMock(return_value=Result.ok("admin_user"))

        sharing_service = MagicMock()
        sharing_service.share = AsyncMock(return_value=Result.ok(True))

        service = _make_service(backend=backend, sharing_service=sharing_service)

        result = await service.share_submission(
            uid="fs_test_123",
            user_uid="user_1",
            share_with_admin=True,
        )

        assert result.is_ok
        sharing_service.share.assert_awaited_once()


class TestDefaultAudienceOnSubmit:
    """What an *absent* audience means depends on who is asking.

    The PathStep-embedded form has no audience controls, so its submitter had
    no way to say "my teachers" — and teacher reads are gated on share edges,
    so without a default the response reaches nobody. The submit API does offer
    those controls, so an empty audience there is a deliberate choice to stay
    private, and auto-sharing it would publish the answers to a whole
    classroom. Only the caller can tell the two apart.
    """

    @staticmethod
    def _submit_deps():
        template_service = MagicMock()
        template_service.get = AsyncMock(return_value=Result.ok(_make_template()))
        backend = MagicMock()
        backend.create_with_relationships = AsyncMock(return_value=Result.ok(_make_submission()))
        backend.share_with_default_audience = AsyncMock(
            return_value=Result.ok([{"group_uid": "group_x"}, {"group_uid": "group_y"}])
        )
        sharing_service = MagicMock()
        sharing_service.share_with_group = AsyncMock(return_value=Result.ok(True))
        sharing_service.share = AsyncMock(return_value=Result.ok(True))
        return template_service, backend, sharing_service

    @pytest.mark.asyncio
    async def test_the_embedded_form_gets_the_default_audience(self):
        template_service, backend, sharing_service = self._submit_deps()
        service = _make_service(
            backend=backend,
            template_service=template_service,
            sharing_service=sharing_service,
        )

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
            use_default_audience=True,
        )

        assert result.is_ok
        # The audience is resolved for the UID submit_form generated, not for
        # whatever the backend stub happened to echo back.
        created_uid = backend.create_with_relationships.await_args.args[0].uid
        backend.share_with_default_audience.assert_awaited_once_with(created_uid)

    @pytest.mark.asyncio
    async def test_an_api_submit_with_no_audience_stays_private(self):
        """The submit API exposes group_uid/recipient_uids, so leaving them
        empty is a choice. Defaulting here would publish a response its author
        meant only for themselves to their entire classroom."""
        template_service, backend, sharing_service = self._submit_deps()
        service = _make_service(
            backend=backend,
            template_service=template_service,
            sharing_service=sharing_service,
        )

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
        )

        assert result.is_ok
        backend.share_with_default_audience.assert_not_awaited()
        sharing_service.share_with_group.assert_not_awaited()
        sharing_service.share.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_default_audience_is_one_atomic_write(self):
        """Not a per-group loop. A half-written audience is invisible to the
        backfill, which only repairs submissions that have none — so the
        stranded classroom would never be repaired."""
        template_service, backend, sharing_service = self._submit_deps()
        service = _make_service(
            backend=backend,
            template_service=template_service,
            sharing_service=sharing_service,
        )

        await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
            use_default_audience=True,
        )

        assert backend.share_with_default_audience.await_count == 1
        sharing_service.share_with_group.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_explicit_audience_is_not_widened_by_the_default(self):
        """An explicitly narrow share stays narrow. Falling back to the default
        here would re-open the hole this PR closes.

        ``use_default_audience=True`` is passed deliberately: without it the
        default could not have applied anyway, and the test would pass while
        asserting nothing.
        """
        template_service, backend, sharing_service = self._submit_deps()
        service = _make_service(
            backend=backend,
            template_service=template_service,
            sharing_service=sharing_service,
        )

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
            group_uid="group_x",
            use_default_audience=True,
        )

        assert result.is_ok
        shared_groups = {
            call.kwargs["group_uid"] for call in sharing_service.share_with_group.await_args_list
        }
        assert shared_groups == {"group_x"}
        backend.share_with_default_audience.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_audience_write_failure_fails_the_submit(self):
        """A failed default audience is not a survivable partial state.

        It is the submission's *only* audience, so the write failing leaves it
        visible to nobody. Reporting success would tell the learner their
        answer reached their teacher when it reached no one.
        """
        template_service, backend, sharing_service = self._submit_deps()
        event_bus = MagicMock()
        event_bus.publish = AsyncMock()
        backend.share_with_default_audience = AsyncMock(
            return_value=Result.fail(Errors.database(operation="share", message="down"))
        )
        service = _make_service(
            backend=backend,
            template_service=template_service,
            sharing_service=sharing_service,
            event_bus=event_bus,
        )

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
            use_default_audience=True,
        )

        assert result.is_error
        backend.share_with_default_audience.assert_awaited_once()
        # And no FormSubmitted goes out for a submission nobody can read.
        event_bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_submitter_in_no_group_is_not_an_error(self):
        """An empty audience is legitimate — the student studies nowhere — and
        must not be conflated with the write failing."""
        template_service, backend, sharing_service = self._submit_deps()
        backend.share_with_default_audience = AsyncMock(return_value=Result.ok([]))
        service = _make_service(
            backend=backend,
            template_service=template_service,
            sharing_service=sharing_service,
        )

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer", "q2": "a"},
            use_default_audience=True,
        )

        assert result.is_ok


class TestVerifyTeacherAccess:
    """The Model B gate's error contract, which the route branches on."""

    @pytest.mark.asyncio
    async def test_shared_with_an_owned_group_is_allowed(self):
        backend = MagicMock()
        backend.verify_teacher_submission_access = AsyncMock(
            return_value=Result.ok([{"group_uid": "group_x"}])
        )
        service = _make_service(backend=backend)

        result = await service.verify_teacher_access("fs_test_123", "teacher_a")

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_no_matching_share_is_forbidden_not_a_fault(self):
        """A refusal must be FORBIDDEN — the route maps only that to 404, and
        maps anything else to 503 so an outage is not reported as 'no such
        submission'."""
        backend = MagicMock()
        backend.verify_teacher_submission_access = AsyncMock(return_value=Result.ok([]))
        service = _make_service(backend=backend)

        result = await service.verify_teacher_access("fs_test_123", "teacher_b")

        assert result.is_error
        assert result.expect_error().category is ErrorCategory.FORBIDDEN

    @pytest.mark.asyncio
    async def test_backend_fault_keeps_its_own_category(self):
        backend = MagicMock()
        backend.verify_teacher_submission_access = AsyncMock(
            return_value=Result.fail(Errors.database(operation="verify", message="Neo4j down"))
        )
        service = _make_service(backend=backend)

        result = await service.verify_teacher_access("fs_test_123", "teacher_a")

        assert result.is_error
        assert result.expect_error().category is not ErrorCategory.FORBIDDEN

    @pytest.mark.asyncio
    async def test_share_without_service_warns(self):
        submission = _make_submission()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(submission))
        service = _make_service(backend=backend)  # no sharing_service

        result = await service.share_submission(
            uid="fs_test_123",
            user_uid="user_1",
            group_uid="group_1",
        )

        # Should still succeed but log warning
        assert result.is_ok
