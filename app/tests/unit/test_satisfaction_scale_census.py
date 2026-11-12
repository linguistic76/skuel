"""The satisfaction scale's numbers are written once, in ``SatisfactionScale``.

A learner rates how a decided choice turned out on ``SatisfactionScale``
(``core/constants.py``). Every reader that divides by the top of the scale, compares
against one of its levels, or prints ``/5`` beside a rating names the constant, so
the scale has one definition. The census fails on a number written next to a
satisfaction reader anywhere else.

**Detection is by shape, over the first-party trees** (``core/``, ``adapters/``,
``ui/``, ``services_bootstrap/``), ``core/constants.py`` excepted. "Next to a
satisfaction reader" means an expression holding a name, attribute or string that
contains ``satisf``:

- a division (``/``, ``//``) of such an expression by a number;
- a comparison with such an expression on one side and a number on another;
- an f-string that formats such an expression and has ``/`` and a digit in its text;
- a string (a Cypher fragment) where ``satisf…`` is followed by a comparison or a
  division and a digit.

The page bundles (``static/js/``) and the prompt templates
(``core/prompts/templates/``) are read with the string rule. ``_CONTROL`` plants
each shape once and the detector must find every one; the floor on readers seen
keeps a walker that reads nothing from passing.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime
from pathlib import Path

import pytest
from fasthtml.common import to_xml

from core.constants import SatisfactionScale
from core.models.choice.choice import Choice
from core.models.enums.entity_enums import EntityStatus
from ui.activities.choices_views import ChoiceStatsBar

APP = Path(__file__).resolve().parents[2]
PY_TREES = ("core", "adapters", "ui", "services_bootstrap")
TEXT_GLOBS = (("static/js", "*.js"), ("core/prompts/templates", "*.md"))
SCALE_HOME = APP / "core" / "constants.py"

_WORD = "satisf"
_STRING_RULE = re.compile(r"satisf\w*[^\n]{0,30}?(?:>=|<=|>|<|==|/)\s*\d")
_SLASH_DIGIT = re.compile(r"/\s*\d")


def _is_number(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    )


def _mentions_satisfaction(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and _WORD in sub.id.lower():
            return True
        if isinstance(sub, ast.Attribute) and _WORD in sub.attr.lower():
            return True
        if (
            isinstance(sub, ast.Constant)
            and isinstance(sub.value, str)
            and _WORD in sub.value.lower()
        ):
            return True
    return False


def scale_literals(source: str) -> list[tuple[int, str]]:
    """Every (line, shape) where a number sits beside a satisfaction reader."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div | ast.FloorDiv):
            if _is_number(node.right) and _mentions_satisfaction(node.left):
                found.append((node.lineno, "division"))
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            if any(_is_number(o) for o in operands) and any(
                _mentions_satisfaction(o) for o in operands if not _is_number(o)
            ):
                found.append((node.lineno, "comparison"))
        elif isinstance(node, ast.JoinedStr):
            text = "".join(
                v.value
                for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
            formats_rating = any(
                isinstance(v, ast.FormattedValue) and _mentions_satisfaction(v.value)
                for v in node.values
            )
            if formats_rating and _SLASH_DIGIT.search(text):
                found.append((node.lineno, "f-string"))
            elif _STRING_RULE.search(text.lower()):
                found.append((node.lineno, "string"))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _STRING_RULE.search(node.value.lower())
        ):
            found.append((node.lineno, "string"))
    return found


def _python_files() -> list[Path]:
    return [
        path
        for tree in PY_TREES
        for path in sorted((APP / tree).rglob("*.py"))
        if path != SCALE_HOME and "__pycache__" not in path.parts
    ]


def _text_files() -> list[Path]:
    return [path for folder, glob in TEXT_GLOBS for path in sorted((APP / folder).rglob(glob))]


# One plant per shape the census claims to catch, each on its own line.
_CONTROL = """
def plants(choice, scores, avg_satisfaction):
    a = choice.satisfaction_score / 5.0
    b = sum((c.satisfaction_score or 0) / 5 for c in scores)
    c = choice.satisfaction_score >= 4
    d = 3.5 <= avg_satisfaction
    e = f"Satisfaction: {choice.satisfaction_score}/5"
    f = "WHERE c.satisfaction_score >= 4"
    g = f"WHERE {node}.satisfaction_score > 3"
"""
_CONTROL_HITS = {
    (3, "division"),
    (4, "division"),
    (5, "comparison"),
    (6, "comparison"),
    (7, "f-string"),
    (8, "string"),
    (9, "string"),
}

