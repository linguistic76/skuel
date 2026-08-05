"""Pin the Alpine.js documentation to the live component registry.

Why this exists
---------------
Commit ``327f26623`` (2026-03-28) deleted 12 Alpine components in one commit and
updated none of the documentation. The rot went unnoticed for over four months
because *nothing was looking*: the docs named components as prose, and no check
compared that prose to the registry. Worked examples could not be copied — the
components they mounted did not exist.

The durable fix is an **allow-list derived from ground truth**, not a
hand-maintained list of dead names. ``scripts/health/stale_names.py`` is the
deny-list mechanism, and it has the failure mode that let this drift: somebody
must remember to add a name to it when they delete a component. Here the truth
is *derived*, so deleting a component breaks the build on its own.

``skuel.js`` is not the whole registry
--------------------------------------
The obvious assumption — "all Alpine components live in ``static/js/skuel.js``" —
is **false**, and asserting it is how the first version of this module shipped a
wrong ground truth. Five files under ``static/js/`` call ``Alpine.data()``:
``skuel.js`` holds the 22 shared components, and four page-local bundles
(``today.js``, ``explore-reading.js``, ``ku-reading.js``, ``ps-detail.js``) each
register one more, loaded by their own routes. A guard built on ``skuel.js``
alone reports a live component as dead — ``today`` is documented correctly in
``docs/design-handoff/today/today.md`` and would have been flagged.

So the registry here is the **union across every registrar**, discovered by
globbing rather than by a hard-coded file list, and a new bundle is picked up
automatically.

What is checked
---------------
1. Every ``x-data="name(...)"`` in *any* doc under ``docs/``, ``.claude/skills/``
   or ``CLAUDE.md`` names a live component (or a documented teaching
   placeholder). Tree-wide, because a stale mount is equally broken wherever it
   sits — four docs outside the original three were teaching deleted or
   never-existing components.
2. Every component named in the first column of a table inside an
   ``<!-- alpine-registry:begin -->`` region is live. Only the first column is
   read: later columns hold state-field names (``expanded``, ``sortBy``), which
   are not components.
3. The two docs that *claim* to list the whole shared registry actually list
   exactly ``skuel.js``'s components — so a newly added shared component also
   fails the build until it is documented.
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

JS_DIR = APP_ROOT / "static" / "js"
SKUEL_JS = JS_DIR / "skuel.js"

UI_DEVELOPMENT = APP_ROOT / "docs" / "user-guides" / "ui-development.md"
ALPINE_ARCHITECTURE = APP_ROOT / "docs" / "architecture" / "ALPINE_JS_ARCHITECTURE.md"
UI_BROWSER_SKILL = APP_ROOT / ".claude" / "skills" / "ui-browser" / "SKILL.md"

ALPINE_DOCS = (UI_DEVELOPMENT, ALPINE_ARCHITECTURE, UI_BROWSER_SKILL)

# Docs whose marked regions are advertised as the complete SHARED registry
# (skuel.js). Adding a component to skuel.js must add a row to each of these.
#
# ALPINE_JS_ARCHITECTURE.md is deliberately absent: it documents four components
# as teaching patterns and says so, rather than claiming to be a full index.
COMPLETE_REGISTRY_DOCS = (UI_DEVELOPMENT, UI_BROWSER_SKILL)

# Roots scanned by the tree-wide x-data check.
DOC_ROOTS = (APP_ROOT / "docs", APP_ROOT / ".claude" / "skills", APP_ROOT / "CLAUDE.md")

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

_ALPINE_DATA_RE = re.compile(r"Alpine\.data\(\s*'([^']+)'")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_LEADING_IDENT_RE = re.compile(r"^([A-Za-z_]\w*)")


def _registrars() -> dict[Path, frozenset[str]]:
    """Map each static/js bundle to the components it registers.

    Globbed, not hard-coded: a new page-local bundle is covered the day it lands.
    """
    found: dict[Path, frozenset[str]] = {}
    for js in sorted(JS_DIR.glob("*.js")):
        names = frozenset(_ALPINE_DATA_RE.findall(js.read_text(encoding="utf-8")))
        if names:
            found[js] = names
    return found


def _registry() -> frozenset[str]:
    """Every live component name, across every registrar."""
    return frozenset().union(*_registrars().values())


def _skuel_js_registry() -> frozenset[str]:
    """The shared registry only — what the doc tables enumerate."""
    return _registrars()[SKUEL_JS]


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


def _all_doc_files() -> list[Path]:
    files: list[Path] = []
    for root in DOC_ROOTS:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    return files


def test_smoke_fixture_matches_skuel_js() -> None:
    """The anchor itself must be honest before the docs are measured against it."""
    assert _assert_registry_in_sync() is None


def test_registry_spans_every_registrar_not_just_skuel_js() -> None:
    """Positive control on the ground truth itself.

    The first version of this module derived truth from skuel.js alone and was
    wrong: four page-local bundles register components too. Pin that the union is
    strictly larger than skuel.js, so a regression back to the narrow reading
    fails loudly instead of silently reporting live components as dead.
    """
    registrars = _registrars()
    assert SKUEL_JS in registrars, "skuel.js registers no components — parse broke"
    assert len(registrars) > 1, (
        "expected page-local Alpine bundles beside skuel.js; if they were "
        "genuinely consolidated, simplify this module rather than weakening it"
    )
    assert _registry() > _skuel_js_registry()
    # The smoke fixture covers the shared bundle specifically.
    assert _skuel_js_registry() == {
        m.group(0) for e in _REGISTRY_COMPONENTS if (m := _LEADING_IDENT_RE.match(e))
    }


@pytest.mark.parametrize("doc", ALPINE_DOCS, ids=lambda p: p.name)
def test_marked_registry_tables_list_only_live_components(doc: Path) -> None:
    """No registry table names a deleted component."""
    stale = _components_in_regions(doc.read_text(encoding="utf-8")) - _registry()
    assert not stale, (
        f"{doc.relative_to(APP_ROOT)} documents component(s) no static/js bundle "
        f"registers: {sorted(stale)}."
    )


@pytest.mark.parametrize("doc", COMPLETE_REGISTRY_DOCS, ids=lambda p: p.name)
def test_docs_claiming_completeness_are_complete(doc: Path) -> None:
    """A new shared component must be documented, not just an old one removed."""
    missing = _skuel_js_registry() - _components_in_regions(doc.read_text(encoding="utf-8"))
    assert not missing, (
        f"{doc.relative_to(APP_ROOT)} claims to list the complete shared registry "
        f"but omits: {sorted(missing)}. Add a row, or drop the completeness claim "
        f"and remove the doc from COMPLETE_REGISTRY_DOCS."
    )


@pytest.mark.parametrize("doc", COMPLETE_REGISTRY_DOCS, ids=lambda p: p.name)
def test_marked_regions_are_present(doc: Path) -> None:
    """Deleting the markers must not silently disable the checks above."""
    assert _iter_marked_regions(doc.read_text(encoding="utf-8")), (
        f"{doc.relative_to(APP_ROOT)} has no {REGION_BEGIN} region — the "
        f"registry tables are no longer machine-checked."
    )


def test_no_doc_anywhere_mounts_a_dead_component() -> None:
    """Tree-wide: every x-data mount in every doc names a live component.

    Deliberately not limited to the three Alpine-specific docs. Scoping it that
    way is what let `choiceOptions` and `focusTrapModal` (both deleted in
    327f26623) survive in docs/domains/ and docs/ui/, and let `exerciseForm` and
    `insightActionConfirmation` — names that never existed in any commit — sit in
    docs/patterns/ as copyable examples.
    """
    registry = _registry()
    offenders: dict[str, list[str]] = {}
    for doc in _all_doc_files():
        bad = {
            name
            for name in _X_DATA_RE.findall(doc.read_text(encoding="utf-8", errors="ignore"))
            if name not in registry and name not in PLACEHOLDERS
        }
        if bad:
            offenders[str(doc.relative_to(APP_ROOT))] = sorted(bad)
    assert not offenders, (
        "docs mount Alpine components that no static/js bundle registers: "
        f"{offenders}. Either the component was deleted (repoint the example to a "
        f"live one) or the name never existed (delete the example)."
    )
