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
from ui.profile.shared_view import SharedItemCard, SharedWithMeView


def _item(entity_props: dict, **edge) -> SharedWithMeItem:
    return {
        "entity": EntityDTO.from_dict(entity_props),
        "role": edge.get("role", "student"),
        "shared_at": edge.get("shared_at", "2026-07-04T12:42:38.288833Z"),
        "shared_by": edge.get("shared_by", "user_admin"),
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
