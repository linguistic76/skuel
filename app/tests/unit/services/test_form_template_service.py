"""Tests for FormTemplateService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.forms.form_template import FormTemplate
from core.models.update_contracts import RawChanges
from core.services.forms.form_template_service import FormTemplateService
from core.utils.result_simplified import ErrorCategory, Errors, Result


def _make_template(**kwargs):
    defaults = {
        "uid": "ft_test_123",
        "title": "Feedback Form",
        "entity_type": EntityType.FORM_TEMPLATE,
        "form_schema": ({"name": "q1", "type": "text", "label": "Q1"},),
    }
    defaults.update(kwargs)
    return FormTemplate(**defaults)


def _make_service(backend=None, event_bus=None):
    backend = backend or MagicMock()
    return FormTemplateService(backend=backend, event_bus=event_bus)


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_success(self):
        template = _make_template()
        backend = MagicMock()
        backend.create = AsyncMock(return_value=Result.ok(template))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.create(template)

        assert result.is_ok
        assert result.value.title == "Feedback Form"
        assert result.value.entity_type == EntityType.FORM_TEMPLATE
        backend.create.assert_awaited_once()
        event_bus.publish_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_backend_failure(self):
        template = _make_template()
        backend = MagicMock()
        backend.create = AsyncMock(
            return_value=Result.fail(Errors.database(operation="create", message="DB error"))
        )
        service = _make_service(backend=backend)

        result = await service.create(template)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_create_publishes_event(self):
        template = _make_template()
        backend = MagicMock()
        backend.create = AsyncMock(return_value=Result.ok(template))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        await service.create(template)

        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert event.event_type == "form_template.created"
        assert event.title == "Feedback Form"
        assert event.field_count == 1


class TestGet:
    @pytest.mark.asyncio
    async def test_get_success(self):
        template = _make_template()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(template))
        service = _make_service(backend=backend)

        result = await service.get("ft_test_123")

        assert result.is_ok
        assert result.value.uid == "ft_test_123"

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.get("ft_nonexistent")

        assert result.is_error


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_success(self):
        template = _make_template(title="Updated Title")
        backend = MagicMock()
        backend.update = AsyncMock(return_value=Result.ok(template))
        backend.get = AsyncMock(return_value=Result.ok(template))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.update(
            uid="ft_test_123", updates=RawChanges({"title": "Updated Title"})
        )

        assert result.is_ok
        backend.update.assert_awaited_once()
        event_bus.publish_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_no_changes(self):
        """Empty updates dict still goes through mixin (validates existence)."""
        template = _make_template()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(template))
        backend.update = AsyncMock(return_value=Result.ok(template))
        service = _make_service(backend=backend)

        result = await service.update(uid="ft_test_123", updates=RawChanges({}))

        assert result.is_ok


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_success_no_submissions(self):
        template = _make_template()
        backend = MagicMock()
        backend.count_submissions = AsyncMock(return_value=Result.ok(0))
        backend.get = AsyncMock(return_value=Result.ok(template))
        backend.delete = AsyncMock(return_value=Result.ok(True))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.delete("ft_test_123")

        assert result.is_ok
        backend.delete.assert_awaited_once()
        event_bus.publish_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_blocked_by_submissions(self):
        """Cannot delete a template that has submissions."""
        backend = MagicMock()
        backend.count_submissions = AsyncMock(return_value=Result.ok(3))
        backend.delete = AsyncMock()
        service = _make_service(backend=backend)

        result = await service.delete("ft_test_123")

        assert result.is_error
        assert "3 existing submission" in str(result.error)
        backend.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_guard_counts_every_classroom(self):
        """The delete guard is deliberately NOT classroom-scoped.

        count_submissions takes a teacher scope so reader-facing counts can be
        bounded to the caller's own classrooms. This guard must pass None: a
        scoped count would report 0 for another classroom's submissions and let
        the template be deleted out from under them.
        """
        backend = MagicMock()
        backend.count_submissions = AsyncMock(return_value=Result.ok(3))
        backend.delete = AsyncMock()
        service = _make_service(backend=backend)

        await service.delete("ft_test_123")

        backend.count_submissions.assert_awaited_once_with("ft_test_123", teacher_uid=None)

    @pytest.mark.asyncio
    async def test_delete_refuses_when_the_count_cannot_be_read(self):
        """An unreadable count blocks the delete instead of permitting it.

        The guard is the only thing standing between a delete and orphaned
        RESPONDS_TO_FORM submissions. Reading a backend failure as 0 would let
        a transient outage do exactly the damage the guard exists to prevent —
        fail-safe for a guard means refusing on uncertainty.
        """
        backend = MagicMock()
        backend.count_submissions = AsyncMock(
            return_value=Result.fail(
                Errors.database(operation="count_submissions", message="Neo4j unavailable")
            )
        )
        backend.delete = AsyncMock(return_value=Result.ok(True))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.delete("ft_test_123")

        assert result.is_error
        backend.delete.assert_not_awaited()
        event_bus.publish_async.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_reports_a_failed_count_as_a_fault_not_a_refusal(self):
        """The refusal must name the fault, not invent a submission count.

        Dressing an outage as the business rule would tell an admin to go
        delete submissions that may not exist, and the advice would never
        resolve. An infrastructure fault is not a domain answer.
        """
        backend = MagicMock()
        backend.count_submissions = AsyncMock(
            return_value=Result.fail(
                Errors.database(operation="count_submissions", message="Neo4j unavailable")
            )
        )
        backend.delete = AsyncMock(return_value=Result.ok(True))
        service = _make_service(backend=backend)

        result = await service.delete("ft_test_123")

        error = result.expect_error()
        assert error.category is ErrorCategory.DATABASE
        assert "Neo4j unavailable" in error.message
        assert "existing submission" not in error.message

    @pytest.mark.asyncio
    async def test_delete_publishes_event(self):
        template = _make_template()
        backend = MagicMock()
        backend.count_submissions = AsyncMock(return_value=Result.ok(0))
        backend.get = AsyncMock(return_value=Result.ok(template))
        backend.delete = AsyncMock(return_value=Result.ok(True))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        await service.delete("ft_test_123")

        event = event_bus.publish_async.call_args[0][0]
        assert event.event_type == "form_template.deleted"
        assert event.template_uid == "ft_test_123"


class TestPathStepLinking:
    @pytest.mark.asyncio
    async def test_link_to_path_step(self):
        backend = MagicMock()
        backend.link_to_path_step = AsyncMock(return_value=Result.ok(True))
        service = _make_service(backend=backend)

        result = await service.link_to_path_step("ft_1", "ps:1")

        assert result.is_ok
        backend.link_to_path_step.assert_awaited_once_with("ft_1", "ps:1")

    @pytest.mark.asyncio
    async def test_unlink_from_path_step(self):
        backend = MagicMock()
        backend.unlink_from_path_step = AsyncMock(return_value=Result.ok(True))
        service = _make_service(backend=backend)

        result = await service.unlink_from_path_step("ft_1", "ps:1")

        assert result.is_ok
