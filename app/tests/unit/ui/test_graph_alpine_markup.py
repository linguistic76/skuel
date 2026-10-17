"""Markup pins for the graph and Explore Alpine components.

Alpine calls a component's own ``init()`` when it mounts the ``x-data``
element, so an ``x-init="init()"`` beside it runs the component a second time
(two graph fetches, two document listeners). A directive outside every
``x-data`` element is never bound, so the depth select must sit inside the
``relationshipGraph`` scope.

The rendered markup of the two graph components is also kept as fixture files
under ``tests/js/fixtures/``, where ``tests/js/graph-components.test.js`` mounts
it with the vendored Alpine. The drift test here keeps those files equal to
what the Python renders; regenerate them with
``SKUEL_WRITE_JS_FIXTURES=1 uv run pytest tests/unit/ui/test_graph_alpine_markup.py``.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fasthtml.common import FT, Div, to_xml

from core.constants import GraphDepth
from core.models.type_hints import EntityUID
from ui.explore.cards import render_explore_search_panel
from ui.explore.graph import ExploreGraphView
from ui.explore.nav import render_explore_sidebar_page
from ui.patterns.relationships.relationship_graph import RelationshipGraphView

FIXTURES = Path(__file__).resolve().parents[2] / "js" / "fixtures"

COMPONENTS = ("relationshipGraph(", "exploreGraph(", "exploreSearch(")

SIDEBAR_DATA: dict[str, list[str]] = {
    "studying_kus": [],
    "in_progress_ps": [],
    "pinned_items": [],
    "understood_kus": [],
}


def _walk(node: object) -> Iterator[FT]:
    if isinstance(node, FT):
        yield node
        for child in node.children:
            yield from _walk(child)
    elif isinstance(node, list | tuple):
        for child in node:
            yield from _walk(child)


def _component_roots(tree: FT) -> list[FT]:
    return [el for el in _walk(tree) if str(el.attrs.get("x-data", "")).startswith(COMPONENTS)]


def _rendered_surfaces() -> dict[str, FT]:
    return {
        "RelationshipGraphView": RelationshipGraphView(EntityUID("task_abc"), "tasks"),
        "ExploreGraphView standalone": ExploreGraphView(mode="hub"),
        "Explore sidebar, signed out": render_explore_sidebar_page(Div("x"), None, None),
        "Explore sidebar, signed in": render_explore_sidebar_page(Div("x"), SIDEBAR_DATA, None),
        "Explore search panel": render_explore_search_panel(["yoga", "breath"]),
    }


@pytest.mark.parametrize("surface", list(_rendered_surfaces()))
def test_component_mounts_without_a_second_init(surface: str) -> None:
    tree = _rendered_surfaces()[surface]
    roots = _component_roots(tree)
    assert roots, f"{surface}: no component root rendered"
    for root in roots:
        assert "x-init" not in root.attrs, (
            f"{surface}: x-init beside {root.attrs['x-data']} runs init() twice"
        )


def _graph_root(depth: int = GraphDepth.NEIGHBORHOOD) -> FT:
    (root,) = _component_roots(RelationshipGraphView(EntityUID("task_abc"), "tasks", depth))
    return root


def _depth_select(root: FT) -> FT:
    selects = [el for el in _walk(root) if el.tag == "select"]
    assert len(selects) == 1, "the depth select is not inside the relationshipGraph scope"
    return selects[0]


def test_depth_select_is_bound_by_the_graph_scope() -> None:
    select = _depth_select(_graph_root())
    assert select.attrs["x-on:change"] == "changeDepth($event.target.value)"
    assert select.attrs["aria-label"] == "Graph depth"


def test_depth_options_stop_at_the_route_cap() -> None:
    select = _depth_select(_graph_root())
    values = [int(el.attrs["value"]) for el in _walk(select) if el.tag == "option"]
    assert values == list(range(GraphDepth.DIRECT, GraphDepth.DEFAULT + 1))


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_the_initial_depth_is_the_selected_option(depth: int) -> None:
    select = _depth_select(_graph_root(depth))
    selected = [
        el.attrs["value"] for el in _walk(select) if el.tag == "option" and el.attrs.get("selected")
    ]
    assert selected == [str(depth)]


def test_graph_scope_renders_its_error() -> None:
    slots = [el for el in _walk(_graph_root()) if el.attrs.get("x-text") == "error"]
    assert len(slots) == 1
    assert slots[0].attrs.get("x-show") == "error"


def test_graph_scope_reloads_on_relationships_changed() -> None:
    root = _graph_root()
    assert root.attrs["x-on:relationships-changed.window"] == "loadGraph(depth)"


FIXTURE_SURFACES = {
    "relationship-graph.html": lambda: RelationshipGraphView(EntityUID("task_abc"), "tasks"),
    "explore-graph.html": lambda: ExploreGraphView(mode="hub"),
}


@pytest.mark.parametrize("name", list(FIXTURE_SURFACES))
def test_js_fixture_matches_the_rendered_markup(name: str) -> None:
    rendered = to_xml(FIXTURE_SURFACES[name]())
    path = FIXTURES / name
    if os.environ.get("SKUEL_WRITE_JS_FIXTURES") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered)
    assert path.exists() and path.read_text() == rendered, (
        f"{path} is stale — regenerate with SKUEL_WRITE_JS_FIXTURES=1 "
        "uv run pytest tests/unit/ui/test_graph_alpine_markup.py"
    )
