"""Pin the Alpine.js documentation to the live ``skuel.js`` component registry.

Why this exists
---------------
Commit ``327f26623`` (2026-03-28) deleted 12 Alpine components in one commit and
updated none of the documentation. The rot went unnoticed for over four months
because *nothing was looking*: the docs named components as prose, and no check
compared that prose to the registry. Worked examples in
``ALPINE_JS_ARCHITECTURE.md`` could not be copied — the components they mounted
did not exist.

The durable fix is an **allow-list derived from ground truth**, not a
hand-maintained list of dead names. ``scripts/health/stale_names.py`` is the
deny-list mechanism, and it has the failure mode that let this drift: somebody
must remember to add a name to it when they delete a component. Here the truth
is *derived*, so deleting a component from ``skuel.js`` breaks the build on its
own:

    skuel.js  --(_assert_registry_in_sync)-->  _REGISTRY_COMPONENTS  --> these docs

Deleting a component forces the smoke-test fixture to change, which changes the
set this module reads, which fails any doc still teaching the component.

What is checked
---------------
1. Every ``x-data="name(...)"`` in the three docs names a live component (or a
   documented teaching placeholder). This covers *usage* examples anywhere.
2. Every component named in the first column of a table inside an
   ``<!-- alpine-registry:begin -->`` region is live. Only the first column is
   read: the other columns hold state-field names (``expanded``, ``sortBy``),
   which are not components.
3. The two docs that *claim* to list the whole registry actually do — so a
   newly added component also fails the build until it is documented.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]

# scripts/ is not a package — the sibling import resolves at runtime via the
# sys.path insert below, but not for MyPy (same ignore as scripts/health/stale_names.py
# and tests/unit/scripts/test_stale_names.py).
sys.path.insert(0, str(APP_ROOT / "scripts"))

from smoke_test import (  # type: ignore[import-not-found]  # noqa: E402
    _REGISTRY_COMPONENTS,
    _assert_registry_in_sync,
)

SKUEL_JS = APP_ROOT / "static" / "js" / "skuel.js"

UI_DEVELOPMENT = APP_ROOT / "docs" / "user-guides" / "ui-development.md"
ALPINE_ARCHITECTURE = APP_ROOT / "docs" / "architecture" / "ALPINE_JS_ARCHITECTURE.md"
UI_BROWSER_SKILL = APP_ROOT / ".claude" / "skills" / "ui-browser" / "SKILL.md"

ALPINE_DOCS = (UI_DEVELOPMENT, ALPINE_ARCHITECTURE, UI_BROWSER_SKILL)

# Docs whose marked regions are advertised as the COMPLETE registry. Adding a
# component to skuel.js must add a row to each of these.
#
# ALPINE_JS_ARCHITECTURE.md is deliberately absent: it documents four components
# as teaching patterns and says so, rather than claiming to be a full index.
COMPLETE_REGISTRY_DOCS = (UI_DEVELOPMENT, UI_BROWSER_SKILL)

# Generic names in "how to add a component" examples. These are intentionally
# NOT registry components — they stand in for whatever the reader is writing.
# Keep this set tiny; a real component name never belongs here.
PLACEHOLDERS = frozenset({"componentName", "myComponent", "myWidget"})

REGION_BEGIN = "<!-- alpine-registry:begin -->"
REGION_END = "<!-- alpine-registry:end -->"

# x-data="name(...)", x_data="name(...)", "x-data": "name(...)".
# The value must START with an identifier, so inline object literals
# (x-data="{ open: false }") correctly do not match.
_X_DATA_RE = re.compile(r"""x[-_]data["']?\s*[:=]\s*["']\s*([A-Za-z_]\w*)""")

_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_LEADING_IDENT_RE = re.compile(r"^([A-Za-z_]\w*)")


def _registry() -> frozenset[str]:
    """The live component names, via the smoke test's mount list.

    ``_REGISTRY_COMPONENTS`` holds mount expressions ("collapsible(true)");
    take the leading identifier of each.
    """
    names = set()
    for expr in _REGISTRY_COMPONENTS:
        match = _LEADING_IDENT_RE.match(expr)
        assert match is not None, f"unparseable mount expression: {expr!r}"
        names.add(match.group(1))
    return frozenset(names)


def _iter_marked_regions(text: str) -> list[list[str]]:
    """Return the line-lists of each <!-- alpine-registry --> region."""
    regions: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if REGION_BEGIN in line:
            assert current is None, "nested alpine-registry:begin"
            current = []
        elif REGION_END in line:
            assert current is not None, "alpine-registry:end without begin"
            regions.append(current)
            current = None
        elif current is not None:
            current.append(line)
    assert current is None, "unclosed alpine-registry:begin"
    return regions


def _components_in_regions(text: str) -> set[str]:
    """Component names from the FIRST column of tables in marked regions.

    Later columns document state fields (`expanded`, `sortBy`, `filters`), which
    are not components — reading them would produce noise, not coverage.
    """
    found: set[str] = set()
    for region in _iter_marked_regions(text):
        for line in region:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            first_cell = stripped.split("|")[1]
            for span in _BACKTICK_RE.findall(first_cell):
                ident = _LEADING_IDENT_RE.match(span.strip())
                if ident is not None:
                    found.add(ident.group(1))
    return found


def test_smoke_fixture_matches_skuel_js() -> None:
    """The anchor itself must be honest before the docs are measured against it.

    Without this, a fixture that silently drifted from skuel.js would let every
    doc assertion below pass while documenting components that do not exist.
    """
    assert _assert_registry_in_sync() is None


def test_registry_is_non_empty_and_parses() -> None:
    """Positive control: guard against an empty allow-list passing everything.

    Every assertion in this module is of the form "doc name ∈ registry". If the
    registry parsed to the empty set the *docs* checks would fail loudly, but a
    registry that parsed to a huge junk set would make them all vacuous — so pin
    the count and a known member.
    """
    registry = _registry()
    assert len(registry) == len(_REGISTRY_COMPONENTS)
    assert "searchFilters" in registry
    # Cross-check against the raw source, independent of the smoke-test list.
    registered = set(re.findall(r"Alpine\.data\(\s*'([^']+)'", SKUEL_JS.read_text()))
    assert registry == registered


@pytest.mark.parametrize("doc", ALPINE_DOCS, ids=lambda p: p.name)
def test_x_data_examples_name_live_components(doc: Path) -> None:
    """Every x-data example mounts a component that exists.

    This is the check that would have caught `taskFilter()` — a component that
    never existed in any commit — and the `searchSidebar()` / `timelineViewer()`
    examples left behind by 327f26623.
    """
    registry = _registry()
    offenders = {
        name
        for name in _X_DATA_RE.findall(doc.read_text(encoding="utf-8"))
        if name not in registry and name not in PLACEHOLDERS
    }
    assert not offenders, (
        f"{doc.relative_to(APP_ROOT)} mounts component(s) not registered in "
        f"static/js/skuel.js: {sorted(offenders)}. Either the component was "
        f"deleted (update the example to a live one) or the name is a typo."
    )


@pytest.mark.parametrize("doc", ALPINE_DOCS, ids=lambda p: p.name)
def test_marked_registry_tables_list_only_live_components(doc: Path) -> None:
    """No registry table names a deleted component."""
    registry = _registry()
    documented = _components_in_regions(doc.read_text(encoding="utf-8"))
    stale = documented - registry
    assert not stale, (
        f"{doc.relative_to(APP_ROOT)} documents component(s) that "
        f"static/js/skuel.js no longer registers: {sorted(stale)}."
    )


@pytest.mark.parametrize("doc", COMPLETE_REGISTRY_DOCS, ids=lambda p: p.name)
def test_docs_claiming_completeness_are_complete(doc: Path) -> None:
    """A new component must be documented, not just an old one removed.

    Both of these docs tell the reader their tables are the whole registry. If
    that claim is allowed to decay, the next reader greps the doc, does not find
    the component they need, and writes a duplicate.
    """
    registry = _registry()
    documented = _components_in_regions(doc.read_text(encoding="utf-8"))
    missing = registry - documented
    assert not missing, (
        f"{doc.relative_to(APP_ROOT)} claims to list the complete registry but "
        f"omits: {sorted(missing)}. Add a row, or drop the completeness claim "
        f"and remove the doc from COMPLETE_REGISTRY_DOCS."
    )


@pytest.mark.parametrize("doc", COMPLETE_REGISTRY_DOCS, ids=lambda p: p.name)
def test_marked_regions_are_present(doc: Path) -> None:
    """Deleting the markers must not silently disable the checks above."""
    regions = _iter_marked_regions(doc.read_text(encoding="utf-8"))
    assert regions, (
        f"{doc.relative_to(APP_ROOT)} has no {REGION_BEGIN} region — the "
        f"registry tables are no longer machine-checked."
    )
