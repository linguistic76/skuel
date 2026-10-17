"""Accessibility pins: status colour contrast, banner politeness, control height.

- Each status token (``text-error`` / ``-success`` / ``-warning`` / ``-info``) is
  AA (4.5:1) as text on its theme's background, light and dark — computed from
  ``static/css/input.css``, the file Tailwind compiles.
- No class string puts status text on its own status tint (``bg-success/15
  text-success``): the light tokens fail AA on a tint of themselves (green-700 on
  its 15% tint is 4.09:1). A pill uses the Badge palette instead.
- No light-only ``base-*`` colour: ``input.css`` defines no ``--color-base-*``
  token and no ``.py`` or ``static/js`` file names a ``base-100/200/300/content``
  utility. The text and surface pairs the panels and wells draw are AA in both
  themes.
- An error banner is ``role="alert"`` alone: an ``aria-live="polite"`` beside it
  contradicts the role's implicit assertive politeness.
- ``Input`` and ``Select`` are 44px on phones and 40px from ``md`` up; with
  ``compact=True`` (dense chat chrome) 44px on phones and 32px from ``md``. Each
  renders one utility per property per breakpoint — two would be decided by
  their order in ``output.css``, not by the component — and ``full_width``
  picks exactly one width. The Today quick-add row matches the field height.
"""

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from fasthtml.common import Option, to_xml

from ui.components import Input, Select, TextArea
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


_BASE_UTILITY = re.compile(r"\bbase-(100|200|300|content)\b")


def _base_utility_offenders() -> list[str]:
    offenders = [
        f"static/css/input.css: {m.group(0)}"
        for m in re.finditer(r"--color-base-[\w-]+", INPUT_CSS)
    ]
    sources = [p for root in ("ui", "adapters", "core") for p in (APP_ROOT / root).rglob("*.py")]
    sources += (APP_ROOT / "static" / "js").rglob("*.js")
    for path in sorted(sources):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if _BASE_UTILITY.search(line):
                offenders.append(f"{path.relative_to(APP_ROOT)}:{lineno}")
    return offenders


def test_no_light_only_base_colour_token_or_utility() -> None:
    assert _base_utility_offenders() == []


def test_the_base_utility_scan_sees_a_class_string() -> None:
    assert _BASE_UTILITY.search('cls="rounded bg-base-200 p-4"')
    assert _BASE_UTILITY.search('cls="text-base-content/70"')
    assert not _BASE_UTILITY.search('cls="text-base font-semibold"')


# (text, alpha, surface) — every pair the panels and wells draw. A titled panel is
# a card (the page background in both themes, so the status tokens hold on it);
# faded text inside a muted well is foreground at an opacity, never
# muted-foreground, which is 4.34:1 on light muted.
_SURFACE_PAIRS = [
    ("muted-foreground", 1.0, "card"),
    ("foreground", 0.8, "card"),
    ("foreground", 1.0, "muted"),
    ("foreground", 0.6, "muted"),
]


def _mix(
    top: tuple[float, float, float], under: tuple[float, float, float], alpha: float
) -> tuple[float, float, float]:
    r, g, b = (alpha * t + (1 - alpha) * u for t, u in zip(top, under, strict=True))
    return (r, g, b)


@pytest.mark.parametrize("theme", [":root", ".dark"])
@pytest.mark.parametrize(("text", "alpha", "surface"), _SURFACE_PAIRS)
def test_surface_text_pairs_are_aa(theme: str, text: str, alpha: float, surface: str) -> None:
    block = _block(theme)
    under = _hsl_rgb(_var(block, surface))
    ratio = _contrast(_mix(_hsl_rgb(_var(block, text)), under, alpha), under)
    assert ratio >= AA_TEXT, f"{theme} {text}/{alpha} on {surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", [":root", ".dark"])
def test_a_card_panel_is_the_page_background(theme: str) -> None:
    block = _block(theme)
    assert _var(block, "card") == _var(block, "background")


