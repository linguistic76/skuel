"""Forgeable-flag gate on POST /journals/follow-up (Codex #572 P1 + canon P3).

The composer's grounding dials are FOUNDER-only in the UI, but a POST flag is
forgeable — the route must force BOTH ``summon_canon`` and ``summon_vault``
off server-side for a non-FOUNDER, and thread them through for a FOUNDER.

Harness: real ``fast_app`` + Starlette TestClient with genuine CSRF (mirrors
``test_path_steps_ui_progress.py``); auth monkeypatched at the import site.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.journals_routes import create_journals_routes
from core.services.journal.journal_service import JournalFollowUp
from core.utils.result_simplified import Result

_USER_UID = "user_test"


def _fake_require_authenticated_user(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _auth_and_csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "adapters.inbound.journals_routes.require_authenticated_user",
        _fake_require_authenticated_user,
    )
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _user_service(is_founder: bool) -> MagicMock:
    user = MagicMock()
    user.journal_tier.is_founder = MagicMock(return_value=is_founder)
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


def _client_for(*, is_founder: bool) -> tuple[TestClient, MagicMock, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    journal = MagicMock()
    journal.run_follow_up = AsyncMock(
        return_value=Result.ok(JournalFollowUp(text="reply", sources=()))
    )
    user_service = _user_service(is_founder)
    services = MagicMock()
    services.user = user_service
    services.journal = journal
    create_journals_routes(app, rt, services)
    return TestClient(app), journal, user_service


def _post_follow_up(client: TestClient, extra: dict[str, str]) -> httpx2.Response:
    import json

    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    # Unsaved (ephemeral) follow-up: memory rides the structured transcript_json
    # accumulator (ADR-078 §5). The forgeable-flag gate under test runs before the
    # memory branch, so any valid opening pair exercises it.
    data = {
        "transcript_json": json.dumps(
            [
                {"role": "user", "content": "my note"},
                {"role": "assistant", "content": "prior response"},
            ]
        ),
        "user_reply": "tell me more",
        **extra,
    }
    return client.post("/journals/follow-up", data=data, headers={CSRF_HEADER_NAME: token})


class TestFollowUpSummonGate:
    def test_non_founder_forged_flags_are_forced_off(self) -> None:
        client, journal, _ = _client_for(is_founder=False)

        response = _post_follow_up(client, {"summon_canon": "true", "summon_vault": "true"})

        assert response.status_code == 200
        kwargs = journal.run_follow_up.await_args.kwargs
        assert kwargs["summon_canon"] is False
        assert kwargs["summon_vault"] is False

    def test_founder_flags_thread_through(self) -> None:
        client, journal, user_service = _client_for(is_founder=True)

        response = _post_follow_up(client, {"summon_canon": "true", "summon_vault": "true"})

        assert response.status_code == 200
        kwargs = journal.run_follow_up.await_args.kwargs
        assert kwargs["summon_canon"] is True
        assert kwargs["summon_vault"] is True
        # ONE user resolve covers both dials.
        user_service.get_user.assert_awaited_once()

    def test_founder_vault_only_dial(self) -> None:
        client, journal, _ = _client_for(is_founder=True)

        _post_follow_up(client, {"summon_vault": "true"})

        kwargs = journal.run_follow_up.await_args.kwargs
        assert kwargs["summon_canon"] is False
        assert kwargs["summon_vault"] is True

    def test_absent_flags_default_off_without_a_user_lookup(self) -> None:
        client, journal, user_service = _client_for(is_founder=True)

        response = _post_follow_up(client, {})

        assert response.status_code == 200
        kwargs = journal.run_follow_up.await_args.kwargs
        assert kwargs["summon_canon"] is False
        assert kwargs["summon_vault"] is False
        # No summon requested → no user lookup spent on the common path.
        user_service.get_user.assert_not_awaited()


class TestFollowUpCanonBookScope:
    def test_selected_books_thread_through_as_list(self) -> None:
        client, journal, _ = _client_for(is_founder=True)

        _post_follow_up(client, {"summon_canon": "true", "canon_book_uids": "res_a,res_b"})

        kwargs = journal.run_follow_up.await_args.kwargs
        assert kwargs["canon_book_uids"] == ["res_a", "res_b"]

    def test_empty_scope_means_whole_shelf_not_empty_list(self) -> None:
        # An empty CSV with the dial ON must draw the WHOLE shelf (None), never
        # [] — an empty resource_uids list is a guaranteed miss in retrieve().
        client, journal, _ = _client_for(is_founder=True)

        _post_follow_up(client, {"summon_canon": "true", "canon_book_uids": ""})

        kwargs = journal.run_follow_up.await_args.kwargs
        assert kwargs["canon_book_uids"] is None

    def test_book_scope_ignored_when_canon_dial_off(self) -> None:
        client, journal, _ = _client_for(is_founder=True)

        _post_follow_up(client, {"canon_book_uids": "res_a"})

        kwargs = journal.run_follow_up.await_args.kwargs
        assert kwargs["summon_canon"] is False
        assert kwargs["canon_book_uids"] is None
