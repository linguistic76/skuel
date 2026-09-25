"""The Groups hub tiles open the one UserEntry detail page (ADR-088 §3).

A listed share is opened at ``/gradebook/{entry_uid}``, whose audience read
composes the same fragment the list is gated by, so whatever is listed can be
opened — there is no per-group peer page beside it.
"""

from __future__ import annotations

from fasthtml.common import to_xml

from ui.groups.shared_preview import GroupSharedPreviewList


def test_tile_links_to_the_gradebook_detail_page() -> None:
    html = to_xml(
        GroupSharedPreviewList(
            [
                {
                    "entity": {"uid": "ue_shared_1", "title": "Reflection 1"},
                    "author_name": "Alex Rivera",
                    "shared_at": "2026-04-10T12:00:00",
                }
            ]
        )
    )
    assert 'href="/gradebook/ue_shared_1"' in html
    assert "/groups/" not in html
    assert "by Alex Rivera" in html
