"""No colour ignores the theme.

A fixed-palette fill (``bg-slate-50``, ``bg-red-50``, ``bg-white``) paints the same in
both themes. Under text that follows the theme, it goes unreadable in dark mode: light
text on a light slab. Under its own fixed text, it stays a pale patch on a dark page. A
fill follows the theme in one of two ways:

- **A neutral fill is a theme token**: ``bg-muted``, ``bg-muted/50``, ``bg-card``,
  ``bg-background``, ``bg-foreground/10``. A neutral palette fill (slate, gray, zinc,
  neutral, stone) at shade 300 or lighter, or an opaque ``bg-white``, is refused, because
  a token covers each one.
- **A coloured light fill** (shade 300 or lighter) carries its dark twin in the same
  literal (``bg-red-50 dark:bg-red-400/10``), and so does every coloured text in that
  literal (``text-red-800 dark:text-red-300``).

A coloured text follows the theme the same way:

- **On no fill of its own**, a coloured text (shade 500 or darker) is fixed whatever it
  sits on: ``text-blue-600`` is 3.6:1 on the dark background, ``text-yellow-600`` 2.9:1 on
  the light one. A status colour is a status token (``text-success``, ``text-warning``,
  ``text-error``, ``text-info``, each AA on both backgrounds); any other carries its dark
  twin (``text-violet-700 dark:text-violet-300``). Text on a fill set by another element
  moves into the fill's literal, so the judge sees what it sits on.
- **``destructive`` names a fill**: the danger button's, dark ``#7f1d1d``, under its
  ``text-destructive-foreground``. As text, a border or a faint tint it is 2.0:1 or less
  on the dark background; those are ``error`` (identical in light).

Some fills pass because they read on both themes: a saturated fill (shade 400 or darker,
such as a dot, a bar or a count badge) and a translucent overlay (``bg-black/50``,
``bg-white/20``). A literal ``background`` in a style string is refused, because no class
census can see that fill. A style computed per entity, as an f-string (the avatar's hue,
a thread's colour), is data, not a palette choice, so the guard does not read it.

The literals the guard reads: every string constant under ``ui/``, ``adapters/inbound/``
and ``core/models/enums/`` (f-string parts included), and every quoted string in
``static/js/``.
"""

import ast
import re
from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parents[3]
_PY_ROOTS = ("ui", "adapters/inbound", "core/models/enums")
_NEUTRAL = "slate|gray|zinc|neutral|stone"
_HUE = (
    "red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple"
    "|fuchsia|pink|rose"
)
_EDGE_L, _EDGE_R = r"(?<![\w/:-])", r"(?![\w/-])"
_FILL = re.compile(
    rf"{_EDGE_L}((?:[a-z0-9-]+:)*)bg-(?:({_NEUTRAL})-(\d+)|({_HUE})-(\d+)|(white|black))(/\d+)?{_EDGE_R}"
)
_TEXT = re.compile(rf"{_EDGE_L}((?:[a-z0-9-]+:)*)text-(?:{_HUE})-(\d+){_EDGE_R}")
_DESTRUCTIVE = re.compile(
    rf"{_EDGE_L}(?:[a-z0-9-]+:)*(?:(?:text|border|ring|outline|divide|decoration|fill|stroke)"
    rf"-destructive(?:/\d+)?|bg-destructive/(?:[1-4]?\d)){_EDGE_R}"
)
_STYLE_BACKGROUND = re.compile(
    r"background(?:-color)?\s*:\s*(?:#|rgba?\(|hsla?\((?!\s*var)|oklch\(|white\b|black\b)",
    re.IGNORECASE,
)


def literal_problems(text: str, *, computed: bool = False) -> list[str]:
    """What is wrong with one literal's fills. ``computed``: an f-string part (its style
    colours are data, so only its classes are read)."""
    problems = [
        f"{match.group(0)}: destructive names a fill; text, borders and tints use error"
        for match in _DESTRUCTIVE.finditer(text)
    ]
    light_hue = own_fill = False
    for match in _FILL.finditer(text):
        variants, neutral, neutral_shade, hue, hue_shade, black_white, alpha = match.groups()
        if variants.startswith("dark:"):
            continue
        token = match.group(0)
        own_fill = True
        if (neutral and int(neutral_shade) <= 300) or (black_white == "white" and not alpha):
            problems.append(f"{token} is a neutral fill: use a theme token (bg-muted, bg-card, …)")
        elif hue and int(hue_shade) <= 300:
            light_hue = True
            if not re.search(rf"{_EDGE_L}dark:{re.escape(variants)}bg-", text):
                problems.append(f"{token} has no dark twin (dark:{variants}bg-{hue}-400/10)")
    if light_hue or not own_fill:
        for match in _TEXT.finditer(text):
            variants, shade = match.groups()
            if variants.startswith("dark:") or int(shade) < 500:
                continue
            if re.search(rf"{_EDGE_L}dark:{re.escape(variants)}text-", text):
                continue
            problems.append(
                f"{match.group(0)} sits on a light fill with no dark twin"
                if light_hue
                else f"{match.group(0)} is fixed whatever it sits on: a status token "
                "(text-success, text-warning, text-error, text-info) or its dark twin"
            )
    if not computed and _STYLE_BACKGROUND.search(text):
        problems.append("a style paints a fixed background: use classes")
    return problems


