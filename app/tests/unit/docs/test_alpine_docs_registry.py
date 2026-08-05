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
1. Every named component reference in *any* first-party doc under ``docs/``,
   ``.claude/skills/`` or ``CLAUDE.md`` is live (or a documented teaching
   placeholder). **Three shapes**, because a doc can name a component without
   ever mounting it: ``x-data="name(...)"`` mounts (including the f-string form
   FastHTML docs favour), ``Alpine.data('name', …)`` definitions, and prose that
   *instructs* a mount. Mount-only checking left a copy-paste ``swipeHandler``
   recipe in ``patterns-reference.md`` green while the architecture doc said
   touch/swipe had no live successor. Both ``.md`` and ``.html`` — the Today
   design handoff is HTML and mounts ``x-data="today()"``. Tree-wide, because a
   stale example is equally broken wherever it sits — five docs outside the
   original three were teaching deleted or never-existing components.

   Each shape was added only after grepping the corpus for it. Enumerating the
   shapes already seen, instead of measuring which occur, produced four
   successive coverage gaps here (HTML files, recipes, f-string mounts, prose
   directives). The corpus is the specification.

   **Known limit:** free prose that names a component *without* mentioning
   ``x-data`` is not checked. Distinguishing component names from method names
   (``toggle()``, ``validate()``) in open prose has no reliable signal — the
   attempt produced 61/30/42 candidates per doc. Marked registry regions
   (check 2) exist to cover that case deliberately.
2. Every component named in the first column of a table inside an
   ``<!-- alpine-registry:begin -->`` region is live. Only the first column is
   read: later columns hold state-field names (``expanded``, ``sortBy``), which
   are not components.
3. The two docs that *claim* to list the whole shared registry match
   ``skuel.js`` **exactly** — both directions. Omissions fail, so a newly added
   shared component must be documented; and page-local names fail too, so those
   tables cannot quietly become mixed shared/page-local registries (check 2
   alone would allow it, since it measures against the 26-component union).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
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

# Roots scanned by the tree-wide component-reference check.
DOC_ROOTS = (APP_ROOT / "docs", APP_ROOT / ".claude" / "skills", APP_ROOT / "CLAUDE.md")

# Vendored upstream reference docs — not SKUEL's claims. See _all_doc_files().
VENDORED_DOCS = APP_ROOT / "docs" / "llms.txt"

# Generic names in "how to add a component" examples. These are intentionally
# NOT registry components — they stand in for whatever the reader is writing.
# Keep this set tiny; a real component name never belongs here.
PLACEHOLDERS = frozenset({"componentName", "myComponent", "myWidget"})

REGION_BEGIN = "<!-- alpine-registry:begin -->"
REGION_END = "<!-- alpine-registry:end -->"

# x-data="name(...)", x_data="name(...)", "x-data": "name(...)".
#
# The `[rRbBuUfF]{0,2}` allows a Python string prefix before the quote. FastHTML
# docs interpolate constructor args, so `**{"x-data": f"chartVis('{url}', 'bar')"}`
# is the COMMON first-party form — 8 sites across the chartjs and vis-network
# skills. Requiring a bare quote missed every one of them, so a rename of
# chartVis or relationshipGraph would have left those examples stale and green.
#
# The value must START with an identifier, so inline object literals
# (x-data="{ open: false }") correctly do not match.
_X_DATA_RE = re.compile(r"""x[-_]data["']?\s*[:=]\s*[rRbBuUfF]{0,2}["']\s*([A-Za-z_]\w*)""")

# One pattern, two inputs. Against JS it runs on comment-STRIPPED source (so a
# prose mention cannot register); against docs it runs on raw text (so a prose
# mention IS a finding). The safety difference lives in the input, not here.
#
# Deliberately NOT anchored to line-start: today.js registers mid-line via
# `if (window.Alpine) window.Alpine.data('today', …)`, and an anchor would
# silently drop a live component.
_ALPINE_DATA_RE = re.compile(r"""Alpine\.data\(\s*['"]([A-Za-z_]\w*)['"]""")
# Backticked `name(...)` call — used only on lines that also mention x-data.
_PROSE_CALL_RE = re.compile(r"`([a-z][A-Za-z0-9]*)\([^`]*\)`")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_LEADING_IDENT_RE = re.compile(r"^([A-Za-z_]\w*)")


