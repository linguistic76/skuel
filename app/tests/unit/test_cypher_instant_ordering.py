"""No Cypher ordering or ``min``/``max`` of a raw instant in ``adapters/persistence`` (UTC arc, PR 6b).

An instant is stored as a string by some writers (the mapper's ``isoformat()``)
and as a native by others (Cypher ``datetime()``). Neo4j orders values of
different types by type before value — every string after every temporal, so
first under ``DESC`` — and ``max()`` of a string and a native is the string,
whatever its age. A string order of stamps is only a wall-clock order: it
misreads an offset and ranks a whole second after its own fractions. So every
``ORDER BY`` key, and every ``min(``/``max(`` argument, that reads an instant
property reads it through ``datetime(...)`` (ADR-089 §2, R5).

The check walks every module's AST and reads its string literals — f-strings
rebuilt with ``{…}`` for their placeholders, docstrings skipped — and in each
``ORDER BY`` clause and ``min(``/``max(`` call finds the property reads
(``alias.property``). A read of an instant property that no enclosing call
wraps in ``datetime(`` fails, as does a dynamic read (``alias.{field}``) outside
the reviewed allowlist: a dynamic sort key goes through
``comparable_property`` (the type rule, in one place).

What it does not see: a raw instant carried under an alias (``WITH n.created_at
AS at … ORDER BY at``), and comparisons (``<``, ``>=``). A comparison of a
property every writer stores as a native stays raw by design (the session,
token, retention and rate-limit windows; the SearchEvent window is indexed).
Both are left to a census by hand.

See: /docs/roadmap/utc-instants-arc.md § PR 6
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from core.models.choice.choice import Choice
from core.models.habit.habit import Habit
from core.models.report.activity_report import ActivityReport
from core.models.user.conversation import ConversationSession
from core.utils.timestamp_helpers import is_instant_field

APP_ROOT = Path(__file__).resolve().parents[2]
PERSISTENCE = APP_ROOT / "adapters" / "persistence"

# Instant properties whose names do not end in ``_at``, each a ``datetime`` on
# the model beside it (pinned by the type rule below).
MODEL_INSTANTS: tuple[tuple[str, type], ...] = (
    ("decision_deadline", Choice),
    ("period_start", ActivityReport),
    ("period_end", ActivityReport),
    ("data_cutoff", ActivityReport),
    ("last_completed", Habit),
    ("last_activity", ConversationSession),
)

# Edge stamps no model declares, whose writers stamp ``datetime()``:
# MASTERED.last_practiced, IN_PROGRESS.last_accessed.
EDGE_INSTANTS: frozenset[str] = frozenset({"last_practiced", "last_accessed"})

INSTANT_NAMES: frozenset[str] = frozenset(name for name, _ in MODEL_INSTANTS) | EDGE_INSTANTS

# Dynamic reads that never carry an instant. RelationshipSpec.order_by_property
# is developer-authored, and its two values are the integers ``order`` and
# ``sequence`` (docs/roadmap/field-name-guarding-in-cypher.md).
DYNAMIC_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        ("_relationship_ordered_mixin.py", "r.{order_by_property}"),
    }
)

_CLAUSE_END = re.compile(r"\b(LIMIT|SKIP|RETURN|WITH|UNION|MATCH|CALL|WHERE|UNWIND)\b")
_PROPERTY = re.compile(r"(?<![\w.$])([A-Za-z_]\w*)\.([A-Za-z_]\w*|\{[^}]*\})")
_AGGREGATE = re.compile(r"\b(?:min|max)\(")


def is_instant_name(name: str) -> bool:
    return name.endswith("_at") or name in INSTANT_NAMES


def _literal_text(node: ast.JoinedStr) -> str:
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            parts.append("{" + ast.unparse(value.value) + "}")
    return "".join(parts)


def _docstring_nodes(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def string_literals(source: str) -> list[tuple[int, str]]:
    """Every string literal in ``source`` that is not a docstring, with its first line."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    inside_fstring: set[int] = set()
    literals: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            inside_fstring.update(id(v) for v in node.values)
            literals.append((node.lineno, _literal_text(node)))
    literals.extend(
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and id(node) not in inside_fstring
    )
    return literals


def _enclosing_calls(text: str, index: int) -> list[str]:
    """The names of the calls whose parentheses enclose ``text[index]``, innermost first."""
    names: list[str] = []
    depth = 0
    for position in range(index - 1, -1, -1):
        char = text[position]
        if char == ")":
            depth += 1
        elif char == "(":
            if depth:
                depth -= 1
                continue
            name = re.search(r"([A-Za-z_]\w*)\s*$", text[:position])
            names.append(name.group(1) if name else "")
    return names


def _clause_spans(text: str) -> list[tuple[int, int]]:
    """The ``ORDER BY`` key lists and ``min(``/``max(`` argument spans in ``text``."""
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"ORDER BY\b", text):
        start = match.end()
        end_match = _CLAUSE_END.search(text, start)
        spans.append((start, end_match.start() if end_match else len(text)))
    for match in _AGGREGATE.finditer(text):
        depth, position = 1, match.end()
        while position < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[position], 0)
            position += 1
        spans.append((match.end(), position - 1))
    return spans


