"""Pin every documented ContentOrigin tier table to the live mapping.

Why this exists
---------------
``EntityType.__doc__`` carried a hand-transcribed copy of ``_CONTENT_ORIGIN_BY_TYPE``
from the same file and had drifted on two members: ``FORM_TEMPLATE`` appeared in no
tier at all, and ``REVISED_EXERCISE`` was filed under ``CURRICULUM`` when the mapping
says ``USER_CREATED``. That copy is deleted. Two prose enumerations are deliberately
kept — ``CLAUDE.md`` and ``ENUM_ARCHITECTURE.md`` — because a complete tier table is
genuinely useful at those two altitudes, and one of them was wrong the same way
(``THREE_LAYER_LENS.md`` asserted the inverse of the code in prose).

Keeping a hand-maintained list without a check is the bet that already failed three
times. So the truth here is *derived* — moving a type between tiers breaks the build
until every table is updated.

The corpus is discovered, not enumerated
----------------------------------------
A hard-coded list of "the two docs with tier tables" has the failure mode it is meant
to prevent: somebody adds a third table and nothing looks at it. So this module globs
first-party docs and picks up any table whose header names a ``ContentOrigin`` column
and an ``EntityTypes`` column. A new table is covered on arrival.

The ``EntityTypes`` column is located **by header name, not by position** — the two
tables today have four and three columns respectively, and reading "the third cell"
would silently compare the wrong column in a table shaped differently tomorrow.

Known limit
-----------
Only tables are checked. Prose that names a tier membership in a sentence
("``RevisedExercise`` has ``ContentOrigin.CURRICULUM``" — the real defect in
``THREE_LAYER_LENS.md``) has no reliable structural signal, and the fix applied there
was to stop restating membership and point at ``content_origin()`` instead. Prefer a
pointer in prose; use a table only when the enumeration is complete.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.models.enums.entity_enums import ContentOrigin, EntityType

APP_ROOT = Path(__file__).resolve().parents[3]

# Group phrases the tables use instead of naming six members twice over. Each maps to
# a set derived from the enum, and the count written in the doc is asserted against it
# below — a phrase that has silently changed size fails loudly instead of resolving to
# a stale membership.
GROUP_PHRASES = {
    r"\b(?:all |the )?(\d+) Activity Templates\b": frozenset(
        m for m in EntityType if m.is_activity_template()
    ),
    r"\b(?:all |the )?(\d+) Activit(?:ies|y types)\b": frozenset(
        m for m in EntityType if m.is_activity()
    ),
}

# Doc spellings → members. Docs write display CamelCase (``FormTemplate``); the enum
# writes UPPER_SNAKE. Both are accepted so a table may use either.
SPELLINGS: dict[str, EntityType] = {}
for _m in EntityType:
    SPELLINGS[_m.name] = _m
    SPELLINGS[_m.name.title().replace("_", "")] = _m


def _doc_files() -> list[Path]:
    files = [APP_ROOT / "CLAUDE.md", *sorted((APP_ROOT / "docs").rglob("*.md"))]
    files += sorted((APP_ROOT / ".claude" / "skills").rglob("*.md"))
    return [f for f in files if f.is_file()]


def _tier_tables() -> list[tuple[Path, dict[ContentOrigin, str]]]:
    """Every markdown table that enumerates tier membership, as {origin: cell}."""
    found: list[tuple[Path, dict[ContentOrigin, str]]] = []
    for path in _doc_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "|" not in line:
                continue
            headers = [c.strip().strip("`*") for c in line.strip().strip("|").split("|")]
            lowered = [h.lower() for h in headers]
            if "contentorigin" not in lowered or "entitytypes" not in lowered:
                continue
            origin_col = lowered.index("contentorigin")
            types_col = lowered.index("entitytypes")
            rows: dict[ContentOrigin, str] = {}
            for row in lines[i + 2 :]:  # skip the |---| separator
                if not row.strip().startswith("|"):
                    break
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                if len(cells) <= max(origin_col, types_col):
                    continue
                name = cells[origin_col].strip("`*")
                if name in ContentOrigin.__members__:
                    rows[ContentOrigin[name]] = cells[types_col]
            if rows:
                found.append((path, rows))
    return found


def _members_named_in(cell: str) -> set[EntityType]:
    named = {SPELLINGS[t] for t in re.findall(r"\b[A-Za-z][A-Za-z_]+\b", cell) if t in SPELLINGS}
    for pattern, group in GROUP_PHRASES.items():
        if match := re.search(pattern, cell):
            claimed = int(match.group(1))
            assert claimed == len(group), (
                f"the phrase {match.group(0)!r} claims {claimed} members but the group "
                f"derived from EntityType has {len(group)}"
            )
            named |= group
    return named


def test_tier_tables_are_discovered() -> None:
    """Guard the guard: a discovery bug would make every check below vacuous."""
    tables = _tier_tables()
    names = {p.relative_to(APP_ROOT).as_posix() for p, _ in tables}
    assert names >= {"CLAUDE.md", "docs/architecture/ENUM_ARCHITECTURE.md"}, (
        f"expected the two known tier tables to be discovered, found {sorted(names)}"
    )
    for path, rows in tables:
        assert set(rows) == set(ContentOrigin), (
            f"{path.relative_to(APP_ROOT)} names only {sorted(o.name for o in rows)} — a tier "
            "table must cover all four tiers or it cannot be checked for completeness"
        )


@pytest.mark.parametrize(
    ("path", "rows"),
    _tier_tables(),
    ids=lambda v: v.relative_to(APP_ROOT).as_posix() if isinstance(v, Path) else "",
)
def test_tier_table_matches_mapping(path: Path, rows: dict[ContentOrigin, str]) -> None:
    """Each documented tier must equal what content_origin() actually returns."""
    where = path.relative_to(APP_ROOT)
    for origin, cell in rows.items():
        documented = _members_named_in(cell)
        # Ground truth via the method, not the dict: a member missing from
        # _CONTENT_ORIGIN_BY_TYPE raises here rather than silently leaving a tier.
        actual = {m for m in EntityType if m.content_origin() is origin}
        missing = sorted(m.name for m in actual - documented)
        wrong = sorted(f"{m.name} (really {m.content_origin().name})" for m in documented - actual)
        assert not missing and not wrong, (
            f"{where} § tier {origin.name} disagrees with content_origin() — "
            f"missing: {missing or 'none'}; wrongly listed: {wrong or 'none'}"
        )


def test_every_member_is_covered_by_each_table() -> None:
    """A table may not quietly omit a member from all four of its rows."""
    for path, rows in _tier_tables():
        covered: set[EntityType] = set()
        for cell in rows.values():
            covered |= _members_named_in(cell)
        absent = sorted(m.name for m in set(EntityType) - covered)
        assert not absent, (
            f"{path.relative_to(APP_ROOT)} names no tier for: {absent} — this is exactly how "
            "FORM_TEMPLATE went missing from the EntityType docstring"
        )
