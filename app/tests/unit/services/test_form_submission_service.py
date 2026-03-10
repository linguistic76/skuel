"""Tests for FormSubmissionService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus
from core.models.forms.form_submission import FormSubmission
from core.models.forms.form_template import FormTemplate
from core.services.forms.form_submission_service import FormSubmissionService
from core.utils.result_simplified import Errors, Result


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
    return FormSubmissionService(
        backend=backend,
        event_bus=event_bus,
        sharing_service=sharing_service,
        form_template_service=template_service,
    )


class TestSubmitForm:
    @pytest.mark.asyncio
    async def test_submit_success(self):
        template = _make_template()
        template_service = MagicMock()
        template_service.get_form_template = AsyncMock(return_value=Result.ok(template))

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

    @pytest.mark.asyncio
    async def test_submit_template_not_found(self):
        template_service = MagicMock()
        template_service.get_form_template = AsyncMock(
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
        template_service.get_form_template = AsyncMock(return_value=Result.ok(template))

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
        template_service.get_form_template = AsyncMock(return_value=Result.ok(template))

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
        template_service.get_form_template = AsyncMock(return_value=Result.ok(template))

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
        template_service.get_form_template = AsyncMock(return_value=Result.ok(template))

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
        template_service.get_form_template = AsyncMock(return_value=Result.ok(template))

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
        template_service.get_form_template = AsyncMock(return_value=Result.ok(template))

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
        template_service.get_form_template = AsyncMock(return_value=Result.ok(template))

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
        backend.execute_query = AsyncMock(return_value=Result.ok([{"uid": "admin_user"}]))

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


class TestFallbackTemplateResolution:
    """Test _get_template fallback when form_template_service is not wired."""

    @pytest.mark.asyncio
    async def test_fallback_to_backend_query(self):
        """When template_service is None, service queries backend directly."""
        submission = _make_submission(form_data={"q1": "answer"})
        backend = MagicMock()
        # First call: template lookup; create_with_relationships for atomic create
        backend.execute_query = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "ft": {
                            "uid": "ft_test_123",
                            "title": "Test",
                            "entity_type": "form_template",
                            "form_schema": '[{"name": "q1", "type": "text", "label": "Q1"}]',
                        }
                    }
                ]
            ),
        )
        backend.create_with_relationships = AsyncMock(return_value=Result.ok(submission))

        service = _make_service(backend=backend)  # no template_service

        result = await service.submit_form(
            user_uid="user_1",
            form_template_uid="ft_test_123",
            form_data={"q1": "answer"},
        )

        assert result.is_ok
        backend.create_with_relationships.assert_awaited_once()
