"""A bare ``border`` utility takes the theme's border token, in light and in dark.

``Card`` and every other element that names no border colour inherit this rule, so a
palette colour here puts one fixed colour on all of them in both themes.
"""

from __future__ import annotations

import re
from pathlib import Path

_INPUT_CSS = Path(__file__).resolve().parents[3] / "static" / "css" / "input.css"


def test_the_default_border_colour_is_the_theme_token() -> None:
    rule = re.search(
        r"\*,\s*::after,\s*::before,\s*::backdrop,\s*::file-selector-button\s*\{\s*"
        r"border-color:\s*([^;]+);",
        _INPUT_CSS.read_text(),
    )

    assert rule, "the base rule that sets the default border colour is gone"
    assert rule.group(1) == "var(--color-border, currentcolor)"
