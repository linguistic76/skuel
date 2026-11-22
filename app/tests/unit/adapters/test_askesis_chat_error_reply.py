"""What a learner reads when Askesis cannot answer.

The chat door (``POST /askesis/api/submit``) answers a failed pipeline with the error's
``display_message``, and the API door's refusal toast (``X-Toast-Message``, which every
``boundary_handler`` route sends and the toast manager shows) carries the same sentence:
never the raw text of the exception the pipeline met, and never the developer's message.
The service here is the real ``with_error_handling`` decorator over a pipeline that raises,
so the error is exactly the one a live failure produces.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.requests import Request
from starlette.testclient import TestClient

import adapters.inbound.csrf as csrf
from adapters.inbound.askesis_api import create_askesis_api_routes
from adapters.inbound.askesis_ui import create_askesis_ui_routes
from adapters.inbound.boundary import result_to_response
from adapters.inbound.rate_limit import reset_buckets_for_testing
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import UserRole
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import ErrorContext, Errors, Result

_USER_UID = "user_learner"
_RAW = "Couldn't connect to graph.example.io:7687 (resolved to ('10.0.0.7', 7687))"
_TIMEOUT_USER_MESSAGE = "Your question is taking too long to process. Please try again."


class _RaisingPipeline:
    """An Askesis service whose pipeline raises, under the decorator the real one wears."""

    @with_error_handling("answer_user_question", error_type="system", uid_param="user_uid")
    async def answer_user_question(
        self, user_uid: str, question: str, **_options: object
    ) -> Result[dict[str, object]]:
        raise ConnectionError(_RAW)


class _FailingPipeline:
    """An Askesis service that answers a written refusal."""

    def __init__(self, error: ErrorContext) -> None:
        self._error = error

    async def answer_user_question(
        self, user_uid: str, question: str, **_options: object
    ) -> Result[dict[str, object]]:
        return Result.fail(self._error)


def _fake_auth(request: Request) -> str:
    return _USER_UID


async def _csrf_ok(request: Request) -> tuple[bool, str]:
    return True, ""


@pytest.fixture(autouse=True)
def _clean_quota_buckets():
    reset_buckets_for_testing()
    yield
    reset_buckets_for_testing()


def _client(service: object, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(csrf, "verify_csrf", _csrf_ok)
    monkeypatch.setattr("adapters.inbound.askesis_ui.require_authenticated_user", _fake_auth)
    monkeypatch.setattr("adapters.inbound.askesis_api.require_authenticated_user", _fake_auth)
    app, rt = fast_app(pico=False, default_hdrs=False)
    user = MagicMock()
    user.uid = _USER_UID
    user.role = UserRole.MEMBER
    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(user))
    create_askesis_ui_routes(
        rt, service, intelligence_tier=IntelligenceTier.FULL, user_service=user_service
    )
    create_askesis_api_routes(
        rt, service, intelligence_tier=IntelligenceTier.FULL, user_service=user_service
    )
    return TestClient(app)


def _chat_text(client: TestClient) -> str:
    response = client.post("/askesis/api/submit", data={"message": "What should I practise?"})
    assert response.status_code == 200
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", response.text))


class TestChatReply:
    def test_a_raised_exception_reads_as_the_unexpected_error_sentence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        text = _chat_text(_client(_RaisingPipeline(), monkeypatch))

        assert "An unexpected error occurred" in text
        assert "graph.example.io" not in text

    def test_a_written_refusal_reads_as_its_user_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        timeout = Errors.system(
            message="Pipeline timed out after 30s",
            operation="answer_user_question",
            user_message=_TIMEOUT_USER_MESSAGE,
        )

        text = _chat_text(_client(_FailingPipeline(timeout), monkeypatch))

        assert _TIMEOUT_USER_MESSAGE in text
        assert "timed out after 30s" not in text


class TestRefusalToast:
    def test_the_api_doors_toast_carries_the_user_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(_RaisingPipeline(), monkeypatch)

        response = client.get("/api/askesis/ask", params={"question": "What should I practise?"})

        assert response.status_code == 500
        assert response.headers["X-Toast-Message"] == "An unexpected error occurred"
        assert response.json()["message"] == "An unexpected error occurred"

    def test_every_boundary_refusal_toasts_its_user_message(self) -> None:
        missing = Errors.not_found("Task", "task_abc123")

        response = result_to_response(Result.fail(missing))

        assert response.headers["X-Toast-Message"] == "The requested Task could not be found"
        assert response.headers["X-Toast-Type"] == "error"

    def test_a_validation_refusal_still_toasts_its_reason(self) -> None:
        refused = Errors.validation("Title must not be empty", field="title")

        response = result_to_response(Result.fail(refused))

        assert response.headers["X-Toast-Message"] == "Title must not be empty"
