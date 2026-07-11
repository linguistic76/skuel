"""Unit tests for the Activity Domain inline field-update API factory.

The factory registers one ``POST /api/{domain}/{uid}/{field}`` route per
FieldUpdateSpec, shared by all 6 Activity Domains (status + priority today).
These tests exercise the observable behaviors of those routes without
spinning up FastHTML or a real DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from adapters.inbound.route_factories import (
    PRIORITY_VALUES,
    ActivityFieldApiConfig,
    FieldUpdateSpec,
    create_activity_field_api_routes,
)
from core.utils.result_simplified import Errors, Result


@pytest.fixture(autouse=True)
def _disable_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    """``csrf_protected`` reads env at call time — force enforcement off."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")


class _RouteRegistry:
    """Capture handlers registered via ``@rt(path, methods=...)``."""

    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], Any] = {}

    def __call__(self, path: str, methods: list[str] | None = None):
        method = (methods[0] if methods else "GET").upper()

        def decorator(func):
            self.handlers[(path, method)] = func
            return func

        return decorator

    def get(self, path: str, method: str = "POST"):
        return self.handlers[(path, method.upper())]


@dataclass
class _FakeEntity:
    """Minimal stand-in for an Activity Domain entity."""

    uid: str
    status: str


def _request(form_data: dict[str, str] | None, user_uid: str = "user_test") -> Any:
    """Build a minimal request stub with a session and async ``.form()``."""
    return SimpleNamespace(
        method="POST",
        session={"user_uid": user_uid},
        url=SimpleNamespace(path="/api/tasks/uid/status"),
        form=AsyncMock(return_value=form_data or {}),
    )


def _config(
    *,
    service: Any,
    fields: tuple[FieldUpdateSpec, ...],
    card_fn: Any = lambda entity: SimpleNamespace(rendered=entity),
    domain_name: str = "tasks",
    singular: str = "task",
) -> ActivityFieldApiConfig:
    return ActivityFieldApiConfig(
        domain_name=domain_name,
        singular=singular,
        service=service,
        card_fn=card_fn,
        fields=fields,
    )


def _status_config(*, service: Any, update_status: Any, **kwargs: Any) -> ActivityFieldApiConfig:
    return _config(
        service=service, fields=(FieldUpdateSpec(field="status", apply=update_status),), **kwargs
    )


def _register(config: ActivityFieldApiConfig, field: str = "status") -> Any:
    """Register routes against a fake registry and return one field handler."""
    rt = _RouteRegistry()
    handlers = create_activity_field_api_routes(rt, config)
    assert len(handlers) == len(config.fields)
    return rt.get(f"/api/{config.domain_name}/{{uid}}/{field}", "POST")


# ============================================================================
# Route registration — one route per FieldUpdateSpec
# ============================================================================


def test_registers_post_route_per_field_at_expected_paths() -> None:
    rt = _RouteRegistry()
    service = SimpleNamespace(verify_ownership=AsyncMock())

    create_activity_field_api_routes(
        rt,
        _config(
            service=service,
            fields=(
                FieldUpdateSpec(field="status", apply=AsyncMock()),
                FieldUpdateSpec(
                    field="priority", apply=AsyncMock(), allowed_values=PRIORITY_VALUES
                ),
            ),
            domain_name="goals",
        ),
    )

    assert ("/api/goals/{uid}/status", "POST") in rt.handlers
    assert ("/api/goals/{uid}/priority", "POST") in rt.handlers


def test_handlers_get_distinct_names_per_domain_and_field() -> None:
    """FastHTML derives route names from ``__name__`` — collisions are ambiguity."""
    rt = _RouteRegistry()
    service = SimpleNamespace(verify_ownership=AsyncMock())

    create_activity_field_api_routes(
        rt,
        _config(
            service=service,
            fields=(
                FieldUpdateSpec(field="status", apply=AsyncMock()),
                FieldUpdateSpec(field="priority", apply=AsyncMock()),
            ),
        ),
    )

    names = {h.__name__ for h in rt.handlers.values()}
    assert names == {"update_tasks_status", "update_tasks_priority"}


# ============================================================================
# Success path — card_fn invoked with the updated entity
# ============================================================================


@pytest.mark.asyncio
async def test_success_returns_card_for_updated_entity() -> None:
    entity = _FakeEntity(uid="task.1", status="completed")
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock(return_value=Result.ok(entity))
    card_fn = MagicMock(side_effect=lambda e: SimpleNamespace(rendered=e))

    handler = _register(_status_config(service=service, update_status=update, card_fn=card_fn))
    response = await handler(_request({"status": "completed"}), uid="task.1")

    update.assert_awaited_once_with("task.1", "completed")
    card_fn.assert_called_once_with(entity)
    assert response.rendered is entity


@pytest.mark.asyncio
async def test_priority_success_applies_value_and_returns_card() -> None:
    entity = _FakeEntity(uid="task.1", status="active")
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock(return_value=Result.ok(entity))
    card_fn = MagicMock(side_effect=lambda e: SimpleNamespace(rendered=e))

    config = _config(
        service=service,
        fields=(FieldUpdateSpec(field="priority", apply=update, allowed_values=PRIORITY_VALUES),),
        card_fn=card_fn,
    )
    handler = _register(config, field="priority")
    response = await handler(_request({"priority": "high"}), uid="task.1")

    update.assert_awaited_once_with("task.1", "high")
    assert response.rendered is entity


# ============================================================================
# Whitelist — allowed_values rejects garbage before apply is invoked
# ============================================================================