# What the census must leave alone: the constant named, a weight beside a rescaled
# rating, a count compared with zero, an unrelated number.
_CLEAN = """
def clean(choice, ratings, outcomes):
    a = choice.satisfaction_score / SatisfactionScale.HIGHEST
    b = 0.2 * a
    c = outcomes.choices_rated == 0
    d = f"{choice.satisfaction_score}/{SatisfactionScale.HIGHEST}"
    e = f"WHERE c.satisfaction_score >= {SatisfactionScale.GOOD}"
    f = choice.priority >= 4
"""


def test_the_detector_finds_every_planted_shape() -> None:
    assert set(scale_literals(_CONTROL)) == _CONTROL_HITS


def test_the_detector_leaves_named_constants_alone() -> None:
    assert scale_literals(_CLEAN) == []


def test_the_string_rule_reads_a_page_bundle_line() -> None:
    assert _STRING_RULE.search("if (choice.satisfaction_score >= 4) {")
    assert _STRING_RULE.search("`${c.satisfaction_score}/5`")
    assert not _STRING_RULE.search("`${c.satisfaction_score}/${scale.highest}`")


def test_the_walk_reaches_the_satisfaction_readers() -> None:
    """The floor: the walk sees the readers it guards, so an empty scan cannot pass."""
    readers = [path for path in _python_files() if _WORD in path.read_text().lower()]
    names = {path.name for path in readers}
    assert {"choice.py", "choices_views.py", "_behavioral_signals_mixin.py"} <= names
    assert len(readers) >= 15


def test_no_scale_number_beside_a_satisfaction_reader() -> None:
    hits = [
        f"{path.relative_to(APP)}:{line} ({shape})"
        for path in _python_files()
        for line, shape in scale_literals(path.read_text())
    ]
    hits += [
        f"{path.relative_to(APP)}:{number} (string)"
        for path in _text_files()
        for number, text in enumerate(path.read_text().splitlines(), start=1)
        if _STRING_RULE.search(text.lower())
    ]
    assert hits == [], "Name the SatisfactionScale constant instead:\n" + "\n".join(hits)


# ---------------------------------------------------------------------------
# SATISFYING_MEAN, held to the real stats bar
# ---------------------------------------------------------------------------


def _rated(uid: str, rating: int) -> Choice:
    return Choice(
        uid=uid,
        title=uid,
        user_uid="user_v",
        status=EntityStatus.COMPLETED,
        decided_at=datetime(2026, 9, 1, 12, 0),
        satisfaction_score=rating,
    )


_AVERAGE_TILE = re.compile(
    r'Avg Satisfaction</span>\s*<div class="mt-1">\s*<span class="([^"]+)">([^<]*)</span>'
)


def _average_tile(choices: list[Choice]) -> tuple[str, str]:
    """The average tile's value classes and text."""
    match = _AVERAGE_TILE.search(to_xml(ChoiceStatsBar(choices)))
    assert match is not None
    return match.group(1), match.group(2)


@pytest.mark.parametrize(
    ("ratings", "shown", "primary"),
    [
        ([4, 3], "3.5/5", True),  # exactly SATISFYING_MEAN
        ([5, 4, 1], "3.3/5", False),  # just under
        ([5], "5.0/5", True),
        ([1, 2], "1.5/5", False),
    ],
)
def test_the_average_tile_turns_primary_at_the_satisfying_mean(
    ratings: list[int], shown: str, primary: bool
) -> None:
    assert SatisfactionScale.SATISFYING_MEAN == 3.5
    classes, text = _average_tile([_rated(f"choice_{i}", r) for i, r in enumerate(ratings)])
    assert text == shown
    assert ("text-primary" in classes.split()) is primary


def test_the_average_tile_reads_dash_with_nothing_rated() -> None:
    unrated = Choice(uid="choice_u", title="u", user_uid="user_v", status=EntityStatus.ACTIVE)
    classes, text = _average_tile([unrated])
    assert text == "-"
    assert "text-primary" not in classes.split()
