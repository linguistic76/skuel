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
from adapters.inbound.journals_routes import AI_SUBSCRIPTION_MESSAGE, create_journals_routes
from adapters.inbound.rate_limit import (
    LLM_QUOTA_MESSAGE,
    llm_quota_allowed,
    reset_buckets_for_testing,
)
from core.config.intelligence_tier import IntelligenceTier
from core.constants import LLMQuota
from core.models.enums.user_enums import UserRole
from core.services.journal.journal_service import JournalFollowUp
from core.utils.result_simplified import Result

_USER_UID = "user_test"


def _fake_require_authenticated_user(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _auth_and_csrf_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "adapters.inbound.journals_routes.require_authenticated_user",
        _fake_require_authenticated_user,
    )
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")
    # The AI gate records daily-quota units per request — clean buckets so
    # tests never accumulate against the shared _USER_UID.
    reset_buckets_for_testing()
    yield
    reset_buckets_for_testing()


def _user_service(is_founder: bool, role: UserRole = UserRole.MEMBER) -> MagicMock:
    user = MagicMock()
    user.journal_tier.is_founder = MagicMock(return_value=is_founder)
    # Real role so the per-user AI gate (ADR-043) resolves for real — MEMBER
    # passes the gate; the founder axis under test is orthogonal to it.
    user.role = role
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


def _client_for(
    *, is_founder: bool, role: UserRole = UserRole.MEMBER
) -> tuple[TestClient, MagicMock, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    journal = MagicMock()
    journal.run_follow_up = AsyncMock(
        return_value=Result.ok(JournalFollowUp(text="reply", sources=()))
    )
    user_service = _user_service(is_founder, role)
    services = MagicMock()
    services.user = user_service
    services.journal = journal
    services.intelligence_tier = IntelligenceTier.FULL
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
        # ONE user resolve covers the AI tier gate AND both dials.
        user_service.get_user.assert_awaited_once()

    def test_founder_vault_only_dial(self) -> None:
        client, journal, _ = _client_for(is_founder=True)

        _post_follow_up(client, {"summon_vault": "true"})

        kwargs = journal.run_follow_up.await_args.kwargs
        assert kwargs["summon_canon"] is False
        assert kwargs["summon_vault"] is True

    def test_absent_flags_default_off_with_single_gate_lookup(self) -> None:
        client, journal, user_service = _client_for(is_founder=True)

        response = _post_follow_up(client, {})

        assert response.status_code == 200
        kwargs = journal.run_follow_up.await_args.kwargs
        assert kwargs["summon_canon"] is False
        assert kwargs["summon_vault"] is False
        # Every follow-up spends LLM money, so the per-user AI gate (ADR-043)
        # must resolve the role — exactly ONE lookup, with no second load for
        # the dials. (Supersedes the pre-gate zero-lookup optimization.)
        user_service.get_user.assert_awaited_once()


class TestFollowUpQuotaGate:
    """Daily LLM quota at the journals ``_load_ai_gated_user`` seam (PR C2).

    A MEMBER at quota is denied with the quota message — never the
    subscription upsell — and a REGISTERED user still sees the subscription
    denial regardless of quota state (the tier gate fires first)."""

    def _exhaust_quota(self) -> None:
        for _ in range(LLMQuota.DAILY_LIMIT):
            assert llm_quota_allowed(_USER_UID)

    def test_member_over_quota_gets_quota_message_not_upsell(self) -> None:
        client, journal, _ = _client_for(is_founder=False)
        self._exhaust_quota()

        response = _post_follow_up(client, {})

        assert response.status_code == 200
        assert LLM_QUOTA_MESSAGE in response.text
        assert AI_SUBSCRIPTION_MESSAGE not in response.text
        journal.run_follow_up.assert_not_awaited()

    def test_member_under_quota_records_one_unit_per_follow_up(self) -> None:
        client, journal, _ = _client_for(is_founder=False)

        _post_follow_up(client, {})

        journal.run_follow_up.assert_awaited_once()
        # Exactly one unit recorded at gate time: the rest of the window
        # drains after DAILY_LIMIT - 1 further units.
        for _ in range(LLMQuota.DAILY_LIMIT - 1):
            assert llm_quota_allowed(_USER_UID)
        assert llm_quota_allowed(_USER_UID) is False

    def test_registered_still_gets_subscription_denial_even_at_quota(self) -> None:
        client, journal, _ = _client_for(is_founder=False, role=UserRole.REGISTERED)
        self._exhaust_quota()

        response = _post_follow_up(client, {})

        assert response.status_code == 200
        assert AI_SUBSCRIPTION_MESSAGE in response.text
        assert LLM_QUOTA_MESSAGE not in response.text
        journal.run_follow_up.assert_not_awaited()

    def test_validation_failure_burns_no_quota(self) -> None:
        # Codex #800 P2: the quota unit is recorded immediately before the
        # paid call, AFTER validation — a rejected request must never burn
        # the user's last unit.
        client, journal, _ = _client_for(is_founder=False)
        for _ in range(LLMQuota.DAILY_LIMIT - 1):
            assert llm_quota_allowed(_USER_UID)

        response = _post_follow_up(client, {"user_reply": "   "})

        assert response.status_code == 200
        assert "write something" in response.text
        journal.run_follow_up.assert_not_awaited()
        # The empty-reply rejection left the final unit untouched.
        assert llm_quota_allowed(_USER_UID) is True


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
