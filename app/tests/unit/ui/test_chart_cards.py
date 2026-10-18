"""Markup pins for the chartVis cards.

A chart card names one thing: the URL of its Chart.js config. The config's own
``type`` decides the chart kind, so the card passes no chart type to
``chartVis``.

The rendered cards are also kept as fixture files under ``tests/js/fixtures/``,
where ``tests/js/chart-vis.test.js`` mounts them with the vendored Alpine. The
drift test keeps those files equal to what the Python renders; regenerate them
with ``SKUEL_WRITE_JS_FIXTURES=1 uv run pytest tests/unit/ui/test_chart_cards.py``.
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fasthtml.common import FT, to_xml

from ui.insights.components import render_charts_section
from ui.lifepath.alignment import _alignment_radar

FIXTURES = Path(__file__).resolve().parents[2] / "js" / "fixtures"

INSIGHT_CHART_URLS = [
    "/api/insights/charts/impact-distribution",
    "/api/insights/charts/domain-distribution",
    "/api/insights/charts/type-distribution",
    "/api/insights/charts/action-rate",
]


def _walk(node: object) -> Iterator[FT]:
    if isinstance(node, FT):
        yield node
        for child in node.children:
            yield from _walk(child)
    elif isinstance(node, list | tuple):
        for child in node:
            yield from _walk(child)


def _chart_mounts(tree: FT | None) -> list[str]:
    return [
        str(el.attrs["x-data"])
        for el in _walk(tree)
        if str(el.attrs.get("x-data", "")).startswith("chartVis(")
    ]


def _insight_charts() -> FT:
    section = render_charts_section(insight_count=3)
    assert section is not None
    return section


def test_insight_charts_pass_only_their_config_url() -> None:
    assert _chart_mounts(_insight_charts()) == [f"chartVis('{url}')" for url in INSIGHT_CHART_URLS]


def test_alignment_radar_passes_only_its_config_url() -> None:
    assert _chart_mounts(_alignment_radar()) == ["chartVis('/api/lifepath/alignment/chart')"]


def test_too_few_insights_render_no_charts() -> None:
    assert render_charts_section(insight_count=2) is None


FIXTURE_SURFACES: dict[str, Callable[[], FT]] = {
    "insight-charts.html": _insight_charts,
    "alignment-radar.html": _alignment_radar,
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
        "uv run pytest tests/unit/ui/test_chart_cards.py"
    )
