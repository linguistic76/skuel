"""Markup for the hostile-value Alpine test, rendered from the Python.

``tests/js/alpine-hostile-values.test.js`` mounts these fixtures with the
vendored Alpine and checks that a value carrying quotes, a backslash, a newline,
U+2028 or a closing ``</script>`` reaches the component as data: no injected
code runs, and the component state equals the value exactly. The values are
``tests/js/fixtures/hostile-values.json``, read by both sides.

The drift test keeps each fixture equal to what the Python renders; regenerate
with ``SKUEL_WRITE_JS_FIXTURES=1 uv run pytest tests/unit/ui/test_alpine_hostile_fixtures.py``.
"""

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from fasthtml.common import Div, to_xml

from core.models.group.group import Group
from ui.groups.hub import GroupsHub
from ui.insights.components import InsightsFilters, render_filter_form

FIXTURES = Path(__file__).resolve().parents[2] / "js" / "fixtures"
HOSTILE: list[str] = json.loads((FIXTURES / "hostile-values.json").read_text())


def _insight_filters() -> str:
    """One filter form per hostile value, the value in every request-derived field."""
    return to_xml(
        Div(
            *(
                Div(
                    render_filter_form(
                        InsightsFilters(
                            domain=value,
                            impact=value,
                            search=value,
                            insight_type=value,
                            action_status=value,
                            offset=0,
                        )
                    ),
                    data_case=str(index),
                )
                for index, value in enumerate(HOSTILE)
            )
        )
    )


def _groups_hub() -> str:
    """The groups hub with one group per hostile uid, the first one active."""
    groups = [Group(uid=value, name=f"Group {index}") for index, value in enumerate(HOSTILE)]
    return to_xml(GroupsHub(groups, active_group_uid=HOSTILE[0]))


RENDERERS: dict[str, Callable[[], str]] = {
    "insight-filters-hostile.html": _insight_filters,
    "groups-hub-hostile.html": _groups_hub,
}


@pytest.mark.parametrize("name", list(RENDERERS))
def test_hostile_fixture_matches_the_render(name: str) -> None:
    rendered = RENDERERS[name]()
    path = FIXTURES / name
    if os.environ.get("SKUEL_WRITE_JS_FIXTURES") == "1":
        path.write_text(rendered)
    assert path.exists() and path.read_text() == rendered, (
        f"{path} is stale — regenerate with SKUEL_WRITE_JS_FIXTURES=1 "
        "uv run pytest tests/unit/ui/test_alpine_hostile_fixtures.py"
    )
