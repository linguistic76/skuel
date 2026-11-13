"""A statistic's value colour is a token with a compiled text class."""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest
from fasthtml.common import to_xml

from ui.patterns.stats_grid import StatCard, StatColor, StatItem, StatsGrid, value_color_class

_OUTPUT_CSS = Path(__file__).resolve().parents[3] / "static" / "css" / "output.css"


def test_every_stat_colour_has_a_class_in_the_compiled_stylesheet() -> None:
    css = _OUTPUT_CSS.read_text()
    for color in get_args(StatColor):
        cls = value_color_class(color)
        assert cls == f"text-{color}"
        assert re.search(rf"\.{re.escape(cls)}[,{{]", css), f"{cls} is not compiled"


def test_a_value_with_no_colour_takes_the_default_text_colour() -> None:
    assert value_color_class(None) == "text-foreground"
    assert "text-foreground" in to_xml(StatCard(label="Total", value=3))


@pytest.mark.parametrize("color", ["purple-600", "orange-600", "accent", "secondary", ""])
def test_a_colour_outside_the_tokens_is_refused(color: str) -> None:
    with pytest.raises(ValueError, match="not a stat colour"):
        value_color_class(color)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not a stat colour"):
        StatsGrid([StatItem(label="Habits", value=4, color=color)])  # type: ignore[arg-type]


def test_a_token_colours_the_value() -> None:
    html = to_xml(StatsGrid([StatItem(label="Mastered", value=4, color="success")]))
    assert "text-3xl font-bold text-success" in html
