"""Unit test for the teaching forms list route's tuple unpacking.

FormTemplateService.list() returns Result[tuple[list[FormTemplate], int]] (the
BaseService contract). teaching_forms_ui types its service as Any, so mypy cannot
verify the unpack — this test locks the runtime behavior (PR5 of the arg-type
campaign). The previous code did `templates = result.value or []` and iterated the
(list, int) tuple, so `template.uid` hit the inner list / int and raised
AttributeError; the fix unpacks `templates, _total = result.value`.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

import adapters.inbound.teaching_forms_ui as tfu
from core.utils.result_simplified import Result


class _FakeTemplate:
    def __init__(self, uid: str, title: str) -> None:
        self.uid = uid
        self.title = title
        self.instructions = ""
        self.form_schema: dict[str, object] = {}


def _identity_decorator(fn):
    return fn


def _fake_require_role(*_args, **_kwargs):
    return _identity_decorator


def _fake_teacher(uid):
    """Stand-in for the User `@require_role` injects (non-admin: scoped reads)."""
    from types import SimpleNamespace

    from core.models.enums.user_enums import UserRole

    return SimpleNamespace(
        uid=uid,
        role=UserRole.TEACHER,
        has_permission=UserRole.TEACHER.has_permission,
    )


@pytest.mark.asyncio
async def test_forms_list_unpacks_list_int_tuple(monkeypatch):
    """The forms list handler iterates the templates list, not the (list, int) tuple."""

    def _fake_render(content, active, request):
        return content

    def _fake_auth(_request):
        return "user_teacher"

    # require_role is applied as a decorator at route-creation time — patch before create.
    monkeypatch.setattr(tfu, "require_role", _fake_require_role)
    monkeypatch.setattr(tfu, "require_authenticated_user", _fake_auth)
    monkeypatch.setattr(tfu, "render_teaching_sidebar_page", _fake_render)

    captured: list = []

    def _fake_rt(_path: str):
        def _register(fn):
            captured.append(fn)
            return fn

        return _register

    service = MagicMock()
    service.list = AsyncMock(return_value=Result.ok(([_FakeTemplate("ft_1", "Survey")], 1)))
    service.count_submissions = AsyncMock(return_value=Result.ok(3))

    tfu.create_teaching_forms_ui_routes(
        MagicMock(), _fake_rt, service, MagicMock(), MagicMock(), MagicMock()
    )

    # First registered route is teaching_forms_list.
    handler = captured[0]
    content = await handler(request=MagicMock(), current_user=_fake_teacher("user_teacher"))

    rendered = to_xml(content)
    # The template title only appears if the LIST (not the tuple) was iterated.
    assert "Survey" in rendered
    # The count is scoped to the caller's classrooms — see
    # tests/integration/routes/test_unscoped_uid_read_ownership.py for why.
    service.count_submissions.assert_awaited_once_with("ft_1", "user_teacher")
