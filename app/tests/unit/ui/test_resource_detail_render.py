"""render_resource_detail "Cited by" section — render-shape guard (PR 4).

The Resource detail page reverse-traverses CITES_RESOURCE to show who cites the
work. These tests render the section from flat citer rows (uid, title,
entity_type, locator) exactly as the service returns them, so citer-routing,
locator display, and the empty-state guard fail here instead of at runtime.
"""

from __future__ import annotations

from types import SimpleNamespace

from fasthtml.common import to_xml

from ui.library.resource_detail import render_resource_detail


def _resource() -> SimpleNamespace:
    return SimpleNamespace(
        uid="resource.tao-of-pooh",
        title="The Tao of Pooh",
        media_type=None,
        author="Benjamin Hoff",
        publisher=None,
        publication_year=1982,
        isbn=None,
        resource_duration_minutes=None,
        description="A gentle introduction to Taoism.",
        tags=(),
        source_url=None,
    )


def test_ku_citer_row_links_and_shows_locator() -> None:
    """A Ku citer links to /explore/ku/{uid} and shows its locator."""
    html = to_xml(
        render_resource_detail(
            _resource(),
            cited_by=[
                {
                    "uid": "ku.values.tao-te-ching-v1",
                    "title": "Tao Te Ching",
                    "entity_type": "ku",
                    "locator": "ch. 4",
                }
            ],
        )
    )
    assert "Cited by" in html
    assert "/explore/ku/ku.values.tao-te-ching-v1" in html
    assert "Tao Te Ching" in html
    assert "ch. 4" in html


def test_path_step_citer_row_links_to_ps_detail() -> None:
    """A PathStep citer links to /explore/ps/{uid}."""
    html = to_xml(
        render_resource_detail(
            _resource(),
            cited_by=[
                {
                    "uid": "ps.mindfulness.breath-awareness-basics",
                    "title": "Breath Awareness Basics",
                    "entity_type": "path_step",
                    "locator": None,
                }
            ],
        )
    )
    assert "/explore/ps/ps.mindfulness.breath-awareness-basics" in html
    assert "Breath Awareness Basics" in html


def test_no_citers_renders_no_cited_by_heading() -> None:
    """Empty cited_by → no "Cited by" section at all (empty-state guard)."""
    html = to_xml(render_resource_detail(_resource(), cited_by=()))
    assert "Cited by" not in html
