"""The binding contract `require_role` publishes (adapters/inbound/auth/roles.py).

FastHTML fills a handler's parameters from the request by reading the
registered callable's signature. The role decorator publishes the handler's
signature minus ``current_user`` on its wrapper, so that name is never bound:
a value a caller sends under it is neither read nor coerced (``Any("x")``
would raise before the role gate ran), and the decorator's assignment is the
only writer. The decorator also pins the one spelling,
``current_user: Any = None``, at decoration time.

This module runs under ``from __future__ import annotations`` on purpose:
every annotation below is a string at runtime, exactly as in the route
modules that carry the same import, so the decoration-time check is proven
against evaluated annotations, not annotation objects.
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.auth.roles import INJECTED_PARAM, require_admin, signature_for_binding
from adapters.inbound.fasthtml_types import Request
from core.models.enums import UserRole
from core.models.user.user import User
from core.utils.result_simplified import Result

_USER_UID = "user_admin"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _USER_UID
    user.role = role
    user.has_permission = role.has_permission
    return user


def _getter_for(role: UserRole):
    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    def get_user_service() -> MagicMock:
        return user_service

    return get_user_service


def _app_with_recording_handler(monkeypatch: pytest.MonkeyPatch, role: UserRole = UserRole.ADMIN):
    """A role-gated GET and POST that record what they received as ``current_user``."""
    monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)
    app, rt = fast_app(pico=False, default_hdrs=False)
    received: list[Any] = []

    @rt("/gated")
    @require_admin(_getter_for(role))
    async def gated(request: Request, current_user: Any = None) -> dict[str, str]:
        received.append(current_user)
        return {"uid": current_user.uid}

    @rt("/gated", methods=["POST"])
    @require_admin(_getter_for(role))
    async def gated_post(request: Request, current_user: Any = None) -> dict[str, str]:
        received.append(current_user)
        return {"uid": current_user.uid}

    return TestClient(app), received


class TestCurrentUserIsNeverBoundFromTheRequest:
    @pytest.mark.parametrize(
        ("query", "headers"),
        [("", {}), ("?current_user=x", {}), ("", {"Current-User": "x"})],
        ids=["absent", "query-string", "header"],
    )
    def test_supplied_value_is_ignored_and_the_user_is_injected(
        self, monkeypatch: pytest.MonkeyPatch, query: str, headers: dict[str, str]
    ) -> None:
        client, received = _app_with_recording_handler(monkeypatch)

        response = client.get(f"/gated{query}", headers=headers)

        assert response.status_code == 200
        assert response.json() == {"uid": _USER_UID}
        assert received[-1].uid == _USER_UID

    def test_form_field_is_ignored_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, received = _app_with_recording_handler(monkeypatch)

        response = client.post("/gated", data={"current_user": "x"})

        assert response.status_code == 200
        assert received[-1].uid == _USER_UID

    def test_role_gate_still_answers_before_the_handler(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, received = _app_with_recording_handler(monkeypatch, role=UserRole.MEMBER)

        response = client.get("/gated?current_user=x")

        assert response.status_code == 403
        assert received == []


class TestPublishedSignature:
    def test_wrapper_publishes_the_handler_signature_minus_current_user(self) -> None:
        @require_admin(_getter_for(UserRole.ADMIN))
        async def handler(request: Request, uid: str, current_user: Any = None) -> dict[str, str]:
            return {}

        published = inspect.signature(handler)

        assert list(published.parameters) == ["request", "uid"]
        assert published.return_annotation is not inspect.Signature.empty

    def test_helper_keeps_every_other_parameter_in_order(self) -> None:
        async def handler(
            request: Request, current_user: Any = None, role: str | None = None
        ) -> None: ...

        reduced = signature_for_binding(handler)

        assert list(reduced.parameters) == ["request", "role"]
        assert INJECTED_PARAM not in reduced.parameters


class TestTheOneSpellingIsPinnedAtDecoration:
    def test_bare_current_user_is_refused(self) -> None:
        with pytest.raises(TypeError, match=r"`current_user: Any = None`; got `current_user`"):

            @require_admin(_getter_for(UserRole.ADMIN))
            async def handler(request: Request, current_user) -> None: ...

    def test_missing_current_user_is_refused(self) -> None:
        with pytest.raises(TypeError, match=r"got no such parameter"):

            @require_admin(_getter_for(UserRole.ADMIN))
            async def handler(request: Request) -> None: ...

    def test_no_default_is_refused(self) -> None:
        with pytest.raises(TypeError, match=r"got `current_user: (typing\.)?Any`"):

            @require_admin(_getter_for(UserRole.ADMIN))
            async def handler(request: Request, current_user: Any) -> None: ...

    def test_other_annotation_is_refused(self) -> None:
        with pytest.raises(TypeError, match=r"got `current_user: object = None`"):

            @require_admin(_getter_for(UserRole.ADMIN))
            async def handler(request: Request, current_user: object = None) -> None: ...


class TestWhyAnyAndNotUser:
    """The boundary's reason, held as a fact about FastHTML rather than prose.

    On a handler that LACKS the role decorator, FastHTML binds a
    dataclass-annotated parameter from the request: ``current_user: User``
    would hand the handler a User built from the caller's own fields — a
    caller-chosen identity. ``current_user: Any = None`` on the same mistake
    leaves None, and the first attribute read fails closed.
    """

    def test_a_user_annotation_is_body_bound_on_an_undecorated_handler(self) -> None:
        app, rt = fast_app(pico=False, default_hdrs=False)
        received: list[Any] = []

        @rt("/forgot-the-decorator")
        async def handler(request: Request, current_user: User) -> dict[str, str]:
            received.append(current_user)
            return {"uid": current_user.uid}

        response = TestClient(app).get("/forgot-the-decorator?uid=user_admin&title=Mallory")

        assert response.status_code == 200
        assert isinstance(received[-1], User)
        assert received[-1].uid == "user_admin"

    def test_the_boundary_spelling_fails_closed_on_an_undecorated_handler(self) -> None:
        app, rt = fast_app(pico=False, default_hdrs=False)
        received: list[Any] = []

        @rt("/forgot-the-decorator")
        async def handler(request: Request, current_user: Any = None) -> dict[str, str]:
            received.append(current_user)
            return {"uid": current_user.uid}

        client = TestClient(app)

        # Nothing supplied: the slot holds None and the first attribute read fails.
        with pytest.raises(AttributeError):
            client.get("/forgot-the-decorator?uid=user_admin")
        assert received == [None]

        # A supplied value never reaches the handler: `Any("x")` raises in the binder.
        with pytest.raises(TypeError, match="Any cannot be instantiated"):
            client.get("/forgot-the-decorator?current_user=x")
        assert received == [None]
