"""The Groups hub tiles open the one UserEntry detail page (ADR-088 §3).

A listed share is opened at ``/gradebook/{entry_uid}``, whose audience read
composes the same fragment the list is gated by, so whatever is listed can be
opened — there is no per-group peer page beside it. The tiles render the
*Shared with you* row shape (``SharedWithMeItem``), the one reader narrowed
to a group.
"""

from __future__ import annotations

from fasthtml.common import to_xml

from core.models.entity_dto import EntityDTO
from ui.groups.shared_preview import GroupSharedPreviewList


def test_tile_links_to_the_gradebook_detail_page() -> None:
    html = to_xml(
        GroupSharedPreviewList(
            [
                {
                    "entity": EntityDTO.from_dict(
                        {"uid": "ue_shared_1", "entity_type": "user_entry", "title": "Reflection 1"}
                    ),
                    "shared_at": "2026-04-10T12:00:00",
                    "shared_by": "Alex Rivera",
                    "sharer_uid": "user_alex",
                    "via_direct": False,
                    "via_groups": [{"uid": "g_1", "name": "Physics"}],
                    "review": {"reviewed_by": None, "revised_after_feedback": False},
                }
            ]
        )
    )
    assert 'href="/gradebook/ue_shared_1"' in html
    assert "/groups/" not in html
    assert "by Alex Rivera" in html