@pytest.mark.asyncio
async def test_value_outside_whitelist_renders_banner_and_skips_apply() -> None:
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock()
    card_fn = MagicMock()

    config = _config(
        service=service,
        fields=(FieldUpdateSpec(field="priority", apply=update, allowed_values=PRIORITY_VALUES),),
        card_fn=card_fn,
    )
    handler = _register(config, field="priority")
    response = await handler(_request({"priority": "banana"}), uid="task.1")

    update.assert_not_awaited()
    card_fn.assert_not_called()
    assert "Invalid priority value" in to_xml(response)


@pytest.mark.asyncio
async def test_no_whitelist_passes_value_through_to_apply() -> None:
    """Status has no whitelist — transition validation is the service's job."""
    entity = _FakeEntity(uid="task.1", status="paused")
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock(return_value=Result.ok(entity))

    handler = _register(_status_config(service=service, update_status=update))
    await handler(_request({"status": "paused"}), uid="task.1")

    update.assert_awaited_once_with("task.1", "paused")


# ============================================================================
# Standard apply path — accepts any (uid, value) -> Result callable
# ============================================================================


@pytest.mark.asyncio
async def test_standard_apply_receives_uid_and_value() -> None:
    """Domains pass a thin wrapper around the facade update — must get (uid, value)."""
    entity = _FakeEntity(uid="habit.1", status="paused")
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))

    captured: dict[str, str] = {}

    async def update(uid: str, new_status: str) -> Result[Any]:
        captured["uid"] = uid
        captured["status"] = new_status
        return Result.ok(entity)

    handler = _register(
        _status_config(
            service=service, update_status=update, domain_name="habits", singular="habit"
        )
    )
    await handler(_request({"status": "paused"}), uid="habit.1")

    assert captured == {"uid": "habit.1", "status": "paused"}


# ============================================================================
# Explicit status-to-method dispatch — caller's apply can dispatch per-status
# (e.g. GoalsService.set_status calls activate/complete/archive).
# ============================================================================


@pytest.mark.asyncio
async def test_status_dispatching_apply_routes_to_correct_method() -> None:
    """The callable form accepts caller-side dispatch on the status string."""
    activate = AsyncMock(return_value=Result.ok(_FakeEntity(uid="goal.1", status="active")))
    complete = AsyncMock(return_value=Result.ok(_FakeEntity(uid="goal.1", status="completed")))
    dispatch = {"active": activate, "completed": complete}

    async def set_status(uid: str, new_status: str) -> Result[Any]:
        return await dispatch[new_status](uid)

    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    handler = _register(
        _status_config(
            service=service,
            update_status=set_status,
            domain_name="goals",
            singular="goal",
        )
    )

    await handler(_request({"status": "completed"}), uid="goal.1")

    complete.assert_awaited_once_with("goal.1")
    activate.assert_not_awaited()


# ============================================================================
# Ownership failure — renders not-found banner, never invokes apply
# ============================================================================


@pytest.mark.asyncio
async def test_ownership_failure_renders_not_found_banner() -> None:
    service = SimpleNamespace(
        verify_ownership=AsyncMock(return_value=Result.fail(Errors.not_found("task", "task.1")))
    )
    update = AsyncMock()
    card_fn = MagicMock()

    handler = _register(_status_config(service=service, update_status=update, card_fn=card_fn))
    response = await handler(_request({"status": "completed"}), uid="task.1")

    update.assert_not_awaited()
    card_fn.assert_not_called()
    assert "Task not found" in to_xml(response)


# ============================================================================
# Missing form field — renders banner, never invokes apply
# ============================================================================


@pytest.mark.asyncio
async def test_missing_field_value_renders_banner() -> None:
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock()
    card_fn = MagicMock()

    handler = _register(_status_config(service=service, update_status=update, card_fn=card_fn))
    response = await handler(_request({}), uid="task.1")

    update.assert_not_awaited()
    card_fn.assert_not_called()
    assert "Missing status value" in to_xml(response)


@pytest.mark.asyncio
async def test_blank_field_value_renders_banner() -> None:
    """Empty-string value must be rejected — ``form.get(field)`` returns ``""``."""
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock()

    handler = _register(_status_config(service=service, update_status=update))
    response = await handler(_request({"status": ""}), uid="task.1")

    update.assert_not_awaited()
    assert "Missing status value" in to_xml(response)


# ============================================================================
# Service error — renders banner with the error's display_message
# ============================================================================


@pytest.mark.asyncio
async def test_service_error_renders_display_message_in_banner() -> None:
    err = Errors.validation("Cannot transition from archived", field="status", value="active")
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock(return_value=Result.fail(err))
    card_fn = MagicMock()

    handler = _register(_status_config(service=service, update_status=update, card_fn=card_fn))
    response = await handler(_request({"status": "active"}), uid="task.1")

    card_fn.assert_not_called()
    assert err.display_message in to_xml(response)


# ============================================================================
# Singular casing — banner uses capitalized singular regardless of input
# ============================================================================


@pytest.mark.asyncio
async def test_not_found_banner_capitalizes_singular() -> None:
    """``singular="principle"`` → ``"Principle not found"``."""
    service = SimpleNamespace(
        verify_ownership=AsyncMock(return_value=Result.fail(Errors.not_found("principle")))
    )
    update = AsyncMock()

    handler = _register(
        _status_config(
            service=service,
            update_status=update,
            domain_name="principles",
            singular="principle",
        )
    )
    response = await handler(_request({"status": "active"}), uid="p.1")

    assert "Principle not found" in to_xml(response)
