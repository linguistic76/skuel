"""Tests for the Engage/Abandon action group rendered on /explore/ps/{uid}.

Covers the ``render_engagement_actions`` helper in ``path_steps_ui.py`` —
the single source of truth for what the engagement action area looks like.
HTMX handler closures inside ``create_path_steps_ui_routes`` delegate to
the engagement service and then re-render via this helper, so testing the
helper covers the visible contract for slice 1.

Full handler-flow coverage (Neo4j edge writes, lifecycle transitions) lives
in ``tests/integration/test_ps_engagement_lifecycle.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fasthtml.common import to_xml

from adapters.inbound.path_steps_ui import render_engagement_actions
from core.services.ps_engagement.engagement import Engagement

_PS_UID = "ps:test:slice1"
_WRAPPER_ID = 'id="ps-engagement-actions"'


def _engaged() -> Engagement:
    return Engagement(
        student_uid="user_alice",
        ps_uid=_PS_UID,
        state="engaged",
        since=datetime(2026, 5, 11, 9, 0, tzinfo=UTC),
    )


class TestRenderEngagementActionsNoActive:
    """When find_active returned None — page invites the user to engage."""

    def test_shows_engage_button_with_post_target(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, None))

        assert "Engage with this Path Step" in html
        assert f'hx-post="/explore/ps/{_PS_UID}/engage"' in html

    def test_uses_wrapper_id_and_swaps_self(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, None))

        assert _WRAPPER_ID in html
        assert 'hx-target="#ps-engagement-actions"' in html
        assert 'hx-swap="outerHTML"' in html

    def test_no_abandon_button_in_clean_state(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, None))

        assert "Abandon" not in html


class TestRenderEngagementActionsEngaged:
    """When an active engagement exists — show status + Abandon."""

    def test_shows_engaged_badge(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, _engaged()))

        assert "Engaged" in html

    def test_shows_abandon_button_with_confirm(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, _engaged()))

        assert "Abandon" in html
        assert f'hx-post="/explore/ps/{_PS_UID}/abandon"' in html
        assert "hx-confirm=" in html

    def test_complete_button_deferred_with_note(self) -> None:
        """Slice 1 does not ship the Complete flow — review screen lands in slice 4."""
        html = to_xml(render_engagement_actions(_PS_UID, _engaged()))

        # No live POST target for complete in slice 1.
        assert f"/explore/ps/{_PS_UID}/complete" not in html
        # But the user is told why.
        assert "review screen" in html.lower()

    def test_wrapper_id_preserved_for_htmx_swap(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, _engaged()))

        assert _WRAPPER_ID in html
