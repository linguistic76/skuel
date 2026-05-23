"""Unit tests for the Activity Domain status-update API factory.

The factory registers a single ``POST /api/{domain}/{uid}/status`` route
shared by all 6 Activity Domains. These tests exercise the four observable
behaviors of that route without spinning up FastHTML or a real DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from adapters.inbound.route_factories import (
    ActivityStatusApiConfig,
    create_activity_status_api_routes,
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
    update_status: Any,
    card_fn: Any = lambda entity: SimpleNamespace(rendered=entity),
    domain_name: str = "tasks",
    singular: str = "task",
) -> ActivityStatusApiConfig:
    return ActivityStatusApiConfig(
        domain_name=domain_name,
        singular=singular,
        service=service,
        update_status=update_status,
        card_fn=card_fn,
    )


def _register(config: ActivityStatusApiConfig) -> Any:
    """Register routes against a fake registry and return the status handler."""
    rt = _RouteRegistry()
    handlers = create_activity_status_api_routes(rt, config)
    assert len(handlers) == 1
    return rt.get(f"/api/{config.domain_name}/{{uid}}/status", "POST")


# ============================================================================
# Route registration
# ============================================================================


def test_registers_post_status_route_at_expected_path() -> None:
    rt = _RouteRegistry()
    service = SimpleNamespace(verify_ownership=AsyncMock())
    update = AsyncMock()

    create_activity_status_api_routes(
        rt, _config(service=service, update_status=update, domain_name="goals", singular="goal")
    )

    assert ("/api/goals/{uid}/status", "POST") in rt.handlers


# ============================================================================
# Success path — card_fn invoked with the updated entity
# ============================================================================


@pytest.mark.asyncio
async def test_success_returns_card_for_updated_entity() -> None:
    entity = _FakeEntity(uid="task.1", status="completed")
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock(return_value=Result.ok(entity))
    card_fn = MagicMock(side_effect=lambda e: SimpleNamespace(rendered=e))

    handler = _register(_config(service=service, update_status=update, card_fn=card_fn))
    response = await handler(_request({"status": "completed"}), uid="task.1")

    update.assert_awaited_once_with("task.1", "completed")
    card_fn.assert_called_once_with(entity)
    assert response.rendered is entity


# ============================================================================
# Standard update_method path — accepts any (uid, status) -> Result callable
# ============================================================================


@pytest.mark.asyncio
async def test_standard_update_method_receives_uid_and_status() -> None:
    """Domains pass a thin wrapper around core.update — must get (uid, status)."""
    entity = _FakeEntity(uid="habit.1", status="paused")
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))

    captured: dict[str, str] = {}

    async def update(uid: str, new_status: str) -> Result[Any]:
        captured["uid"] = uid
        captured["status"] = new_status
        return Result.ok(entity)

    handler = _register(
        _config(service=service, update_status=update, domain_name="habits", singular="habit")
    )
    await handler(_request({"status": "paused"}), uid="habit.1")

    assert captured == {"uid": "habit.1", "status": "paused"}


# ============================================================================
# Explicit status-to-method dispatch — caller's update_status can dispatch
# per-status (e.g. GoalsService.set_status calls activate/complete/archive).
# ============================================================================


@pytest.mark.asyncio
async def test_status_dispatching_update_routes_to_correct_method() -> None:
    """The callable form accepts caller-side dispatch on the status string."""
    activate = AsyncMock(return_value=Result.ok(_FakeEntity(uid="goal.1", status="active")))
    complete = AsyncMock(return_value=Result.ok(_FakeEntity(uid="goal.1", status="completed")))
    dispatch = {"active": activate, "completed": complete}

    async def set_status(uid: str, new_status: str) -> Result[Any]:
        return await dispatch[new_status](uid)

    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    handler = _register(
        _config(
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
# Ownership failure — renders not-found banner, never invokes update
# ============================================================================


@pytest.mark.asyncio
async def test_ownership_failure_renders_not_found_banner() -> None:
    service = SimpleNamespace(
        verify_ownership=AsyncMock(return_value=Result.fail(Errors.not_found("task", "task.1")))
    )
    update = AsyncMock()
    card_fn = MagicMock()

    handler = _register(_config(service=service, update_status=update, card_fn=card_fn))
    response = await handler(_request({"status": "completed"}), uid="task.1")

    update.assert_not_awaited()
    card_fn.assert_not_called()
    assert "Task not found" in to_xml(response)


# ============================================================================
# Missing status form field — renders banner, never invokes update
# ============================================================================


@pytest.mark.asyncio
async def test_missing_status_form_field_renders_banner() -> None:
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock()
    card_fn = MagicMock()

    handler = _register(_config(service=service, update_status=update, card_fn=card_fn))
    response = await handler(_request({}), uid="task.1")

    update.assert_not_awaited()
    card_fn.assert_not_called()
    assert "Missing status value" in to_xml(response)


@pytest.mark.asyncio
async def test_blank_status_form_field_renders_banner() -> None:
    """Empty-string status must be rejected — ``form.get("status")`` returns ``""``."""
    service = SimpleNamespace(verify_ownership=AsyncMock(return_value=Result.ok(None)))
    update = AsyncMock()

    handler = _register(_config(service=service, update_status=update))
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

    handler = _register(_config(service=service, update_status=update, card_fn=card_fn))
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
        _config(
            service=service,
            update_status=update,
            domain_name="principles",
            singular="principle",
        )
    )
    response = await handler(_request({"status": "active"}), uid="p.1")

    assert "Principle not found" in to_xml(response)
