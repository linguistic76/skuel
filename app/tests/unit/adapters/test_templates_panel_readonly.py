"""
Pin the Activity Templates panel as read-only — and as actually mounted.

Templates are vault-authored (`_tmpl.md` + the PathStep's
``{domain}_template_uids:`` frontmatter); the PS detail page surfaces them and
authors nothing. Two halves are worth pinning because both were broken before
the arc's PR-3:

1. **The mount.** ``render_templates_panel_placeholder`` had zero callers, so
   the TEACHER-gated fragment route existed with nothing loading it and
   ``render_ps_detail_content``'s ``user_role`` parameter gated nothing. The
   caller is what these tests assert.
2. **Read-only.** The panel used to carry "+ Add" / "Edit" / "Detach" controls
   pointing at create/edit/detach handlers that no longer exist.

See: /docs/roadmap/done/activity-templates-vault-door.md
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fasthtml.common import to_xml

from core.models.enums import UserRole
from core.utils.result_simplified import Result
from ui.explore.ps_detail import render_ps_detail_content
from ui.teaching.templates_panel import (
    PANEL_DOMAINS,
    render_templates_panel,
    render_templates_panel_placeholder,
)

_PS_UID = "ps.mindfulness-101.step-1"
_PANEL_URL = f"/teaching/ps/{_PS_UID}/templates"
_DOMAINS = ("task", "goal", "habit", "event", "choice", "principle")


def _register(services: Any) -> tuple[list[str], dict[str, Any]]:
    """Register the panel routes against ``services``; return paths + handlers."""
    from adapters.inbound.templates_ui import create_templates_ui_routes

    paths: list[str] = []
    handlers: dict[str, Any] = {}

    def rt(path: str, methods: list[str] | None = None) -> Any:
        paths.append(path)

        def _keep(handler: Any) -> Any:
            handlers[path] = handler
            return handler

        return _keep

    create_templates_ui_routes(object(), rt, services)  # type: ignore[arg-type]
    return paths, handlers


class _CountingService:
    """Records how many ``list_for_pathstep`` calls are in flight at once."""

    def __init__(self, tracker: dict[str, int]) -> None:
        self._tracker = tracker

    async def list_for_pathstep(self, ps_uid: str) -> Result[list[dict[str, Any]]]:
        self._tracker["live"] += 1
        self._tracker["peak"] = max(self._tracker["peak"], self._tracker["live"])
        await asyncio.sleep(0)  # yield, so a sequential loop cannot overlap
        self._tracker["live"] -= 1
        return Result.ok([{"uid": f"tt.{ps_uid}.x", "title": "X"}])


def _detail_html(user_role: UserRole | None) -> str:
    return to_xml(
        render_ps_detail_content(
            step=SimpleNamespace(title="Step", description="d", tags=()),
            uid=_PS_UID,
            content_html="",
            is_marked_read=False,
            is_bookmarked=False,
            is_in_progress=False,
            is_mastered=False,
            user_uid="user_test",
            user_role=user_role,
        )
    )


class TestPanelMount:
    """The PS detail page is the caller — the gate lives there."""

    @pytest.mark.parametrize("role", [UserRole.TEACHER, UserRole.ADMIN])
    def test_panel_mounted_for_teacher_and_above(self, role: UserRole) -> None:
        assert f'hx-get="{_PANEL_URL}"' in _detail_html(role)

    @pytest.mark.parametrize("role", [None, UserRole.REGISTERED, UserRole.MEMBER])
    def test_panel_absent_below_teacher(self, role: UserRole | None) -> None:
        assert "/templates" not in _detail_html(role)

    def test_placeholder_targets_the_registered_fragment_route(self) -> None:
        """The placeholder's hx-get is the path ``templates_ui`` registers."""
        services = SimpleNamespace(**{f"{d}_templates": object() for d in _DOMAINS}, user=object())
        paths, _ = _register(services)

        assert paths == ["/teaching/ps/{ps_uid}/templates"]
        assert _PANEL_URL in to_xml(render_templates_panel_placeholder(_PS_UID))


class TestPanelIsReadOnly:
    """No authoring affordance survives — the vault is the door."""

    def _html(self) -> str:
        attached = {
            "task": [{"uid": "tt.mindfulness-101.morning-sit", "title": "Morning sit"}],
            "habit": [{"uid": "ht.mindfulness-101.daily-check", "title": "Daily check"}],
        }
        return to_xml(render_templates_panel(_PS_UID, attached))

    def test_renders_attached_templates(self) -> None:
        html = self._html()
        assert "Morning sit" in html
        assert "tt.mindfulness-101.morning-sit" in html

    def test_all_six_domains_have_a_row(self) -> None:
        html = self._html()
        for _domain, label in PANEL_DOMAINS:
            assert label in html

    def test_no_mutation_affordance(self) -> None:
        html = self._html()
        assert "<form" not in html.lower()
        assert "/new" not in html
        assert "/edit" not in html
        assert "/detach" not in html

    def test_names_the_real_door(self) -> None:
        assert "_tmpl.md" in self._html()


class TestPanelReadsFanOut:
    """Six domains, six graph round-trips — issued together, not in turn.

    The panel is now on every TEACHER+ PS detail page load, so the sequential
    loop ``_gather_attached`` used while it was unmounted became six serial
    AuraDB round-trips per view. ``_CountingService`` yields inside the call,
    so a sequential loop would peak at 1.
    """

    def test_six_reads_are_concurrent(self) -> None:
        tracker = {"live": 0, "peak": 0}
        services = SimpleNamespace(
            **{f"{d}_templates": _CountingService(tracker) for d in _DOMAINS},
            user=object(),
        )
        _, handlers = _register(services)
        # The role gate is exercised in TestPanelMount; reach the inner handler
        # (functools.wraps exposes it) so this test is about the fan-out alone.
        inner = handlers["/teaching/ps/{ps_uid}/templates"].__wrapped__
        request = SimpleNamespace(session={"user_uid": "user_test"}, query_params={})

        asyncio.run(inner(request, ps_uid=_PS_UID))

        assert tracker["peak"] == len(_DOMAINS)
        assert tracker["live"] == 0
