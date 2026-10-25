"""The /insights chart configs' colours, pinned to the exact strings Chart.js draws.

``InsightStore``'s four chart configs take their colours from
``core/utils/palette.py`` (``ChartColor``, ``SemanticColor``) and, for the type
doughnut, ``InsightType.get_color()``, through ``rgba()``.
A palette value that moves moves a colour a learner sees, so each serialized
string is pinned here.
"""

from unittest.mock import MagicMock

import pytest

from core.models.insight.persisted_insight import InsightField, InsightType
from core.ports.query_types import ChartJsConfig
from core.services.insight.insight_store import InsightStore
from core.utils.palette import rgba
from core.utils.result_simplified import Result

# The backend's grouped-count rows, one list per field.
COUNT_ROWS: dict[InsightField, list[dict[str, object]]] = {
    InsightField.IMPACT: [{"value": v, "count": 1} for v in ("critical", "high", "low")],
    InsightField.DOMAIN: [{"value": "habits", "count": 2}, {"value": "tasks", "count": 1}],
    InsightField.INSIGHT_TYPE: [
        {"value": "streak_pattern", "count": 2},
        {"value": "knowledge_gap", "count": 1},
    ],
}


@pytest.fixture
def store() -> InsightStore:
    backend = MagicMock()

    async def count_by(_user_uid: str, field: InsightField) -> Result[list[dict[str, object]]]:
        return Result.ok(COUNT_ROWS[field])

    backend.count_active_insights_by = count_by
    store = InsightStore(backend=backend)

    async def stats(_user_uid: str) -> Result[dict[str, float]]:
        return Result.ok({"action_rate": 0.25})

    store.get_insight_stats = stats  # type: ignore[method-assign,assignment]
    return store


def _background(config: ChartJsConfig | None) -> object:
    assert config is not None
    return config["data"]["datasets"][0]["backgroundColor"]


async def test_impact_doughnut_colours(store: InsightStore) -> None:
    config = (await store.get_impact_distribution_chart("user_x")).value
    assert _background(config) == [
        "rgba(220, 38, 38, 0.8)",
        "rgba(234, 88, 12, 0.8)",
        "rgba(250, 204, 21, 0.8)",
        "rgba(34, 197, 94, 0.8)",
    ]


async def test_domain_bar_colour(store: InsightStore) -> None:
    config = (await store.get_domain_distribution_chart("user_x")).value
    assert _background(config) == "rgba(59, 130, 246, 0.8)"


async def test_type_doughnut_colours_follow_the_type(store: InsightStore) -> None:
    """Each slice takes its type's own colour, whatever place its count gives it."""
    config = (await store.get_type_distribution_chart("user_x")).value
    assert _background(config) == [
        rgba(InsightType.STREAK_PATTERN.get_color(), 0.8),
        rgba(InsightType.KNOWLEDGE_GAP.get_color(), 0.8),
    ]
    assert _background(config) == ["rgba(14, 142, 79, 0.8)", "rgba(19, 132, 183, 0.8)"]


async def test_type_doughnut_refuses_a_stored_type_outside_the_enum(store: InsightStore) -> None:
    COUNT_ROWS[InsightField.INSIGHT_TYPE].append({"value": "retired_type", "count": 1})
    try:
        result = await store.get_type_distribution_chart("user_x")
    finally:
        COUNT_ROWS[InsightField.INSIGHT_TYPE].pop()
    assert result.is_error


async def test_action_rate_gauge_colours(store: InsightStore) -> None:
    config = (await store.get_action_rate_chart("user_x")).value
    assert _background(config) == ["rgba(34, 197, 94, 0.8)", "rgba(156, 163, 175, 0.3)"]


@pytest.mark.parametrize(
    ("hex_colour", "alpha", "expected"),
    [
        ("#3B82F6", 0.8, "rgba(59, 130, 246, 0.8)"),
        ("#3b82f6", 1, "rgba(59, 130, 246, 1)"),
        ("#9CA3AF", 0.3, "rgba(156, 163, 175, 0.3)"),
    ],
)
def test_rgba_spells_a_hex_colour_with_an_alpha(
    hex_colour: str, alpha: float, expected: str
) -> None:
    assert rgba(hex_colour, alpha) == expected


@pytest.mark.parametrize("bad", ["3B82F6", "#3B82F", "#3B82F6FF", "#GGGGGG"])
def test_rgba_refuses_anything_but_six_digit_hex(bad: str) -> None:
    with pytest.raises(ValueError, match="six-digit"):
        rgba(bad, 0.5)