@pytest.mark.parametrize("theme", [":root", ".dark"])
def test_error_text_is_aa_on_a_faint_muted_well(theme: str) -> None:
    block = _block(theme)
    well = _mix(_hsl_rgb(_var(block, "muted")), _hsl_rgb(_var(block, "background")), 0.4)
    ratio = _contrast(_hex_rgb(_var(block, "status-error")), well)
    assert ratio >= AA_TEXT, f"{theme} --status-error is {ratio:.2f}:1 on muted/40"


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


_PROPERTY_PREFIXES = {
    "height": ("h-",),
    "width": ("w-",),
    "padding-x": ("px-", "pl-", "pr-", "p-"),
    "padding-y": ("py-", "pt-", "pb-", "p-"),
    "radius": ("rounded",),
    "font-size": ("text-sm", "text-xs", "text-13", "text-base", "text-lg"),
    "display": ("flex", "block", "inline-flex", "inline-block", "grid"),
}


def _tokens(control: object) -> list[str]:
    classes = re.search(r'class="([^"]*)"', to_xml(control))
    assert classes
    return classes.group(1).split()


def _conflicts(tokens: list[str]) -> list[str]:
    """Two utilities for one property at one breakpoint (variants like ``focus-visible:`` skipped)."""
    found: list[str] = []
    for breakpoint in ("", "md:"):
        plain = [
            token.removeprefix(breakpoint)
            for token in tokens
            if token.startswith(breakpoint) and ":" not in token.removeprefix(breakpoint)
        ]
        for prop, prefixes in _PROPERTY_PREFIXES.items():
            hits = [token for token in plain if token.startswith(prefixes)]
            if len(hits) > 1:
                found.append(f"{breakpoint}{prop}: {hits}")
    return found


@pytest.mark.parametrize("full_width", [True, False])
@pytest.mark.parametrize("make", [Input, Select], ids=["Input", "Select"])
def test_compact_controls_are_44px_on_phones_and_32px_from_md(
    make: Callable[..., object], full_width: bool
) -> None:
    tokens = _tokens(make(name="model", compact=True, full_width=full_width))
    assert "h-11" in tokens and "md:h-8" in tokens
    assert "md:h-10" not in tokens
    assert "text-13" in tokens


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("full_width", [True, False])
@pytest.mark.parametrize("make", [Input, Select, TextArea], ids=["Input", "Select", "TextArea"])
def test_a_field_renders_one_utility_per_property(
    make: Callable[..., object], full_width: bool, compact: bool
) -> None:
    kwargs: dict[str, object] = {"name": "f", "full_width": full_width}
    if compact and make is not TextArea:
        kwargs["compact"] = True
    tokens = _tokens(make(**kwargs))
    assert _conflicts(tokens) == []
    assert ("w-full" in tokens) is full_width
    assert ("w-auto" in tokens) is not full_width


def test_the_conflict_check_sees_a_restated_property() -> None:
    assert _conflicts(["h-11", "md:h-10", "h-10"]) == ["height: ['h-11', 'h-10']"]
    assert _conflicts(["px-3", "pl-9"]) == ["padding-x: ['px-3', 'pl-9']"]
    assert _conflicts(["w-full", "md:w-auto", "focus-visible:ring-2"]) == []


@pytest.mark.parametrize("tag", ["input", "button"])
def test_today_quick_add_row_is_44px_on_phones_and_40px_from_md(tag: str) -> None:
    """The quick-add title field is the component ``Input``; its button matches
    the field's heights so the row stays aligned."""
    xml = to_xml(_quick_add(date(2026, 10, 17)))
    controls = [el for el in re.findall(rf"<{tag}\b[^>]*>", xml) if 'type="hidden"' not in el]
    assert len(controls) == 1
    classes = re.search(r'class="([^"]*)"', controls[0])
    assert classes
    tokens = classes.group(1).split()
    assert "h-11" in tokens and "md:h-10" in tokens
    assert "h-10" not in tokens
