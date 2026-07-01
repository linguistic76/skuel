"""Route tests for the Journals zero-persistence contract (ADR-073).

The contract: the journal text path (`POST /journals/start`), the file-upload
path (`POST /journals/upload`), and the suggestions panel
(`POST /journals/suggest-activities`) run their AI work and return results
*inline* / to the user's own `je_out/` folder — they must write **nothing** to
the store. These tests prove that invariant by asserting the persistence methods
on `user_entry_service` are never awaited, across STANDARD and FOUNDER tiers.

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
    services.journal.run_compiled = AsyncMock(return_value=Result.ok("# Compiled output"))
    services.journal.suggestions_available = True
    services.journal.active_goal_titles = AsyncMock(return_value=Result.ok([]))
    services.journal.suggest_activities = AsyncMock(return_value=Result.ok([]))

    # Persistence surface — every one of these must stay un-awaited on the
    # zero-persistence journal paths (ADR-073).
    services.user_entry = MagicMock()
    services.user_entry.create_entry = AsyncMock(
        return_value=Result.ok((MagicMock(uid="ue_x"), None))
    )
    services.user_entry.update_processed_content = AsyncMock(return_value=Result.ok(True))
    services.user_entry.submit_file = AsyncMock(
        return_value=Result.ok((MagicMock(uid="ue_x"), None))
    )
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
    services.user_entry.submit_file.assert_not_awaited()


def _make_upload_request(form_items: list[tuple[str, Any]], user_uid: str = "user_mike") -> Any:
    """Build a POST request whose ``form()`` yields a starlette FormData.

    Upload handlers use ``form.getlist("file")`` + ``UploadFile`` filtering, so a
    plain dict won't do — FormData carries the real multipart shape.
    """
    from starlette.datastructures import FormData

    form_data = FormData(form_items)

    async def _form() -> FormData:
        return form_data

    return SimpleNamespace(
        method="POST",
        session={"user_uid": user_uid},
        url=SimpleNamespace(path="/journals/upload"),
        query_params={},
        form=_form,
        cookies={},
        headers={},
    )


def _text_upload(filename: str, content: bytes) -> Any:
    """A starlette UploadFile backed by an in-memory buffer."""
    import io

    from starlette.datastructures import UploadFile

    return UploadFile(file=io.BytesIO(content), filename=filename)


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


class TestJournalsUploadZeroPersistence:
    """`POST /journals/upload` compiles to je_out/, never to Neo4j."""

    async def test_single_text_file_writes_je_out_and_persists_nothing(
        self,
        handlers: dict[str, Any],
        mock_services: Any,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        # FOUNDER instructions_only → run_compiled → je_out/{stem}_out.md.
        monkeypatch.setattr("adapters.inbound.journals_routes._JE_OUT", tmp_path)
        mock_services.user.get_user = AsyncMock(return_value=Result.ok(_make_user(is_founder=True)))
        request = _make_upload_request(
            [
                ("file", _text_upload("reflection.txt", b"Ship the site by Friday.")),
                ("processing_mode", "instructions_only"),
            ]
        )
        await handlers["/journals/upload"](request=request)

        mock_services.journal.run_compiled.assert_awaited_once()
        assert (tmp_path / "reflection_out.md").read_text() == "# Compiled output"
        _assert_nothing_persisted(mock_services)

    async def test_no_file_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_upload_request([("processing_mode", "instructions_only")])
        await handlers["/journals/upload"](request=request)
        _assert_nothing_persisted(mock_services)

    async def test_duplicate_basename_batch_is_rejected(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        # Two files share a basename → je_out/{stem}_out.md would collide, so the
        # batch is rejected loudly rather than silently dropping one (Kody, #478).
        request = _make_upload_request(
            [
                ("file", _text_upload("note.txt", b"first")),
                ("file", _text_upload("note.txt", b"second")),
                ("processing_mode", "instructions_only"),
            ]
        )
        response = await handlers["/journals/upload"](request=request)

        from fasthtml.common import to_xml

        assert "Duplicate filename" in to_xml(response)
        _assert_nothing_persisted(mock_services)


class TestSuggestActivitiesZeroPersistence:
    """`POST /journals/suggest-activities` takes content in the body, stores nothing."""

    async def test_content_body_runs_bridge_and_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_request(form={"content": "Ship the site by Friday."})
        await handlers["/journals/suggest-activities"](request=request)

        mock_services.journal.suggest_activities.assert_awaited_once()
        # No stored entry is read or written.
        mock_services.user_entry.get_entry.assert_not_called()
        _assert_nothing_persisted(mock_services)

    async def test_core_tier_returns_inert_panel_and_persists_nothing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.journal = None
        request = _make_request(form={"content": "anything"})
        response = await handlers["/journals/suggest-activities"](request=request)

        assert response is not None
        _assert_nothing_persisted(mock_services)
