#!/usr/bin/env python3
"""
Generate the Search Service Method Reference — docs/reference/SEARCH_SERVICE_METHODS.md
=====================================================================================

The method surface of the nine domain search services, read from the live
classes so it cannot list a method a class lacks or a signature it does not
have:

- a matrix of every search-surface method across the nine services, marking
  for each service whether it inherits the method, overrides it, defines it
  alone, or lacks it — attribution by the first class defining the name on
  the service's MRO
- the inherited methods of the three ``BaseService`` mixins a search service
  exposes (``SEARCH_MIXINS``), each with its real signature and the first
  line of its docstring
- per service: its ``DomainConfig`` search settings and the methods it
  overrides or defines, with signatures and docstring summaries

Prose the classes cannot produce (how ``SearchRouter`` dispatches, the
relationship filters on ``SearchRequest``, graph enrichment) lives in
``docs/architecture/SEARCH_ARCHITECTURE.md``; the artifact links there.

The output is a pure function of its sources — no timestamps — so the drift
test can regenerate and byte-compare it
(``tests/unit/scripts/test_generate_search_method_catalog.py``). There is no
commit-time automation: regenerate after changing a search service or one of
the mixins; CI fails on a stale artifact.

Usage:
    uv run python scripts/generate_search_method_catalog.py          # regenerate
    uv run python scripts/generate_search_method_catalog.py --check  # exit 1 on drift
"""

from __future__ import annotations

import argparse
import inspect
import sys
from annotationlib import Format
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# scripts/ is not a package — the sibling import resolves at runtime via the
# sys.path entry above, not for MyPy (the same ignore as scripts/health/stale_names.py).
from detect_bloat import PLANNED_METHODS  # type: ignore[import-not-found]

from core.ports.search_protocols import DomainSearchOperations
from core.services.base_service import BaseService
from core.services.choices.choices_search_service import ChoicesSearchService
from core.services.events.events_search_service import EventsSearchService
from core.services.goals.goals_search_service import GoalsSearchService
from core.services.habits.habits_search_service import HabitsSearchService
from core.services.ku.ku_search_service import KuSearchService
from core.services.lp.lp_search_service import LpSearchService
from core.services.mixins import (
    RelationshipOperationsMixin,
    SearchOperationsMixin,
    TimeQueryMixin,
)
from core.services.principles.principles_search_service import PrinciplesSearchService
from core.services.ps.ps_search_service import PsSearchService
from core.services.tasks.tasks_search_service import TasksSearchService

if TYPE_CHECKING:
    from collections.abc import Callable

ARTIFACT_PATH = PROJECT_ROOT / "docs" / "reference" / "SEARCH_SERVICE_METHODS.md"


@dataclass(frozen=True)
class SearchServiceEntry:
    """One column of the matrix: a matrix label and the live search class."""

    label: str
    cls: type[BaseService[Any, Any]]


SERVICES: tuple[SearchServiceEntry, ...] = (
    SearchServiceEntry("Tasks", TasksSearchService),
    SearchServiceEntry("Goals", GoalsSearchService),
    SearchServiceEntry("Habits", HabitsSearchService),
    SearchServiceEntry("Events", EventsSearchService),
    SearchServiceEntry("Choices", ChoicesSearchService),
    SearchServiceEntry("Principles", PrinciplesSearchService),
    SearchServiceEntry("KU", KuSearchService),
    SearchServiceEntry("PS", PsSearchService),
    SearchServiceEntry("LP", LpSearchService),
)

# The BaseService mixins whose methods make up a search service's inherited
# search surface. CRUD, context and conversion are BaseService surface too, but
# not search: BASESERVICE_METHOD_INDEX.md lists them.
SEARCH_MIXINS: tuple[type, ...] = (
    SearchOperationsMixin,
    RelationshipOperationsMixin,
    TimeQueryMixin,
)

INHERITED = "I"
OVERRIDDEN = "O"
DEFINED = "D"
ABSENT = "-"

PROTOCOL_MARK = "†"
STAGED_NOTE = "**Staged** (`PLANNED_METHODS`)."


def _public_names(klass: type) -> list[str]:
    """Public callables a class defines in its own body."""
    return sorted(
        name for name, value in vars(klass).items() if not name.startswith("_") and callable(value)
    )


def _first_definer(cls: type, name: str) -> type | None:
    """The class that defines ``name`` for ``cls`` — first hit walking the MRO."""
    for klass in cls.__mro__:
        if name in vars(klass):
            return klass
    return None


def _service_side(klass: type) -> bool:
    """Is ``klass`` on the service's side of BaseService (the service or its own bases)?"""
    return klass not in BaseService.__mro__


def mixin_methods() -> dict[type, list[str]]:
    """Each search mixin's public methods, in ``SEARCH_MIXINS`` order."""
    return {mixin: _public_names(mixin) for mixin in SEARCH_MIXINS}


