"""entity_detail_href — the one entity_type → detail-URL mapping.

Cross-type graph surfaces (MOC card grids on /gradebook/{uid}) resolve child
hrefs through this helper; the mapping must match the live route shapes
(query-param for activity/report domains, path-param for explore/lp/gradebook).
"""

from __future__ import annotations

import pytest

from core.ports.query_types import OrganizerResult
from ui.patterns.entity_links import entity_detail_href
from ui.patterns.hub import hub_cards_from_organizers


@pytest.mark.parametrize(
    ("entity_type", "expected"),
    [
        ("task", "/tasks/detail?uid=tk_1"),
        ("goal", "/goals/detail?uid=tk_1"),
        ("habit", "/habits/detail?uid=tk_1"),
        ("event", "/events/detail?uid=tk_1"),
        ("choice", "/choices/detail?uid=tk_1"),
        ("principle", "/principles/detail?uid=tk_1"),
        ("ku", "/explore/ku/tk_1"),
        ("path_step", "/explore/ps/tk_1"),
        ("learning_path", "/lp/tk_1"),
        ("exercise", "/exercises/get?uid=tk_1"),
        ("user_entry", "/gradebook/tk_1"),
        ("entry_report", "/entry-reports/detail?uid=tk_1"),
        ("activity_report", "/activity-reports/detail?uid=tk_1"),
        ("revised_exercise", "/revised-exercises/detail?uid=tk_1"),
    ],
)
def test_detail_href_mapping(entity_type: str, expected: str) -> None:
    assert entity_detail_href(entity_type, "tk_1") == expected


@pytest.mark.parametrize("entity_type", ["resource", "interaction", "life_path", None])
def test_types_without_detail_pages_resolve_none(entity_type: str | None) -> None:
    assert entity_detail_href(entity_type, "tk_1") is None


def test_hub_cards_href_for_overrides_template_and_sorts_by_order() -> None:
    def _href(child: OrganizerResult) -> str:
        return entity_detail_href(child.get("entity_type"), child["uid"]) or "#"

    children: list[OrganizerResult] = [
        {"uid": "tk_2", "title": "Second", "order": 1, "entity_type": "task"},
        {"uid": "ku.ns.first", "title": "First", "order": 0, "entity_type": "ku"},
        {"uid": "x_unknown", "title": "Unmapped", "order": 2, "entity_type": "interaction"},
    ]
    cards = hub_cards_from_organizers(children, href_for=_href)

    assert [c.name for c in cards] == ["First", "Second", "Unmapped"]
    assert cards[0].href == "/explore/ku/ku.ns.first"
    assert cards[1].href == "/tasks/detail?uid=tk_2"
    assert cards[2].href == "#"


def test_hub_cards_template_path_still_default() -> None:
    children: list[OrganizerResult] = [
        {"uid": "ku.ns.a", "title": "A", "order": 0, "entity_type": "ku"},
    ]
    cards = hub_cards_from_organizers(children)
    assert cards[0].href == "/ku/ku.ns.a"