def raw_instant_reads(text: str) -> list[str]:
    """Each instant property read in an ordering or aggregate of ``text`` that no ``datetime(`` wraps."""
    found: list[str] = []
    for start, end in _clause_spans(text):
        for prop in _PROPERTY.finditer(text, start, end):
            name = prop.group(2)
            dynamic = name.startswith("{")
            if not dynamic and not is_instant_name(name):
                continue
            if "datetime" in _enclosing_calls(text, prop.start()):
                continue
            found.append(prop.group(0))
    return found


def violations() -> list[str]:
    hits: list[str] = []
    for path in sorted(PERSISTENCE.rglob("*.py")):
        for line, text in string_literals(path.read_text(encoding="utf-8")):
            for read in raw_instant_reads(text):
                if (path.name, read) in DYNAMIC_ALLOWED:
                    continue
                hits.append(f"{path.relative_to(APP_ROOT)}:{line}: {read}")
    return hits


@pytest.mark.parametrize(("name", "model"), MODEL_INSTANTS)
def test_each_named_instant_is_an_instant_field(name: str, model: type) -> None:
    assert is_instant_field(model, name)


@pytest.mark.parametrize(
    ("cypher", "expected"),
    [
        ("MATCH (n) RETURN n ORDER BY n.created_at DESC LIMIT 5", ["n.created_at"]),
        ("RETURN n ORDER BY datetime(n.created_at) DESC", []),
        ("ORDER BY datetime(coalesce(e.updated_at, e.created_at)) DESC", []),
        ("ORDER BY datetime(toString(n.{date_field})) DESC, n.uid", []),
        ("ORDER BY toString(e.created_at) DESC, e.uid", ["e.created_at"]),
        ("ORDER BY c.decision_deadline ASC, n.title", ["c.decision_deadline"]),
        ("ORDER BY n.due_date ASC, n.title", []),
        ("ORDER BY e.{sort_by} DESC", ["e.{sort_by}"]),
        ("WITH max(sub.created_at) AS last RETURN last", ["sub.created_at"]),
        ("WITH max(datetime(at)) AS last, min(r.sequence) AS s RETURN last", []),
        ("ORDER BY n.read ASC, datetime(n.created_at) DESC\nLIMIT $limit", []),
        ("ORDER BY n.created_at\n WITH n.updated_at AS u", ["n.created_at"]),
    ],
)
def test_the_scanner_reads_orderings_and_aggregates(cypher: str, expected: list[str]) -> None:
    assert raw_instant_reads(cypher) == expected


def test_the_scanner_reads_fstrings_and_skips_docstrings() -> None:
    source = (
        "def f(field):\n"
        '    """ORDER BY n.created_at is described here, not run."""\n'
        '    return f"MATCH (n) RETURN n ORDER BY n.{field} DESC"\n'
    )
    assert [raw_instant_reads(text) for _, text in string_literals(source)] == [["n.{field}"]]


def test_no_raw_instant_ordering_in_persistence() -> None:
    assert violations() == []


# ----------------------------------------------------------------------------
# The rule in one place: comparable_property, and the filter operators it feeds
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "model", "expected"),
    [
        ("created_at", Choice, "datetime(n.created_at)"),
        ("decision_deadline", Choice, "datetime(n.decision_deadline)"),
        ("title", Choice, "n.title"),
        ("created_at", None, "n.created_at"),
        ("not_a_field", Choice, "n.not_a_field"),
    ],
)
def test_comparable_property_reads_an_instant_through_datetime(
    field: str, model: type | None, expected: str
) -> None:
    from adapters.persistence.neo4j.query.cypher import comparable_property

    assert comparable_property("n", field, model) == expected


def test_a_calendar_field_keeps_its_raw_order() -> None:
    from adapters.persistence.neo4j.query.cypher import comparable_property
    from core.models.task.task import Task

    assert comparable_property("n", "due_date", Task) == "n.due_date"


def test_filter_ranges_compare_instants_on_both_sides_and_days_as_stored() -> None:
    from datetime import UTC, date, datetime

    from adapters.persistence.neo4j.query.cypher import build_search_query
    from core.models.task.task import Task

    query, params = build_search_query(
        Task,
        {
            "created_at__gte": datetime(2026, 9, 1, tzinfo=UTC),
            "created_at__lt": datetime(2026, 10, 1, tzinfo=UTC),
            "due_date__lte": date(2026, 9, 30),
        },
    )

    assert "datetime(n.created_at) >= datetime($created_at_gte)" in query
    assert "datetime(n.created_at) < datetime($created_at_lt)" in query
    assert "n.due_date <= $due_date_lte" in query
    assert params["created_at_gte"] == "2026-09-01T00:00:00+00:00"
