"""
MEGA-QUERY sub-collections must never collect an all-null placeholder map
========================================================================

**The trap, measured on the live engine (2026-08-28):**

===========================================  ==========================
``collect(x)`` over a null                   ``[]``     ✅
``collect(x.uid)`` over a null               ``[]``     ✅
``collect(CASE WHEN x IS NOT NULL …)``       ``[]``     ✅
``collect({uid: x.uid, …})`` over a null     ``[{uid: null, …}]``  ❌
===========================================  ==========================

Cypher's ``collect()`` drops null *values* — but a **map literal is never
null**, only its fields are. So the map-literal form is the one shape that
turns "no neighbours" into a one-element list, and every consumer that counts
it reads 1 where the truth is 0.

That is not hypothetical. Before this guard, ``user_context_populator``
computed ``principle_guided_choice_counts`` as ``len(guided_choices)`` on the
raw projection, and the live graph — which has **no** ``GUIDES_CHOICE`` edges
at all — reported **1 guided choice for each of its 2 principles**. Two lines
below, the same block's *iteration* was null-guarded
(``if choice and choice.get("uid")``): a correct loop and an incorrect count,
touching the same list.

#1171 fixed one instance (``lp_steps``) and ruled the ~30 siblings could wait
because "nothing derives a COUNT from them". This module exists because that
premise had already stopped being true — so it asserts the **rule** rather than
re-checking the consumers: a 39th sub-collection added tomorrow inherits the
guard, and no future audit has to re-derive which consumers count.

**Scope — deliberately this file only.** The same map-literal shape appears at
**54 further sites across 21 other adapter modules** (measured 2026-08-28).
Those are NOT covered here and NOT swept: each needs its own guard-variable
check and its own consumer audit, and most feed iterating consumers where the
placeholder is filtered rather than counted. This guard therefore proves the
MEGA-QUERY file is clean and proves nothing about the rest — do not read a
green run as "the codebase has no phantoms". Widening the sweep is a separate,
larger piece of work.

See: ADR-085 §4 (the anchored-projection sibling), PR #1171,
`docs/architecture/UNIFIED_USER_ARCHITECTURE.md` § entities_rich.
"""

from __future__ import annotations

import re
from pathlib import Path

import adapters.persistence.neo4j.user_context_queries as user_context_queries

QUERY_SOURCE = Path(user_context_queries.__file__)

# A map literal opening a collect(): `collect({` or `collect(DISTINCT {`.
# Both spellings trap identically — the first pass of the sweep matched only
# the DISTINCT one and missed seven sites, which is why this pattern covers
# the CLASS (a map literal) rather than a spelling.
BARE_MAP_COLLECT = re.compile(r"collect\(\s*(?:DISTINCT\s+)?\{")


def _cypher_only(source: str) -> str:
    """The file's Cypher, with Python comments/docstrings left in place.

    Deliberately NOT parsed: a `collect({` inside a docstring is still a
    template someone will copy, so the guard should object to it too.
    """
    return source


def test_no_sub_collection_collects_a_bare_map_literal() -> None:
    """Every map-collecting sub-collection is null-guarded.

    The fix shape, applied uniformly:

        collect(DISTINCT CASE WHEN x IS NOT NULL THEN {uid: x.uid, …} END)

    An empty OPTIONAL MATCH then collects nothing and the list is ``[]``.
    """
    source = _cypher_only(QUERY_SOURCE.read_text())
    offenders = []
    for match in BARE_MAP_COLLECT.finditer(source):
        line_no = source.count("\n", 0, match.start()) + 1
        line = source.splitlines()[line_no - 1].strip()
        offenders.append(f"  {QUERY_SOURCE.name}:{line_no}: {line[:100]}")

    assert offenders == [], (
        "a sub-collection collects a bare map literal, so an entity with no "
        "neighbours yields [{uid: null, …}] instead of [] — any consumer that "
        "counts it reads 1 where the truth is 0. Wrap the map:\n"
        "  collect(DISTINCT CASE WHEN <node> IS NOT NULL THEN {…} END)\n" + "\n".join(offenders)
    )


def test_the_guard_can_actually_fail() -> None:
    """The pattern matches the shape it claims to — not a regex that never fires.

    Without this, `test_no_sub_collection_collects_a_bare_map_literal` would
    pass just as happily against a typo'd pattern that matches nothing.
    """
    assert BARE_MAP_COLLECT.search("collect({uid: x.uid, title: x.title})")
    assert BARE_MAP_COLLECT.search("collect(DISTINCT {uid: x.uid})")
    assert BARE_MAP_COLLECT.search("collect(\n    DISTINCT {uid: x.uid})".replace("\n    ", " "))
    # …and does NOT fire on the guarded form or the null-dropping forms.
    assert not BARE_MAP_COLLECT.search(
        "collect(DISTINCT CASE WHEN x IS NOT NULL THEN {uid: x.uid} END)"
    )
    assert not BARE_MAP_COLLECT.search("collect(x)")
    assert not BARE_MAP_COLLECT.search("collect(x.uid)")
    assert not BARE_MAP_COLLECT.search("collect(CASE WHEN x.status = $s THEN x.uid END)")


def test_the_guarded_form_is_actually_present() -> None:
    """Positive control: the file uses the guarded shape, many times over.

    A file that stopped collecting maps altogether would pass the first test
    vacuously; this pins that the sweep converted them rather than deleted them.
    """
    guarded = len(re.findall(r"collect\(\s*(?:DISTINCT\s+)?CASE WHEN", QUERY_SOURCE.read_text()))
    assert guarded >= 38, (
        f"expected the swept sub-collections to still be present and guarded, found {guarded}"
    )
