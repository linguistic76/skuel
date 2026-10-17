"""Accessibility pins: status colour contrast, banner politeness, control height.

- Each status token (``text-error`` / ``-success`` / ``-warning`` / ``-info``) is
  AA (4.5:1) as text on its theme's background, light and dark — computed from
  ``static/css/input.css``, the file Tailwind compiles.
- No class string puts status text on its own status tint (``bg-success/15
  text-success``): the light tokens fail AA on a tint of themselves (green-700 on
  its 15% tint is 4.09:1). A pill uses the Badge palette instead.
- An error banner is ``role="alert"`` alone: an ``aria-live="polite"`` beside it
  contradicts the role's implicit assertive politeness.
- ``Input`` and ``Select`` are 44px on phones and 40px from ``md`` up, and so is
  the Today quick-add row, whose title field is a raw ``Input``.
"""

import re
from datetime import date
from pathlib import Path

import pytest
from fasthtml.common import Option, to_xml

from ui.components import Input, Select
from ui.patterns.error_banner import render_error_banner, render_inline_error
from ui.today.page import _quick_add

APP_ROOT = Path(__file__).resolve().parents[3]
INPUT_CSS = (APP_ROOT / "static" / "css" / "input.css").read_text()
STATUSES = ("error", "success", "warning", "info")
AA_TEXT = 4.5


def _block(selector: str) -> str:
    match = re.search(
        rf"^\s*{re.escape(selector)} \{{(.*?)^\s*\}}", INPUT_CSS, re.MULTILINE | re.DOTALL
    )
    assert match, f"no {selector} block in input.css"
    return match.group(1)


def _var(block: str, name: str) -> str:
    match = re.search(rf"--{name}:\s*([^;]+);", block)
    assert match, f"--{name} missing"
    return match.group(1).strip()


def _hex_rgb(value: str) -> tuple[float, float, float]:
    h = value.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


def _hsl_rgb(value: str) -> tuple[float, float, float]:
    hue, sat, light = (float(part.rstrip("%")) for part in value.split())
    s, lum = sat / 100, light / 100
    c = (1 - abs(2 * lum - 1)) * s
    x = c * (1 - abs((hue / 60) % 2 - 1))
    m = lum - c / 2
    sector = int(hue // 60) % 6
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][sector]
    return (r + m, g + m, b + m)


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_status_tokens_read_the_theme_variables() -> None:
    theme = _block("@theme inline")
    for status in STATUSES:
        assert _var(theme, f"color-{status}") == f"var(--status-{status})"


@pytest.mark.parametrize("theme", [":root", ".dark"])
@pytest.mark.parametrize("status", STATUSES)
def test_status_text_is_aa_on_its_theme_background(theme: str, status: str) -> None:
    block = _block(theme)
    background = _hsl_rgb(_var(block, "background"))
    ratio = _contrast(_hex_rgb(_var(block, f"status-{status}")), background)
    assert ratio >= AA_TEXT, f"{theme} --status-{status} is {ratio:.2f}:1 on --background"


_TINTED_TEXT = re.compile(r"\bbg-(error|success|warning|info)/\d+\b[^\"']*\btext-\1\b")


def test_no_class_string_puts_status_text_on_its_own_tint() -> None:
    offenders: list[str] = []
    for root in ("ui", "adapters"):
        for path in sorted((APP_ROOT / root).rglob("*.py")):
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                if _TINTED_TEXT.search(line):
                    offenders.append(f"{path.relative_to(APP_ROOT)}:{lineno}")
    assert offenders == []


@pytest.mark.parametrize("severity", ["error", "warning"])
def test_an_error_banner_is_an_alert_without_a_politeness_override(severity: str) -> None:
    xml = to_xml(render_error_banner("Unable to save", severity=severity))
    assert 'role="alert"' in xml
    assert "aria-live" not in xml


def test_an_info_banner_is_a_status() -> None:
    xml = to_xml(render_error_banner("Not generated yet", severity="info"))
    assert 'role="status"' in xml
    assert "aria-live" not in xml


def test_an_inline_error_is_an_alert_without_a_politeness_override() -> None:
    xml = to_xml(render_inline_error("Title is required"))
    assert 'role="alert"' in xml
    assert "aria-live" not in xml


@pytest.mark.parametrize(
    "control",
    [Input(name="title"), Select(Option("a", value="a"), name="kind")],
    ids=["Input", "Select"],
)
def test_form_controls_are_44px_on_phones_and_40px_from_md(control: object) -> None:
    classes = re.search(r'class="([^"]*)"', to_xml(control))
    assert classes
    tokens = classes.group(1).split()
    assert "h-11" in tokens and "md:h-10" in tokens
    assert "h-10" not in tokens


@pytest.mark.parametrize("tag", ["input", "button"])
def test_today_quick_add_row_is_44px_on_phones_and_40px_from_md(tag: str) -> None:
    """The quick-add title field is a raw ``Input``, outside the component's
    heights; its button matches it so the row stays aligned."""
    xml = to_xml(_quick_add(date(2026, 10, 17)))
    controls = [el for el in re.findall(rf"<{tag}\b[^>]*>", xml) if 'type="hidden"' not in el]
    assert len(controls) == 1
    classes = re.search(r'class="([^"]*)"', controls[0])
    assert classes
    tokens = classes.group(1).split()
    assert "h-11" in tokens and "md:h-10" in tokens
    assert "h-10" not in tokens
