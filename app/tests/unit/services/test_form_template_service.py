"""Tests for FormTemplateService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.forms.form_template import FormTemplate
from core.services.forms.form_template_service import FormTemplateService
from core.utils.result_simplified import Errors, Result


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


class TestCreateFormTemplate:
    @pytest.mark.asyncio
    async def test_create_success(self):
        backend = MagicMock()
        backend.create = AsyncMock(return_value=Result.ok(None))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.create_form_template(
            title="Feedback",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
        )

        assert result.is_ok
        assert result.value.title == "Feedback"
        assert result.value.entity_type == EntityType.FORM_TEMPLATE
        assert result.value.uid.startswith("ft_")
        backend.create.assert_awaited_once()
        event_bus.publish_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_backend_failure(self):
        backend = MagicMock()
        backend.create = AsyncMock(
            return_value=Result.fail(Errors.database(operation="create", message="DB error"))
        )
        service = _make_service(backend=backend)

        result = await service.create_form_template(
            title="Test",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_create_publishes_event(self):
        backend = MagicMock()
        backend.create = AsyncMock(return_value=Result.ok(None))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        await service.create_form_template(
            title="Event Test",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
        )

        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert event.event_type == "form_template.created"
        assert event.title == "Event Test"
        assert event.field_count == 1


class TestGetFormTemplate:
    @pytest.mark.asyncio
    async def test_get_success(self):
        template = _make_template()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(template))
        service = _make_service(backend=backend)

        result = await service.get_form_template("ft_test_123")

        assert result.is_ok
        assert result.value.uid == "ft_test_123"

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend=backend)

        result = await service.get_form_template("ft_nonexistent")

        assert result.is_error


class TestUpdateFormTemplate:
    @pytest.mark.asyncio
    async def test_update_success(self):
        template = _make_template(title="Updated Title")
        backend = MagicMock()
        backend.update = AsyncMock(return_value=Result.ok(None))
        backend.get = AsyncMock(return_value=Result.ok(template))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.update_form_template(uid="ft_test_123", title="Updated Title")

        assert result.is_ok
        backend.update.assert_awaited_once()
        event_bus.publish_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_no_changes(self):
        """No-op update returns the existing template without writing."""
        template = _make_template()
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(template))
        backend.update = AsyncMock()
        service = _make_service(backend=backend)

        result = await service.update_form_template(uid="ft_test_123")

        assert result.is_ok
        backend.update.assert_not_awaited()


class TestDeleteFormTemplate:
    @pytest.mark.asyncio
    async def test_delete_success_no_submissions(self):
        backend = MagicMock()
        backend.execute_query = AsyncMock(return_value=Result.ok([{"count": 0}]))
        backend.delete = AsyncMock(return_value=Result.ok(True))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        result = await service.delete_form_template("ft_test_123")

        assert result.is_ok
        backend.delete.assert_awaited_once()
        event_bus.publish_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_blocked_by_submissions(self):
        """Cannot delete a template that has submissions."""
        backend = MagicMock()
        backend.execute_query = AsyncMock(return_value=Result.ok([{"count": 3}]))
        backend.delete = AsyncMock()
        service = _make_service(backend=backend)

        result = await service.delete_form_template("ft_test_123")

        assert result.is_error
        assert "3 existing submission" in str(result.error)
        backend.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_publishes_event(self):
        backend = MagicMock()
        backend.execute_query = AsyncMock(return_value=Result.ok([{"count": 0}]))
        backend.delete = AsyncMock(return_value=Result.ok(True))
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()
        service = _make_service(backend=backend, event_bus=event_bus)

        await service.delete_form_template("ft_test_123")

        event = event_bus.publish_async.call_args[0][0]
        assert event.event_type == "form_template.deleted"
        assert event.template_uid == "ft_test_123"


class TestArticleLinking:
    @pytest.mark.asyncio
    async def test_link_to_article(self):
        backend = MagicMock()
        backend.link_to_article = AsyncMock(return_value=Result.ok(True))
        service = _make_service(backend=backend)

        result = await service.link_to_article("ft_1", "a_1")

        assert result.is_ok
        backend.link_to_article.assert_awaited_once_with("ft_1", "a_1")

    @pytest.mark.asyncio
    async def test_unlink_from_article(self):
        backend = MagicMock()
        backend.unlink_from_article = AsyncMock(return_value=Result.ok(True))
        service = _make_service(backend=backend)

        result = await service.unlink_from_article("ft_1", "a_1")

        assert result.is_ok
