"""The Shared page's two sides render from the service row shapes (Submit & Share arc R6, R7).

Cards render from an EntityDTO built exactly the way the service builds it
(``EntityDTO.from_dict`` over node-shaped properties), so any field-shape
drift fails here instead of at runtime.
"""

from __future__ import annotations

from fasthtml.common import to_xml

from core.models.entity_dto import EntityDTO
from core.ports.query_types import VIA_DIRECT, SharedByMeItem, SharedWithMeItem
from ui.profile.shared_view import (
    SHARED_LIST_ID,
    WALL_ID,
    SharedItemCard,
    SharedPage,
    WallRow,
    shared_filter_bar,
    shared_items_content,
    wall_content,
)


def _item(entity_props: dict, **edge) -> SharedWithMeItem:
    return {
        "entity": EntityDTO.from_dict(entity_props),
        "shared_at": edge.get("shared_at", "2026-09-25T12:42:38.288833Z"),
        "shared_by": edge.get("shared_by", "Peer Name"),
        "sharer_uid": edge.get("sharer_uid", "user_peer"),
        "via_direct": edge.get("via_direct", True),
        "via_groups": edge.get("via_groups", []),
    }


_ENTRY_PROPS = {
    "uid": "ue_65688cb7",
    "entity_type": "user_entry",
    "status": "completed",
    "title": "Small steps design",
    "description": "How I broke the habit down.",
    "user_uid": "user_peer",
}


def _wall_item(**overrides) -> SharedByMeItem:
    item: SharedByMeItem = {
        "entity": EntityDTO.from_dict({**_ENTRY_PROPS, "user_uid": "user_me"}),
        "users": [
            {"uid": "user_a", "username": "alice", "display_name": "Alice", "shared_at": None}
        ],
        "groups": [{"uid": "g_1", "name": "Physics 101", "shared_at": None}],
        "last_shared_at": "2026-09-25T12:42:38.288833Z",
    }
    item.update(overrides)  # type: ignore[typeddict-item]
    return item


# ---------------------------------------------------------------- cards


def test_card_is_the_r6_card() -> None:
    """Title, description, from, date, badge, link — and nothing about status or feedback."""
    html = to_xml(SharedItemCard(_item(_ENTRY_PROPS)))
    assert "Small steps design" in html
    assert "How I broke the habit down." in html
    assert "From Peer Name" in html
    assert "Shared with you" in html
    assert 'href="/gradebook/ue_65688cb7"' in html
    assert "completed" not in html


def test_card_via_chips_name_direct_and_each_group() -> None:
    html = to_xml(
        SharedItemCard(
            _item(_ENTRY_PROPS, via_direct=True, via_groups=[{"uid": "g_1", "name": "Physics 101"}])
        )
    )
    assert "directly" in html
    assert "Physics 101" in html


def test_card_renders_form_submission() -> None:
    props = {
        "uid": "fs_123",
        "entity_type": "form_submission",
        "status": "completed",
        "title": "Weekly check-in",
        "user_uid": "user_peer",
    }
    html = to_xml(SharedItemCard(_item(props)))
    assert "Weekly check-in" in html
    assert "/my-forms/detail?uid=fs_123" in html


def test_card_untitled_falls_back_to_uid() -> None:
    html = to_xml(SharedItemCard(_item({**_ENTRY_PROPS, "title": None})))
    assert "ue_65688cb7" in html


# ---------------------------------------------------------------- filter bar


def test_filter_bar_has_type_shared_by_and_via_with_derived_options() -> None:
    items = [
        _item(_ENTRY_PROPS, via_direct=True),
        _item(
            {**_ENTRY_PROPS, "uid": "ue_2"},
            via_direct=False,
            via_groups=[{"uid": "g_1", "name": "Physics 101"}],
        ),
    ]
    html = to_xml(shared_filter_bar(items))
    assert 'name="entity_type"' in html
    assert 'name="sharer"' in html
    assert 'name="via"' in html
    assert f'value="{VIA_DIRECT}"' in html
    assert 'value="g_1"' in html
    assert "Physics 101" in html
    assert 'value="user_peer"' in html


def test_fragment_content_filtered_empty_vs_unfiltered_empty() -> None:
    assert "matches this filter" in to_xml(shared_items_content([], filtered=True))
    assert "Nothing shared with you yet" in to_xml(shared_items_content([], filtered=False))


# ---------------------------------------------------------------- the wall


def test_wall_row_has_a_stop_sharing_chip_per_audience_member() -> None:
    html = to_xml(WallRow(_wall_item()))
    assert 'id="wall-ue_65688cb7"' in html
    assert 'href="/gradebook/ue_65688cb7"' in html
    assert "Alice" in html and "Physics 101" in html
    assert 'hx-post="/api/user-entries/ue_65688cb7/unshare?audience=user:alice"' in html
    assert 'hx-post="/api/user-entries/ue_65688cb7/unshare?audience=group:g_1"' in html
    assert 'hx-target="#wall-ue_65688cb7"' in html
    assert 'hx-swap="outerHTML"' in html


def test_wall_empty_state() -> None:
    assert "not shared anything yet" in to_xml(wall_content([]))


# ---------------------------------------------------------------- page


def test_page_has_both_sides() -> None:
    html = to_xml(SharedPage([_item(_ENTRY_PROPS)], [_wall_item()]))
    assert "Shared with you" in html
    assert "Your wall" in html
    assert f'id="{SHARED_LIST_ID}"' in html
    assert f'id="{WALL_ID}"' in html
    assert 'name="via"' in html


def test_page_empty_inbox_renders_no_filter_bar() -> None:
    html = to_xml(SharedPage([], []))
    assert 'name="via"' not in html
    assert "Nothing shared with you yet" in html
