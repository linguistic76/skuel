"""``InsightType.get_color()`` — one colour per type, readable in both themes.

The type doughnut colours each slice by its type, so a type looks the same on every
visit. Each colour is pinned as Chart.js draws it, at ``ChartColor.FILL_ALPHA`` over
the chart's surface (``--card``, from ``static/css/input.css``) in the light and the
dark theme:

- every colour is at least 3:1 against both surfaces (WCAG 1.4.11, a graphical object);
- no two colours are closer than ``MIN_DELTA_E`` (CIE76, in CIE Lab) on either surface.
"""

import colorsys
import itertools
import math
import re
from pathlib import Path

import pytest

from core.models.insight.persisted_insight import InsightType
from core.utils.palette import ChartColor

INPUT_CSS = Path(__file__).resolve().parents[3] / "static" / "css" / "input.css"
MIN_CONTRAST = 3.0
MIN_DELTA_E = 20.0

RGB = tuple[float, float, float]


def _token(block_selector: str, name: str) -> RGB:
    """An HSL-triplet token from a block of input.css, as sRGB 0-255."""
    css = INPUT_CSS.read_text()
    block = re.search(rf"\n  {re.escape(block_selector)} \{{(.*?)\n  \}}", css, re.DOTALL)
    assert block, f"{block_selector} block not found in input.css"
    value = re.search(rf"--{name}: ([\d.]+) ([\d.]+)% ([\d.]+)%;", block.group(1))
    assert value, f"--{name} not found under {block_selector}"
    hue, saturation, lightness = (float(part) for part in value.groups())
    red, green, blue = colorsys.hls_to_rgb(hue / 360, lightness / 100, saturation / 100)
    return (red * 255, green * 255, blue * 255)


SURFACES = {"light": _token(":root", "card"), "dark": _token(".dark", "card")}


def _hex(colour: str) -> RGB:
    return (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16))


def _drawn(colour: str, surface: RGB) -> RGB:
    rgb = _hex(colour)
    alpha = ChartColor.FILL_ALPHA
    return (
        rgb[0] * alpha + surface[0] * (1 - alpha),
        rgb[1] * alpha + surface[1] * (1 - alpha),
        rgb[2] * alpha + surface[2] * (1 - alpha),
    )


def _linear(channel: float) -> float:
    channel /= 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _luminance(rgb: RGB) -> float:
    red, green, blue = (_linear(c) for c in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(a: RGB, b: RGB) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _lab(rgb: RGB) -> RGB:
    red, green, blue = (_linear(c) for c in rgb)
    x = (0.4124 * red + 0.3576 * green + 0.1805 * blue) / 0.95047
    y = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    z = (0.0193 * red + 0.1192 * green + 0.9505 * blue) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))


def test_every_type_has_a_six_digit_hex_colour() -> None:
    for insight_type in InsightType:
        assert re.fullmatch(r"#[0-9A-F]{6}", insight_type.get_color()), insight_type


def test_no_two_types_share_a_colour() -> None:
    colours = [insight_type.get_color() for insight_type in InsightType]
    assert len(set(colours)) == len(colours)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_colour_reaches_3_to_1_on_the_chart_surface(theme: str) -> None:
    surface = SURFACES[theme]
    low = {
        insight_type.value: round(_contrast(_drawn(insight_type.get_color(), surface), surface), 2)
        for insight_type in InsightType
        if _contrast(_drawn(insight_type.get_color(), surface), surface) < MIN_CONTRAST
    }
    assert low == {}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_two_colours_are_close_on_the_chart_surface(theme: str) -> None:
    surface = SURFACES[theme]
    close = {
        (a.value, b.value): round(
            math.dist(_lab(_drawn(a.get_color(), surface)), _lab(_drawn(b.get_color(), surface))), 1
        )
        for a, b in itertools.combinations(InsightType, 2)
        if math.dist(_lab(_drawn(a.get_color(), surface)), _lab(_drawn(b.get_color(), surface)))
        < MIN_DELTA_E
    }
    assert close == {}


def test_the_surfaces_are_read_from_input_css() -> None:
    """The control: the light card is white and the dark card is #020817."""
    assert tuple(round(c) for c in SURFACES["light"]) == (255, 255, 255)
    assert tuple(round(c) for c in SURFACES["dark"]) == (2, 8, 23)
