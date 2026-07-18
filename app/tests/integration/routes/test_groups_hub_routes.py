"""Route tests for /groups student-facing hub.

Covers:
- GET /groups — auth, empty/populated, role-filtered get_user_groups call,
  invalid ?group param falls back to first.
- GET /api/groups/{uid}/shared/preview — member returns list fragment,
  non-member returns empty fragment (not a 403 — no enumeration oracle).

No Neo4j required: services are mocked, BasePage is monkey-patched to a
lightweight async identity so we can inspect the content/title the route
hands to it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.exceptions import HTTPException

from core.models.group.group import create_group
from core.utils.result_simplified import Errors, Result


def _make_request(user_uid: str | None = "user_stud_01") -> Any:
    """Build a minimal request-like object for session-backed auth."""
    session = {"user_uid": user_uid} if user_uid is not None else {}
    return SimpleNamespace(
        session=session,
        url=SimpleNamespace(path="/groups"),
        query_params={},
    )


def _make_group(uid: str, name: str) -> Any:
    return create_group(uid=uid, name=name, owner_uid="user_teacher_01")


@pytest.fixture
def mock_services() -> Any:
    services = MagicMock()
    services.groups = MagicMock()
    services.groups.get_user_groups = AsyncMock(return_value=Result.ok([]))
    services.sharing = MagicMock()
    services.sharing.get_user_entries_shared_with_group = AsyncMock(return_value=Result.ok([]))
    services.sharing.get_user_entry_shared_with_group = AsyncMock(return_value=Result.ok(None))
    return services


@pytest.fixture
def handlers(mock_services: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Register /groups hub routes on a collector rt and return them.

    Patches ui.layouts.base_page.BasePage to a lightweight sync stub so we
    don't pull in the full navbar/auth machinery — we only care that the
    route hands the right content and title to BasePage.
    """

    def fake_base_page(**kwargs: Any) -> dict[str, Any]:
        return {"__base_page__": True, **kwargs}

    import ui.layouts.base_page as base_page_module

    monkeypatch.setattr(base_page_module, "BasePage", fake_base_page)

    from adapters.inbound.groups_hub_routes import create_groups_hub_routes

    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    create_groups_hub_routes(MagicMock(), rt_collector, mock_services)
    return registered


# ============================================================================
# GET /groups
# ============================================================================


class TestGroupsHub:
    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(user_uid=None)
        with pytest.raises(HTTPException) as exc:
            await handlers["/groups"](request=request)
        assert exc.value.status_code == 401

    async def test_empty_renders_hub_without_calling_sharing(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """Student with zero student-role groups still renders (empty state)."""
        request = _make_request()
        response = await handlers["/groups"](request=request)

        assert response["__base_page__"] is True
        assert response["title"] == "Groups"
        assert response["active_page"] == "groups"
        mock_services.groups.get_user_groups.assert_awaited_once()
        mock_services.sharing.get_user_entries_shared_with_group.assert_not_called()

    async def test_filters_by_student_role(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """Finding #6: hub must pass role='student' so TA edges don't eat the cap."""
        request = _make_request()
        await handlers["/groups"](request=request)

        call = mock_services.groups.get_user_groups.await_args
        assert call.kwargs.get("role") == "student", (
            "hub route must filter MEMBER_OF edges to role='student'"
        )

    async def test_populated_defaults_to_first_group(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        g1 = _make_group("group_a", "Physics 101")
        g2 = _make_group("group_b", "Chemistry 101")
        mock_services.groups.get_user_groups = AsyncMock(return_value=Result.ok([g1, g2]))

        request = _make_request()
        response = await handlers["/groups"](request=request)

        assert response["__base_page__"] is True

    async def test_invalid_group_query_param_falls_back_to_first(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """?group=does_not_exist must not crash — the hub picks the first tab."""
        g1 = _make_group("group_a", "Physics 101")
        mock_services.groups.get_user_groups = AsyncMock(return_value=Result.ok([g1]))

        request = _make_request()
        response = await handlers["/groups"](request=request, group="group_missing")

        assert response["__base_page__"] is True

    async def test_service_error_treated_as_empty(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """Backend failure must not surface as 500 — degrade to empty state."""
        mock_services.groups.get_user_groups = AsyncMock(
            return_value=Result.fail(Errors.database(operation="get_user_groups", message="boom"))
        )

        request = _make_request()
        response = await handlers["/groups"](request=request)

        assert response["__base_page__"] is True


# ============================================================================
# GET /api/groups/{group_uid}/shared/preview
# ============================================================================


class TestGroupsSharedPreview:
    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(user_uid=None)
        with pytest.raises(HTTPException) as exc:
            await handlers["/api/groups/{group_uid}/shared/preview"](
                request=request, group_uid="group_a"
            )
        assert exc.value.status_code == 401

    async def test_non_member_gets_empty_fragment_not_403(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """The Cypher MEMBER_OF MATCH is the access guard — non-members get
        an empty result, not an authorization error. The route must render
        the HubPreviewEmpty fragment, never raise 403.
        """
        mock_services.sharing.get_user_entries_shared_with_group = AsyncMock(
            return_value=Result.ok([])
        )

        request = _make_request()
        response = await handlers["/api/groups/{group_uid}/shared/preview"](
            request=request, group_uid="group_not_a_member"
        )

        assert response is not None

    async def test_member_with_entries_returns_list_fragment(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        records = [
            {
                "entity": {"uid": "ue_1", "title": "Reflection 1", "created_at": "2026-04-10"},
                "author_name": "Alex Rivera",
                "share_version": "original",
                "shared_at": "2026-04-10T12:00:00",
            }
        ]
        mock_services.sharing.get_user_entries_shared_with_group = AsyncMock(
            return_value=Result.ok(records)
        )

        request = _make_request()
        response = await handlers["/api/groups/{group_uid}/shared/preview"](
            request=request, group_uid="group_a"
        )

        assert response is not None
        mock_services.sharing.get_user_entries_shared_with_group.assert_awaited_once_with(
            user_uid="user_stud_01", group_uid="group_a", limit=12
        )

    async def test_service_error_yields_empty_fragment(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.sharing.get_user_entries_shared_with_group = AsyncMock(
            return_value=Result.fail(Errors.database(operation="query", message="boom"))
        )

        request = _make_request()
        response = await handlers["/api/groups/{group_uid}/shared/preview"](
            request=request, group_uid="group_a"
        )

        assert response is not None

    async def test_sharing_service_none_yields_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If sharing service failed to bootstrap, the preview degrades cleanly."""
        import ui.layouts.base_page as base_page_module

        def fake_base_page(**kwargs: Any) -> dict[str, Any]:
            return {"__base_page__": True, **kwargs}

        monkeypatch.setattr(base_page_module, "BasePage", fake_base_page)

        from adapters.inbound.groups_hub_routes import create_groups_hub_routes

        registered: dict[str, Any] = {}

        def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
            def decorator(fn: Any) -> Any:
                registered[path] = fn
                return fn

            return decorator

        degraded_services = MagicMock()
        degraded_services.groups = MagicMock()
        degraded_services.groups.get_user_groups = AsyncMock(return_value=Result.ok([]))
        degraded_services.sharing = None

        create_groups_hub_routes(MagicMock(), rt_collector, degraded_services)

        response = await registered["/api/groups/{group_uid}/shared/preview"](
            request=_make_request(), group_uid="group_a"
        )
        assert response is not None