def _strip_js_comments(source: str) -> str:
    """Drop ``/* … */`` blocks and whole-line ``//`` comments.

    Every page-local bundle carries a JSDoc header that *names* its component in
    prose — ``* Registers Alpine.data('today', factory)``. Matching raw source
    counts those as registrations, so deleting the executable call while leaving
    the comment would keep a dead component in the registry and let stale docs
    pass. That is the fail-OPEN direction, which is the one that matters for a
    guard.

    Every such header here is a ``/** … */`` JSDoc block, so block-stripping is
    what actually closes the hole. Line comments are stripped only when ``//``
    begins the line, so a ``https://`` inside a string can never truncate real
    code and produce a phantom *missing* registration.

    Known limit, stated rather than papered over: a **trailing** ``code(); //
    Alpine.data('x')`` would still be counted. The pattern cannot be anchored to
    line-start to fix that, because ``today.js`` registers mid-line via ``if
    (window.Alpine) window.Alpine.data('today', …)`` and an anchor would silently
    drop a live component — trading a contrived fail-open for a real one.
    ``test_comments_do_not_register_components`` pins the behaviour both ways.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_blocks, flags=re.MULTILINE)


def _registrars() -> dict[Path, frozenset[str]]:
    """Map each static/js bundle to the components it registers.

    Globbed, not hard-coded: a new page-local bundle is covered the day it lands.
    Comments are stripped first — see ``_strip_js_comments``.
    """
    found: dict[Path, frozenset[str]] = {}
    for js in sorted(JS_DIR.glob("*.js")):
        source = _strip_js_comments(js.read_text(encoding="utf-8"))
        names = frozenset(_ALPINE_DATA_RE.findall(source))
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
    """First-party docs that can carry an Alpine snippet.

    ``.html`` as well as ``.md``: ``docs/design-handoff/today/today.html`` is a
    copyable design handoff that mounts ``x-data="today()"``, and a Markdown-only
    glob left it unchecked while the module claimed to cover any doc under
    ``docs/``. Rename or delete ``today`` and that file would have gone stale
    silently.

    ``docs/llms.txt/`` is excluded: vendored upstream reference material
    (FastHTML, MonsterUI, DaisyUI, shad4fast). Their examples are not SKUEL's
    claims, and holding third-party docs to SKUEL's registry would be wrong as
    well as noisy.
    """
    files: list[Path] = []
    for root in DOC_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        for pattern in ("*.md", "*.html"):
            files.extend(
                path for path in sorted(root.rglob(pattern)) if VENDORED_DOCS not in path.parents
            )
    return files


def test_comments_do_not_register_components() -> None:
    """A prose mention must not keep a deleted component alive.

    The fail-OPEN direction is the one that matters: if the JSDoc header
    ``* Registers Alpine.data('today', factory)`` counted, then deleting the
    executable call while leaving the comment would keep ``today`` in the
    registry and let every stale doc pass. Both directions are pinned, so this
    cannot pass vacuously.
    """
    comment_only = """
    /**
     * Registers Alpine.data('ghostComponent', factory); pair with x-data.
     */
    // Alpine.data('alsoGhost', factory);
    """
    assert _ALPINE_DATA_RE.findall(_strip_js_comments(comment_only)) == []
    # Positive control: the same names in executable position ARE found, so the
    # assertion above is testing comment-stripping and not a broken regex.
    executable = (
        "Alpine.data('ghostComponent', f);\nif (window.Alpine) window.Alpine.data('alsoGhost', f);"
    )
    assert sorted(_ALPINE_DATA_RE.findall(_strip_js_comments(executable))) == [
        "alsoGhost",
        "ghostComponent",
    ]
    # And the real bundles still resolve to the full registry after stripping.
    assert len(_registry()) == 26


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
def test_docs_claiming_completeness_match_the_shared_registry_exactly(doc: Path) -> None:
    """These tables must equal skuel.js — no omissions, and no page-local entries.

    Both directions are needed, and the second is not symmetry for its own sake.
    ``test_marked_registry_tables_list_only_live_components`` measures against the
    26-component union, so a page-local name like ``today`` in a *shared* table
    passes it; checking only for omissions here would let these tables quietly
    become mixed shared/page-local registries while still advertising themselves
    as the complete shared set.
    """
    documented = _components_in_regions(doc.read_text(encoding="utf-8"))
    shared = _skuel_js_registry()

    missing = shared - documented
    assert not missing, (
        f"{doc.relative_to(APP_ROOT)} claims to list the complete shared registry "
        f"but omits: {sorted(missing)}. Add a row, or drop the completeness claim "
        f"and remove the doc from COMPLETE_REGISTRY_DOCS."
    )

    foreign = documented - shared
    assert not foreign, (
        f"{doc.relative_to(APP_ROOT)} lists {sorted(foreign)} in a table that "
        f"claims to be the complete SHARED registry, but those are not in "
        f"skuel.js. Page-local components belong in the prose note about their "
        f"own bundles, not in the shared table."
    )


@pytest.mark.parametrize("doc", COMPLETE_REGISTRY_DOCS, ids=lambda p: p.name)
def test_marked_regions_are_present(doc: Path) -> None:
    """Deleting the markers must not silently disable the checks above."""
    assert _iter_marked_regions(doc.read_text(encoding="utf-8")), (
        f"{doc.relative_to(APP_ROOT)} has no {REGION_BEGIN} region — the "
        f"registry tables are no longer machine-checked."
    )


def _names_in_prose_directives(text: str) -> list[str]:
    """Components named in prose that *instructs* an x-data mount.

    Catches ``3. `x-data` must call `relationshipGraph(uid, entityType, depth)` ``
    — an instruction to mount a component, written without ever mounting it, so
    neither of the other two shapes sees it.

    Narrow on purpose: only lines that mention ``x-data`` **and** backtick a
    ``name(...)`` call. Scanning every backticked call corpus-wide is what this
    module rejected early, because method names (``toggle()``, ``validate()``)
    are indistinguishable from component names in free prose — it produced
    61/30/42 candidates per doc. This rule was measured before being added: it
    matches exactly one line in the whole corpus, naming a live component, with
    zero false positives.
    """
    names: list[str] = []
    for line in text.splitlines():
        if "x-data" not in line and "x_data" not in line:
            continue
        if _X_DATA_RE.search(line):
            continue  # a real mount — the mount shape owns it
        names.extend(_PROSE_CALL_RE.findall(line))
    return names


@pytest.mark.parametrize(
    ("shape", "extract"),
    [
        ("x-data mount", _X_DATA_RE.findall),
        ("Alpine.data definition", _ALPINE_DATA_RE.findall),
        ("prose x-data directive", _names_in_prose_directives),
    ],
)
def test_no_doc_anywhere_names_a_dead_component(
    shape: str, extract: Callable[[str], list[str]]
) -> None:
    """Tree-wide, every shape: each component a doc names must be live.

    Deliberately not limited to the three Alpine-specific docs. Scoping it that
    way is what let `choiceOptions` and `focusTrapModal` (both deleted in
    327f26623) survive in docs/domains/ and docs/ui/, and let `exerciseForm` and
    `insightActionConfirmation` — names that never existed in any commit — sit in
    docs/patterns/ as copyable examples.

    All three shapes are needed, and each was added only after the corpus proved
    it occurs: a deleted component can be handed out as a copy-paste
    ``Alpine.data('swipeHandler', …)`` recipe that is never mounted, or named in
    an instruction to mount it. Enumerating the shapes I had already seen, rather
    than grepping for the shapes present, is what caused three successive
    coverage gaps here (HTML files, recipes, f-string mounts).
    """
    registry = _registry()
    offenders: dict[str, list[str]] = {}
    for doc in _all_doc_files():
        bad = {
            name
            for name in extract(doc.read_text(encoding="utf-8", errors="ignore"))
            if name not in registry and name not in PLACEHOLDERS
        }
        if bad:
            offenders[str(doc.relative_to(APP_ROOT))] = sorted(bad)
    assert not offenders, (
        f"docs name Alpine components ({shape}) that no static/js bundle "
        f"registers: {offenders}. Either the component was deleted (repoint the "
        f"example to a live one) or the name never existed (delete the example)."
    )
