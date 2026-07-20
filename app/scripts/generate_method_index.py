#!/usr/bin/env python3
"""
Generate the BaseService Method Index — docs/reference/BASESERVICE_METHOD_INDEX.md
===================================================================================

One checked-in view of the method surface a SKUEL service developer works
against, read from the live classes so it can never describe code that does
not exist:

- ``BaseService`` mixin methods — the mixin spine is read from
  ``BaseService.__bases__`` (never a hand-maintained list), so a newly
  composed mixin cannot be silently omitted
- the shared ``KnowledgeIntelligenceDelegationMixin`` surface inherited by
  all six Activity Domain facades
- each facade's *facade-specific* public methods — every public callable
  whose defining class (first hit walking the MRO) is outside the shared
  spine, which includes facade-local mixins like ``_OrchestrationMixin``

The output is a pure function of its sources — no timestamps — so the drift
test can regenerate and byte-compare it
(``tests/unit/scripts/test_generate_method_index.py``). There is NO
commit-time automation: regenerate manually after changing mixins or facades;
CI fails on a stale artifact.

Usage:
    uv run python scripts/generate_method_index.py          # regenerate
    uv run python scripts/generate_method_index.py --check  # exit 1 on drift
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path
from typing import Generic

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.services.base_service import BaseService
from core.services.choices_service import ChoicesService
from core.services.events_service import EventsService
from core.services.goals_service import GoalsService
from core.services.habits_service import HabitsService
from core.services.mixins import KnowledgeIntelligenceDelegationMixin
from core.services.principles_service import PrinciplesService
from core.services.tasks_service import TasksService

ARTIFACT_PATH = PROJECT_ROOT / "docs" / "reference" / "BASESERVICE_METHOD_INDEX.md"

FACADES: tuple[type, ...] = (
    TasksService,
    GoalsService,
    HabitsService,
    EventsService,
    ChoicesService,
    PrinciplesService,
)

# Prose only — the mixin LIST comes from BaseService.__bases__, never from
# these keys. A newly composed mixin renders with "N/A" until described here.
MIXIN_DESCRIPTIONS: dict[str, str] = {
    "ConversionHelpersMixin": "DTO ↔ Domain model conversion and result handling",
    "CrudOperationsMixin": "CRUD operations with ownership verification",
    "SearchOperationsMixin": "Text search, filtering, and graph-aware queries",
    "RelationshipOperationsMixin": "Graph relationship operations and traversal",
    "TimeQueryMixin": "Calendar and scheduling queries",
    "ContextOperationsMixin": "Retrieve entities with enriched graph context",
    "KnowledgeIntelligenceDelegationMixin": (
        "Knowledge intelligence delegation shared by all Activity Domain facades"
    ),
}


def mixin_spine() -> tuple[type, ...]:
    """The mixins BaseService composes, in definition (MRO) order."""
    return tuple(base for base in BaseService.__bases__ if base.__name__.endswith("Mixin"))


def _shared_spine_classes() -> frozenset[type]:
    """Classes whose methods are shared surface, not facade-specific."""
    return frozenset(
        {object, Generic, BaseService, KnowledgeIntelligenceDelegationMixin, *mixin_spine()}
    )


def public_methods(cls: type) -> list[str]:
    """Sorted public callables reachable on the class."""
    return sorted(
        name for name in dir(cls) if not name.startswith("_") and callable(getattr(cls, name))
    )


def _first_definer(cls: type, name: str) -> type | None:
    """The class that actually defines ``name`` — first hit walking the MRO."""
    for klass in cls.__mro__:
        if name in vars(klass):
            return klass
    return None


def facade_specific_methods(facade: type) -> list[str]:
    """Public methods the facade adds on top of the shared spine.

    Attribution by defining class, so methods contributed by facade-local
    mixins (e.g. ``_OrchestrationMixin``) and facade overrides of spine
    methods are both included.
    """
    shared = _shared_spine_classes()
    return sorted(
        name for name in public_methods(facade) if _first_definer(facade, name) not in shared
    )


def _method_table(cls: type, methods: list[str]) -> list[str]:
    lines = ["| Method | Async |", "|--------|-------|"]
    for method in methods:
        marker = "✅" if inspect.iscoroutinefunction(getattr(cls, method)) else "—"
        lines.append(f"| `{method}()` | {marker} |")
    return lines


def render_method_index() -> str:
    """Render the full artifact. Pure function of the imported classes."""
    mixins = mixin_spine()
    lines = [
        "# BaseService Method Index",
        "",
        "**Purpose:** Complete reference of all methods available in BaseService"
        " and Activity Domain facades.",
        "",
        "**WARNING:** This file is AUTO-GENERATED. Do not edit manually.",
        "**Regenerate:** `cd app && uv run python scripts/generate_method_index.py`",
        "**Drift-guarded:** `tests/unit/scripts/test_generate_method_index.py`",
        "",
        "---",
        "",
        "## Table of Contents",
        "",
        f"- [BaseService Mixin Methods](#baseservice-mixin-methods) - Methods from"
        f" {len(mixins)} mixins",
        "- [Shared Facade Mixins](#shared-facade-mixins) - Inherited by all"
        f" {len(FACADES)} Activity Domain facades",
        "- [Activity Domain Facades](#activity-domain-facades) - Facade-specific public methods",
        "- [Common Patterns](#common-patterns) - Usage examples",
        "",
        "---",
        "",
        "## BaseService Mixin Methods",
        "",
        "These methods are available on **all services that extend BaseService**.",
        "",
    ]

    for mixin in mixins:
        lines.append(f"### {mixin.__name__}")
        lines.append("")
        lines.append(f"**Purpose:** {MIXIN_DESCRIPTIONS.get(mixin.__name__, 'N/A')}")
        lines.append("")
        lines.extend(_method_table(mixin, public_methods(mixin)))
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Shared Facade Mixins")
    lines.append("")
    lines.append(f"Inherited by all {len(FACADES)} Activity Domain facades on top of BaseService.")
    lines.append("")
    lines.append(f"### {KnowledgeIntelligenceDelegationMixin.__name__}")
    lines.append("")
    lines.append(
        "**Purpose:** "
        f"{MIXIN_DESCRIPTIONS.get(KnowledgeIntelligenceDelegationMixin.__name__, 'N/A')}"
    )
    lines.append("")
    lines.extend(
        _method_table(
            KnowledgeIntelligenceDelegationMixin,
            public_methods(KnowledgeIntelligenceDelegationMixin),
        )
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Activity Domain Facades")
    lines.append("")
    lines.append(
        "Facade-specific public methods — what each facade adds on top of the"
        " shared BaseService + KnowledgeIntelligenceDelegationMixin surface"
        " (explicit delegation methods, facade-local mixins, and overrides)."
    )
    lines.append("")

    for facade in FACADES:
        methods = facade_specific_methods(facade)
        lines.append(f"### {facade.__name__}")
        lines.append("")
        lines.append(f"**Facade-specific public methods:** {len(methods)}")
        lines.append("")
        lines.extend(_method_table(facade, methods))
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.extend(
        [
            "## Common Patterns",
            "",
            "### Facade Usage (Production)",
            "",
            "```python",
            "from core.services.tasks_service import TasksService",
            "",
            "# Auto-delegation to sub-services",
            "result = await tasks_service.create_task(request, user_uid)",
            "```",
            "",
            "### Direct Sub-Service Usage (Testing)",
            "",
            "```python",
            "from core.services.tasks import TasksCoreService",
            "",
            "core = TasksCoreService(backend=mock_backend)",
            "result = await core.create_task(request, user_uid)",
            "```",
            "",
            "---",
            "",
            "## See Also",
            "",
            "- [Sub-Service Catalog](/docs/reference/SUB_SERVICE_CATALOG.md)"
            " - Which service does what",
            "- [Quick Start Guide](/docs/guides/BASESERVICE_QUICK_START.md) - Usage patterns",
            "- [Service Topology](/docs/architecture/SERVICE_TOPOLOGY.md) - Architecture diagrams",
            "- [BaseService Source](/core/services/base_service.py) - Implementation",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate docs/reference/BASESERVICE_METHOD_INDEX.md"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the checked-in artifact differs from a fresh render (no write).",
    )
    args = parser.parse_args()

    content = render_method_index()

    if args.check:
        on_disk = ARTIFACT_PATH.read_text(encoding="utf-8") if ARTIFACT_PATH.exists() else ""
        if on_disk != content:
            print("❌ BASESERVICE_METHOD_INDEX.md is stale.")
            print("   Regenerate: cd app && uv run python scripts/generate_method_index.py")
            return 1
        print("✅ BASESERVICE_METHOD_INDEX.md is fresh.")
        return 0

    ARTIFACT_PATH.write_text(content, encoding="utf-8")
    print(f"✅ Generated: {ARTIFACT_PATH}")
    print(f"   Total lines: {len(content.splitlines())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
