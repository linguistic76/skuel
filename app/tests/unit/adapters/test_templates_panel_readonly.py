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

from types import SimpleNamespace
from typing import Any

import pytest
from fasthtml.common import to_xml

from core.models.enums import UserRole
from ui.explore.ps_detail import render_ps_detail_content
from ui.teaching.templates_panel import (
    PANEL_DOMAINS,
    render_templates_panel,
    render_templates_panel_placeholder,
)

_PS_UID = "ps.mindfulness-101.step-1"
_PANEL_URL = f"/teaching/ps/{_PS_UID}/templates"


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
        from adapters.inbound.templates_ui import create_templates_ui_routes

        registered: list[str] = []

        def rt(path: str, methods: list[str] | None = None) -> Any:
            registered.append(path)
            return lambda handler: handler

        services = SimpleNamespace(
            task_templates=object(),
            goal_templates=object(),
            habit_templates=object(),
            event_templates=object(),
            choice_templates=object(),
            principle_templates=object(),
            user=object(),
        )
        create_templates_ui_routes(object(), rt, services)  # type: ignore[arg-type]

        assert registered == ["/teaching/ps/{ps_uid}/templates"]
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
