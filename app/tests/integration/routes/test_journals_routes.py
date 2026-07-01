"""Route tests for the Journals text-session path (ADR-073 zero-persistence).

The contract: `POST /journals/start` runs the AI workflow on typed text and
returns the response *inline* — it must write **nothing** to the store. These
tests prove that invariant by asserting the persistence methods on
`user_entry_service` are never awaited, for both STANDARD and FOUNDER tiers.

No Neo4j required: services are mocked and only the handler logic is exercised.
Mirrors the harness in `test_today_routes.py`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.exceptions import HTTPException

from core.utils.result_simplified import Errors, Result


@pytest.fixture(autouse=True)
def _disable_csrf_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the ``@csrf_protected`` wrapper fall through to the handler."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")


def _make_request(user_uid: str | None = "user_mike", form: dict[str, str] | None = None) -> Any:
    session = {"user_uid": user_uid} if user_uid is not None else {}
    form_data = form or {}

    async def _form() -> dict[str, str]:
        return form_data

    return SimpleNamespace(
        method="POST",
        session=session,
        url=SimpleNamespace(path="/journals/start"),
        query_params={},
        form=_form,
        cookies={},
        headers={},
    )


def _make_user(is_founder: bool) -> Any:
    user = MagicMock()
    user.journal_tier.is_founder.return_value = is_founder
    return user


@pytest.fixture
def mock_services() -> Any:
    services = MagicMock()

    services.user = MagicMock()
    services.user.get_user = AsyncMock(return_value=Result.ok(_make_user(is_founder=False)))

    services.journal = MagicMock()
    services.journal.run_standard = AsyncMock(return_value=Result.ok("A standard response."))
    services.journal.run_stage1 = AsyncMock(return_value=Result.ok("A scribe record."))

    # Persistence surface — every one of these must stay un-awaited on /journals/start.
    services.user_entry = MagicMock()
    services.user_entry.create_entry = AsyncMock(
        return_value=Result.ok((MagicMock(uid="ue_x"), None))
    )
    services.user_entry.update_processed_content = AsyncMock(return_value=Result.ok(True))
    services.user_entry.list_for_user = AsyncMock(return_value=Result.ok([]))

    services.batch_transcription = None
    services.user_entry_processor = None
    return services


@pytest.fixture
def handlers(mock_services: Any) -> dict[str, Any]:
    """Register the journals routes and return path → handler."""
    from adapters.inbound.journals_routes import create_journals_routes

    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    create_journals_routes(MagicMock(), rt_collector, mock_services)
    return registered


def _assert_nothing_persisted(services: Any) -> None:
    services.user_entry.create_entry.assert_not_awaited()
    services.user_entry.update_processed_content.assert_not_awaited()


class TestJournalsStartZeroPersistence:
    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(user_uid=None)
        with pytest.raises(HTTPException) as exc:
            await handlers["/journals/start"](request=request)
        assert exc.value.status_code == 401

    async def test_standard_returns_inline_and_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_request(form={"raw_entry": "What's on my mind today."})
        response = await handlers["/journals/start"](request=request)

        # Runs the standard workflow, not the founder one.
        mock_services.journal.run_standard.assert_awaited_once()
        mock_services.journal.run_stage1.assert_not_awaited()
        # Inline swap retargeted to the workspace — no redirect, no stored entry.
        assert response.status_code == 200
        assert response.headers["HX-Retarget"] == "#journal-workspace"
        assert response.headers["HX-Reswap"] == "outerHTML"
        _assert_nothing_persisted(mock_services)

    async def test_founder_runs_stage1_and_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.user.get_user = AsyncMock(return_value=Result.ok(_make_user(is_founder=True)))
        request = _make_request(form={"raw_entry": "Founder brainstorm."})
        response = await handlers["/journals/start"](request=request)

        mock_services.journal.run_stage1.assert_awaited_once()
        mock_services.journal.run_standard.assert_not_awaited()
        assert response.headers["HX-Retarget"] == "#journal-workspace"
        _assert_nothing_persisted(mock_services)

    async def test_empty_entry_short_circuits_with_no_ai_and_no_persistence(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_request(form={"raw_entry": "   "})
        await handlers["/journals/start"](request=request)

        mock_services.journal.run_standard.assert_not_awaited()
        mock_services.journal.run_stage1.assert_not_awaited()
        _assert_nothing_persisted(mock_services)

    async def test_ai_failure_still_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.journal.run_standard = AsyncMock(
            return_value=Result.fail(Errors.integration("llm", "boom"))
        )
        request = _make_request(form={"raw_entry": "Trigger an AI failure."})
        await handlers["/journals/start"](request=request)

        _assert_nothing_persisted(mock_services)