def service_methods(cls: type) -> list[str]:
    """Public methods a search service defines itself — overrides and its own."""
    return sorted(
        {
            name
            for klass in cls.__mro__
            if _service_side(klass) and klass is not object
            for name in _public_names(klass)
        }
    )


def domain_specific_methods() -> list[str]:
    """Methods some service defines that no search mixin provides."""
    inherited = {name for names in mixin_methods().values() for name in names}
    return sorted({name for entry in SERVICES for name in service_methods(entry.cls)} - inherited)


def cell(cls: type, name: str) -> str:
    """The matrix mark for ``name`` on ``cls``."""
    definer = _first_definer(cls, name)
    if definer is None:
        return ABSENT
    if not _service_side(definer):
        return INHERITED
    return OVERRIDDEN if getattr(BaseService, name, None) is not None else DEFINED


def protocol_methods() -> frozenset[str]:
    """The methods ``DomainSearchOperations`` declares."""
    return frozenset(_public_names(DomainSearchOperations))


def _annotation(annotation: object) -> str:
    # A module under ``from __future__ import annotations`` hands back the source
    # string itself; ``Format.STRING`` renders the rest as source text.
    return annotation if isinstance(annotation, str) else inspect.formatannotation(annotation)


def signature(func: Callable[..., object]) -> str:
    """The callable's signature as source text, without ``self``."""
    sig = inspect.signature(func, annotation_format=Format.STRING)
    params: list[str] = []
    star_written = False
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        prefix = ""
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            prefix = "*"
            star_written = True
        elif param.kind is inspect.Parameter.VAR_KEYWORD:
            prefix = "**"
        elif param.kind is inspect.Parameter.KEYWORD_ONLY and not star_written:
            params.append("*")
            star_written = True
        text = f"{prefix}{name}"
        if param.annotation is not inspect.Parameter.empty:
            text += f": {_annotation(param.annotation)}"
            if param.default is not inspect.Parameter.empty:
                text += f" = {param.default!r}"
        elif param.default is not inspect.Parameter.empty:
            text += f"={param.default!r}"
        params.append(text)
    rendered = f"({', '.join(params)})"
    if sig.return_annotation is not inspect.Signature.empty:
        rendered += f" -> {_annotation(sig.return_annotation)}"
    return rendered


def summary(func: Callable[..., object]) -> str:
    """The docstring's first paragraph on one line, or an em dash when there is none."""
    doc = inspect.getdoc(func)
    if not doc:
        return "—"
    paragraph = doc.strip().split("\n\n", 1)[0]
    return " ".join(paragraph.split()).replace("``", "`").replace("|", "\\|")


def _escape(text: str) -> str:
    return text.replace("|", "\\|")


def is_staged(owner: type, name: str) -> bool:
    """Is the method registered as staged-but-unwired in the bloat detector's PLANNED tier?"""
    definer = _first_definer(owner, name)
    return definer is not None and f"{_source_path(definer)}::{name}" in PLANNED_METHODS


def _method_rows(owner: type, names: list[str]) -> list[str]:
    lines = ["| Method | Signature | Summary |", "|--------|-----------|---------|"]
    for name in names:
        func = getattr(owner, name)
        staged = f" {STAGED_NOTE}" if is_staged(owner, name) else ""
        lines.append(f"| `{name}` | `{_escape(signature(func))}` | {summary(func)}{staged} |")
    return lines


def _matrix() -> list[str]:
    protocol = protocol_methods()
    header = "| Method | " + " | ".join(entry.label for entry in SERVICES) + " |"
    rule = "|--------|" + "|".join(":" + "-" * max(len(e.label) - 2, 1) + ":" for e in SERVICES)
    lines = [header, rule + "|"]

    def row(name: str) -> str:
        mark = PROTOCOL_MARK if name in protocol else ""
        cells = " | ".join(cell(entry.cls, name) for entry in SERVICES)
        return f"| `{name}()`{mark} | {cells} |"

    for mixin, names in mixin_methods().items():
        lines.append(f"| **{mixin.__name__}** |" + " |" * len(SERVICES))
        lines.extend(row(name) for name in names)
    lines.append("| **Defined by a service** |" + " |" * len(SERVICES))
    lines.extend(row(name) for name in domain_specific_methods())
    return lines


def _config_lines(cls: type[BaseService[Any, Any]]) -> list[str]:
    config = cls._config
    owner = config.user_ownership_relationship
    ownership = f"`{owner.value}` edge" if owner is not None else "none (shared content)"
    prerequisites = ", ".join(f"`{rel.value}`" for rel in config.prerequisite_relationships)
    enrichment = cls._graph_enrichment_patterns
    enrichment_text = (
        f"{len(enrichment)} patterns" if enrichment else "none — results carry no `_graph_context`"
    )
    return [
        f"- **Search fields:** {', '.join(f'`{f}`' for f in config.search_fields)}"
        f" (ordered by `{config.search_order_by}`)",
        f"- **Category field:** `{config.category_field}`",
        f"- **Date field:** `{config.date_field}`",
        f"- **Ownership:** {ownership}",
        f"- **Prerequisite edges:** {prerequisites or 'none'}",
        f"- **Graph enrichment (`_graph_enrichment_patterns`):** {enrichment_text}",
    ]


