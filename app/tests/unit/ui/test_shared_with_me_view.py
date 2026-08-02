"""SharedWithMeView / SharedItemCard — render-shape guard for /profile/shared.

The previous card renderer read fields that don't exist on EntityDTO
(``original_filename``, ``report_type``) and 500'd on the first real share.
These tests render the card from an EntityDTO built exactly the way the
service builds it (``EntityDTO.from_dict`` over node-shaped properties), so
any field-shape drift fails here instead of at runtime.
"""

from __future__ import annotations

from fasthtml.common import to_xml

from core.models.entity_dto import EntityDTO
from core.ports.query_types import SharedWithMeItem
from ui.profile.shared_view import (
    SHARED_LIST_ID,
    SharedItemCard,
    SharedWithMeView,
    shared_filter_bar,
    shared_items_content,
)


def _item(entity_props: dict, **edge) -> SharedWithMeItem:
    return {
        "entity": EntityDTO.from_dict(entity_props),
        "role": edge.get("role", "student"),
        "shared_at": edge.get("shared_at", "2026-07-04T12:42:38.288833Z"),
        "shared_by": edge.get("shared_by", "user_admin"),
        "sharer_uid": edge.get("sharer_uid", "user_admin"),
        "share_version": edge.get("share_version"),
        "subject_exercise_uid": edge.get("subject_exercise_uid"),
        "subject_exercise_title": edge.get("subject_exercise_title"),
        "subject_ps_uid": edge.get("subject_ps_uid"),
        "subject_ps_title": edge.get("subject_ps_title"),
    }


_ENTRY_REPORT_PROPS = {
    "uid": "er_e7ca22a9",
    "entity_type": "entry_report",
    "status": "completed",
    "title": "Feedback: ue_65688cb7",
    "created_by": "user_admin",
}


def test_card_renders_entry_report() -> None:
    """ADR-040 auto-shared EntryReport — the real production shape."""
    html = to_xml(SharedItemCard(_item(_ENTRY_REPORT_PROPS)))
    assert "Feedback: ue_65688cb7" in html
    assert "/entry-reports/detail?uid=er_e7ca22a9" in html
    assert "From user_admin" in html


def test_card_renders_form_submission() -> None:
    """Manually shared FormSubmission — the other live producer."""
    props = {
        "uid": "fs_123",
        "entity_type": "form_submission",
        "status": "completed",
        "title": "Weekly check-in",
        "created_by": "user_peer",
    }
    html = to_xml(SharedItemCard(_item(props, shared_by="Peer Name")))
    assert "Weekly check-in" in html
    assert "/my-forms/detail?uid=fs_123" in html


def test_card_without_detail_page_renders_without_link() -> None:
    """Types with no detail page (e.g. Resource) render a card, not a broken href."""
    props = {
        "uid": "res_1",
        "entity_type": "resource",
        "status": "active",
        "title": "A curated resource",
    }
    html = to_xml(SharedItemCard(_item(props)))
    assert "A curated resource" in html
    assert "href" not in html


def test_card_untitled_falls_back_to_uid() -> None:
    props = {"uid": "er_x", "entity_type": "entry_report", "status": "completed"}
    html = to_xml(SharedItemCard(_item(props)))
    assert "er_x" in html


def test_card_subject_context_line_links_exchange_and_path_step() -> None:
    """C4+C5: the exercise subject links into the exchange thread, the PS to its page."""
    html = to_xml(
        SharedItemCard(
            _item(
                _ENTRY_REPORT_PROPS,
                subject_exercise_uid="ex_tasks",
                subject_exercise_title="List your Tasks",
                subject_ps_uid="ps.skuel.tasks",
                subject_ps_title="Task Management",
            )
        )
    )
    assert "List your Tasks" in html
    assert "/exchange?exercise=ex_tasks" in html
    assert "Task Management" in html
    assert "/explore/ps/ps.skuel.tasks" in html


def test_card_subject_context_line_exercise_only() -> None:
    """No PathStep anchor → the exchange link renders without an "in" segment."""
    html = to_xml(
        SharedItemCard(
            _item(
                _ENTRY_REPORT_PROPS,
                subject_exercise_uid="ex_tasks",
                subject_exercise_title="List your Tasks",
            )
        )
    )
    assert "/exchange?exercise=ex_tasks" in html
    assert " · in " not in html


def test_card_without_subject_renders_no_context_line() -> None:
    """FormSubmissions and other non-report shares carry null subject columns."""
    html = to_xml(SharedItemCard(_item(_ENTRY_REPORT_PROPS)))
    assert "/exchange?exercise=" not in html


def test_view_empty_state() -> None:
    html = to_xml(SharedWithMeView([]))
    assert "Nothing shared with you yet" in html


def test_view_grid_with_items() -> None:
    html = to_xml(SharedWithMeView([_item(_ENTRY_REPORT_PROPS)]))
    assert "Shared With Me" in html
    assert "Feedback: ue_65688cb7" in html


# ============================================================================
# Arc 2 C4: FilterBar + fragment content states
# ============================================================================

_RE_PROPS = {
    "uid": "re_1",
    "entity_type": "revised_exercise",
    "status": "active",
    "title": "The Gentle Return (revised)",
    "created_by": "user_admin",
}


def test_view_renders_filter_bar_with_derived_options() -> None:
    """Type · Shared-by options come from the live inbox, values canonical."""
    items = [
        _item(_ENTRY_REPORT_PROPS, shared_by="Admin", sharer_uid="user_admin"),
        _item(_RE_PROPS, shared_by="Admin", sharer_uid="user_admin"),
    ]
    html = to_xml(SharedWithMeView(items))
    assert 'hx-get="/profile/shared/list-fragment"' in html
    assert f'hx-target="#{SHARED_LIST_ID}"' in html
    # Canonical enum values as option values (emission rule), display names as text.
    assert 'value="entry_report"' in html
    assert 'value="revised_exercise"' in html
    assert "Entry Report" in html
    assert "Revised Exercise" in html
    # Sharer keyed by uid, labeled by display name.
    assert 'value="user_admin"' in html
    assert "Admin" in html
    # No sort dropdown on this bar.
    assert 'name="sort_by"' not in html


def test_view_empty_inbox_renders_no_filter_bar() -> None:
    """A filter that cannot narrow anything is noise — hidden when inbox is empty."""
    html = to_xml(SharedWithMeView([]))
    assert "/profile/shared/list-fragment" not in html
    assert f'id="{SHARED_LIST_ID}"' in html


def test_sharer_options_skip_items_without_creator() -> None:
    """No resolvable sharer → no dropdown option; the item stays under All."""
    props = {"uid": "er_nc", "entity_type": "entry_report", "status": "completed"}
    bar_html = to_xml(shared_filter_bar([_item(props, shared_by=None, sharer_uid=None)]))
    assert 'value="all"' in bar_html
    assert "user_admin" not in bar_html


def test_fragment_content_filtered_empty_vs_unfiltered_empty() -> None:
    """ "No match" line when filters are active; full EmptyState when inbox is empty."""
    filtered_html = to_xml(shared_items_content([], filtered=True))
    assert "Nothing shared matches this filter." in filtered_html
    assert "Nothing shared with you yet" not in filtered_html

    unfiltered_html = to_xml(shared_items_content([], filtered=False))
    assert "Nothing shared with you yet" in unfiltered_html


def test_view_inbox_copy() -> None:
    """C4 inbox identity: the page frames itself as work awaiting your attention."""
    html = to_xml(SharedWithMeView([]))
    assert "for your attention" in html
