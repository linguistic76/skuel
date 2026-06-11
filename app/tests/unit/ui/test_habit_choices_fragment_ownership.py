"""Owner-scoping test for the Habit ↔ Choice HTMX fragment.

Codex P2 (PR #283): /habits/choices-fragment renders choices reached via the
INFORMS_CHOICE / IMPACTS_HABIT edges. Choices are USER_OWNED, but the edge
traversal carries no owner predicate — so a habit edged to *another* user's
choice would leak that choice's title + detail link, violating the
404-not-403 invariant.

These tests drive the registered fragment handler with mocked relationship +
ownership layers and assert a cross-user choice is NOT rendered while a
same-owner choice IS.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

import adapters.inbound.habits_ui as habits_ui
from core.utils.result_simplified import Errors, Result

OWNER = "user_owner"

OWNED_CHOICE = {"uid": "choice_owned", "title": "My own choice", "edge": {}}
FOREIGN_CHOICE = {"uid": "choice_foreign", "title": "Someone else's choice", "edge": {}}


def _capture_routes(monkeypatch, choices_ownership):
    """Build the habits UI routes with a path-keyed fake rt; return handler map."""

    def _fake_auth(_request):
        return OWNER

    monkeypatch.setattr(habits_ui, "require_authenticated_user", _fake_auth)

    # Habit ownership passes (the habit IS owned); the leak is about the CHOICES.
    async def _owns_habit(_service_core, _uid, _user_uid, _name):
        return MagicMock(), None

    monkeypatch.setattr(habits_ui, "require_owned_entity", _owns_habit)

    handlers: dict[str, object] = {}

    def _fake_rt(path: str, **_kwargs):
        def _register(fn):
            handlers[path] = fn
            return fn

        return _register

    habits_service = MagicMock()

    # informed_choices returns one foreign + one owned; impacting returns the foreign.
    async def _get_related(key, _uid):
        if key == "informed_choices":
            return Result.ok([FOREIGN_CHOICE, OWNED_CHOICE])
        return Result.ok([FOREIGN_CHOICE])

    habits_service.relationships.get_related_with_metadata = AsyncMock(side_effect=_get_related)

    habits_ui.create_habits_ui_routes(
        MagicMock(), _fake_rt, habits_service, MagicMock(), choices_ownership
    )
    return handlers


def _ownership_verifier():
    """Verifier that owns only OWNED_CHOICE; foreign choice → NotFound (404-shaped)."""

    async def _verify(uid, user_uid):
        assert user_uid == OWNER
        if uid == OWNED_CHOICE["uid"]:
            return Result.ok(MagicMock())
        return Result.fail(Errors.not_found("Choice", uid))

    verifier = MagicMock()
    verifier.verify_ownership = AsyncMock(side_effect=_verify)
    return verifier


@pytest.mark.asyncio
async def test_cross_user_choice_is_not_rendered(monkeypatch):
    """A choice owned by another user must not appear in the fragment."""
    handlers = _capture_routes(monkeypatch, _ownership_verifier())
    handler = handlers["/habits/choices-fragment"]

    request = MagicMock()
    request.query_params.get.return_value = "habit_owned"

    rendered = to_xml(await handler(request=request))

    # The owned choice is shown; the foreign one is filtered out entirely.
    assert "My own choice" in rendered
    assert "/choices/detail?uid=choice_owned" in rendered
    assert "Someone else's choice" not in rendered
    assert "choice_foreign" not in rendered


@pytest.mark.asyncio
async def test_no_verifier_fails_closed(monkeypatch):
    """With no ownership verifier wired, surface no choices (fail closed)."""
    handlers = _capture_routes(monkeypatch, None)
    handler = handlers["/habits/choices-fragment"]

    request = MagicMock()
    request.query_params.get.return_value = "habit_owned"

    rendered = to_xml(await handler(request=request))

    assert "My own choice" not in rendered
    assert "Someone else's choice" not in rendered