def _python_literals(path: Path) -> list[tuple[int, str, bool]]:
    """(line, text, is an f-string part) for every string constant in a module."""
    tree = ast.parse(path.read_text())
    in_fstring = {
        id(value)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for value in node.values
    }
    return [
        (node.lineno, node.value, id(node) in in_fstring)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _js_literals(path: Path) -> list[tuple[int, str, bool]]:
    return [
        (number, match.group(2), False)
        for number, line in enumerate(path.read_text().splitlines(), 1)
        for match in re.finditer(r"""(['"`])([^'"`]*)\1""", line)
    ]


def _all_literals() -> list[tuple[str, int, str, bool]]:
    found = [
        (str(path.relative_to(_APP_ROOT)), line, text, computed)
        for root in _PY_ROOTS
        for path in sorted((_APP_ROOT / root).rglob("*.py"))
        for line, text, computed in _python_literals(path)
    ]
    found += [
        (str(path.relative_to(_APP_ROOT)), line, text, computed)
        for path in sorted((_APP_ROOT / "static/js").rglob("*.js"))
        for line, text, computed in _js_literals(path)
    ]
    return found


_LITERALS = _all_literals()


def test_no_literal_paints_a_fill_that_ignores_the_theme() -> None:
    problems = [
        f"{path}:{line}: {problem}"
        for path, line, text, computed in _LITERALS
        for problem in literal_problems(text, computed=computed)
    ]
    assert problems == []


@pytest.mark.parametrize(
    ("path", "needle"),
    [
        # A class string: the Alert's error variant.
        ("ui/components/feedback.py", "bg-red-50 dark:bg-red-400/10"),
        # An f-string part: the inline form's success message, built in JS.
        ("ui/exercises/inline_form.py", "bg-green-50 dark:bg-green-400/10"),
        # An enum's badge classes.
        ("core/models/enums/entity_enums.py", "bg-blue-100 dark:bg-blue-400/10"),
        # A quoted string in static/js: the modal backdrop.
        ("static/js/skuel.js", "bg-black/50"),
        # An Alpine expression: a prerequisite's met / unmet colour.
        ("ui/explore/ps_detail.py", "'text-priority-low' : 'text-error'"),
        # An enum's status text.
        ("core/models/enums/entity_enums.py", "text-success"),
    ],
)
def test_the_walk_reads_each_kind_of_literal(path: str, needle: str) -> None:
    """The walk is not vacuous: it reaches a class string, an f-string part, an enum, a JS
    string and an Alpine expression, each holding a colour the guard judges."""
    assert any(p == path and needle in text for p, _, text, _ in _LITERALS)


@pytest.mark.parametrize(
    ("text", "computed", "refused"),
    [
        ("rounded border bg-slate-50 p-4", False, True),
        ("hover:bg-slate-100", False, True),
        ("bg-gray-100 text-gray-600", False, True),
        ("bg-white border-2 border-primary", False, True),
        ("bg-blue-50 text-blue-800", False, True),
        ("bg-blue-50 dark:bg-blue-400/10 text-blue-800", False, True),
        ("hover:bg-blue-50 dark:bg-blue-400/10", False, True),
        ("<div class=\\'p-4 bg-red-50 text-red-800\\'>", True, True),
        ("background:#f4f1fc; border:1px solid #e0d9f4;", False, True),
        ("background-color: white", False, True),
        ("bg-muted/50 border-muted", False, False),
        ("bg-blue-50 dark:bg-blue-400/10 text-blue-800 dark:text-blue-300", False, False),
        ("hover:bg-blue-50 dark:hover:bg-blue-400/10", False, False),
        ("bg-green-500", False, False),
        ("bg-gray-400", False, False),
        ("fixed inset-0 bg-black/50", False, False),
        ("rounded-full bg-white/20", False, False),
        ("text-blue-600", False, True),
        ("text-sm text-green-600 font-medium", False, True),
        ("hover:text-violet-700", False, True),
        ("bg-muted text-amber-600", False, True),
        ("text-sm text-destructive", False, True),
        ("hover:text-destructive/80", False, True),
        ("border border-destructive/40", False, True),
        ("bg-destructive/10 text-error", False, True),
        ("allCompleted ? 'text-priority-low' : 'text-destructive'", False, True),
        ("text-success", False, False),
        ("bg-error/10 border border-error/20", False, False),
        ("text-blue-600 dark:text-blue-400", False, False),
        ("hover:text-violet-700 dark:hover:text-violet-300", False, False),
        ("bg-destructive text-destructive-foreground hover:bg-destructive/90", False, False),
        ("bg-yellow-500 text-yellow-950", False, False),
        ("text-blue-100", False, False),
        ("background-color: hsl(", True, False),
        ("background: hsl(var(--muted))", False, False),
    ],
)
def test_the_judge_refuses_each_way_a_fill_ignores_the_theme(
    text: str, computed: bool, refused: bool
) -> None:
    """The control: each rule refuses its case, and each allowed shape passes."""
    assert bool(literal_problems(text, computed=computed)) is refused