def _source_path(cls: type) -> str:
    return str(Path(inspect.getfile(cls)).resolve().relative_to(PROJECT_ROOT))


def render_catalog() -> str:
    """Render the full artifact. Pure function of the imported classes."""
    lines = [
        "---",
        "related_skills:",
        "- skuel-search-architecture",
        "---",
        "# Search Service Method Reference",
        "",
        "**WARNING:** This file is AUTO-GENERATED. Do not edit manually.",
        "**Regenerate:** `cd app && uv run python scripts/generate_search_method_catalog.py`",
        "**Drift-guarded:** `tests/unit/scripts/test_generate_search_method_catalog.py`",
        "",
        f"Every search method of the {len(SERVICES)} domain search services, read from the live"
        " classes. The inherited surface is the public methods of "
        + ", ".join(f"`{m.__name__}`" for m in SEARCH_MIXINS)
        + "; CRUD and the other `BaseService` mixins are in"
        " [BaseService Method Index](BASESERVICE_METHOD_INDEX.md).",
        "",
        "How `SearchRouter` reaches these services, the relationship filters on `SearchRequest`,"
        " and graph enrichment: [Search Architecture](../architecture/SEARCH_ARCHITECTURE.md).",
        "",
        "---",
        "",
        "## Quick Reference Matrix",
        "",
        f"**{INHERITED}** = inherited from the mixin · **{OVERRIDDEN}** = the service overrides"
        f" a `BaseService` method · **{DEFINED}** = defined by the service alone ·"
        f" **{ABSENT}** = not on the service · **{PROTOCOL_MARK}** = declared by"
        " `DomainSearchOperations`",
        "",
        "A method marked **Staged** below is registered in the bloat detector's PLANNED tier"
        " (`PLANNED_METHODS` in `scripts/detect_bloat.py`): built, and not yet reached by a"
        " production caller.",
        "",
        *_matrix(),
        "",
        "---",
        "",
        "## Inherited Methods",
        "",
    ]

    for mixin, names in mixin_methods().items():
        lines.extend(
            [
                f"### {mixin.__name__}",
                "",
                f"**File:** `{_source_path(mixin)}`",
                "",
                *_method_rows(mixin, names),
                "",
            ]
        )

    lines.extend(["---", "", "## Domain Search Services", ""])

    for entry in SERVICES:
        cls = entry.cls
        own = service_methods(cls)
        lines.extend(
            [
                f"### {cls.__name__}",
                "",
                f"**File:** `{_source_path(cls)}`",
                "",
                *_config_lines(cls),
                "",
            ]
        )
        if own:
            lines.extend(
                [
                    "**Overridden and own methods** (everything else is inherited — see the"
                    " matrix):",
                    "",
                    *_method_rows(cls, own),
                    "",
                ]
            )
        else:
            lines.extend(["Every method is inherited — see the matrix.", ""])

    lines.extend(
        [
            "---",
            "",
            "## See Also",
            "",
            # docs→docs links are relative to the artifact (docs/reference/); code links
            # stay repo-root-absolute — the vault rule, scripts/docs_relative_links.py.
            "- [Search Architecture](../architecture/SEARCH_ARCHITECTURE.md) — SearchRouter,"
            " relationship filters, graph enrichment",
            "- [Search Service Pattern](../patterns/search_service_pattern.md) — writing a"
            " search service",
            "- [BaseService Method Index](BASESERVICE_METHOD_INDEX.md) — the rest of the"
            " BaseService surface",
            "- [Search protocols](/core/ports/search_protocols.py) — `DomainSearchOperations`"
            " and the per-domain search protocols",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate docs/reference/SEARCH_SERVICE_METHODS.md"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the checked-in artifact differs from a fresh render (no write).",
    )
    args = parser.parse_args()

    content = render_catalog()

    if args.check:
        on_disk = ARTIFACT_PATH.read_text(encoding="utf-8") if ARTIFACT_PATH.exists() else ""
        if on_disk != content:
            print("❌ SEARCH_SERVICE_METHODS.md is stale.")
            print(
                "   Regenerate: cd app && uv run python scripts/generate_search_method_catalog.py"
            )
            return 1
        print("✅ SEARCH_SERVICE_METHODS.md is fresh.")
        return 0

    ARTIFACT_PATH.write_text(content, encoding="utf-8")
    print(f"✅ Generated: {ARTIFACT_PATH}")
    print(f"   Total lines: {len(content.splitlines())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
