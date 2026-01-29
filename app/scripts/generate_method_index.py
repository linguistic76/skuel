#!/usr/bin/env python3
"""
Generate BaseService Method Index Documentation
===============================================

Automatically generates /docs/reference/BASESERVICE_METHOD_INDEX.md
by extracting method signatures from:
- BaseService mixins (7 mixins)
- Activity Domain facades (_delegations dicts)

Usage:
    python scripts/generate_method_index.py

Output:
    /docs/reference/BASESERVICE_METHOD_INDEX.md (auto-generated)

Pre-commit Hook:
    This script runs automatically on commit to keep docs in sync.

Version: 1.0.0
Date: 2026-01-29
"""

import ast
import inspect
from pathlib import Path
from typing import Any

# Add project root to Python path
import sys
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def extract_delegations_from_file(filepath: Path) -> dict[str, tuple[str, str]]:
    """
    Extract _delegations dict from a facade service file.

    Args:
        filepath: Path to the facade service file

    Returns:
        Dictionary of {facade_method: (sub_service, target_method)}
    """
    with open(filepath) as f:
        source = f.read()

    tree = ast.parse(source)

    # Find the class with _delegations attribute
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if (
                    isinstance(item, ast.Assign)
                    and isinstance(item.targets[0], ast.Name)
                    and item.targets[0].id == "_delegations"
                ):
                    # Found _delegations assignment
                    # Try to evaluate it (works for simple dicts)
                    try:
                        delegations = ast.literal_eval(item.value)
                        return delegations
                    except (ValueError, SyntaxError):
                        # Complex expression (merge_delegations, etc.)
                        # Fall back to parsing the structure
                        return _parse_delegation_expr(item.value)

    return {}


def _parse_delegation_expr(node: ast.expr) -> dict[str, tuple[str, str]]:
    """
    Parse complex delegation expressions like merge_delegations(...).

    Args:
        node: AST expression node

    Returns:
        Dictionary of delegations
    """
    result: dict[str, tuple[str, str]] = {}

    # Handle merge_delegations() calls
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "merge_delegations"
    ):
        for arg in node.args:
            if isinstance(arg, ast.Dict):
                # Direct dict argument
                for key, value in zip(arg.keys, arg.values, strict=False):
                    if isinstance(key, ast.Constant) and isinstance(value, ast.Tuple):
                        method_name = key.value
                        if len(value.elts) == 2:
                            sub_service = ast.literal_eval(value.elts[0])
                            target_method = ast.literal_eval(value.elts[1])
                            result[method_name] = (sub_service, target_method)

    # Handle simple dict
    elif isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=False):
            if isinstance(key, ast.Constant) and isinstance(value, ast.Tuple):
                method_name = key.value
                if len(value.elts) == 2:
                    sub_service = ast.literal_eval(value.elts[0])
                    target_method = ast.literal_eval(value.elts[1])
                    result[method_name] = (sub_service, target_method)

    return result


def get_mixin_methods() -> dict[str, list[str]]:
    """
    Get methods from each BaseService mixin.

    Returns:
        Dictionary of {mixin_name: [method_names]}
    """
    # Import mixins dynamically to extract methods
    from core.services.mixins import (
        ContextOperationsMixin,
        ConversionHelpersMixin,
        CrudOperationsMixin,
        RelationshipOperationsMixin,
        SearchOperationsMixin,
        TimeQueryMixin,
        UserProgressMixin,
    )

    mixins = {
        "ConversionHelpersMixin": ConversionHelpersMixin,
        "CrudOperationsMixin": CrudOperationsMixin,
        "SearchOperationsMixin": SearchOperationsMixin,
        "RelationshipOperationsMixin": RelationshipOperationsMixin,
        "TimeQueryMixin": TimeQueryMixin,
        "UserProgressMixin": UserProgressMixin,
        "ContextOperationsMixin": ContextOperationsMixin,
    }

    result: dict[str, list[str]] = {}

    for mixin_name, mixin_class in mixins.items():
        methods = []
        for name in dir(mixin_class):
            if not name.startswith("_") or name in ["__init__"]:
                attr = getattr(mixin_class, name)
                if callable(attr):
                    methods.append(name)
        result[mixin_name] = sorted(methods)

    return result


def generate_method_index() -> str:
    """
    Generate the complete method index markdown.

    Returns:
        Markdown content
    """
    lines = []

    # Header
    lines.append("# BaseService Method Index")
    lines.append("")
    lines.append(
        "**Purpose:** Complete reference of all methods available in BaseService and Activity Domain facades."
    )
    lines.append("")
    lines.append(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d')} (Auto-generated)")
    lines.append("")
    lines.append("**WARNING:** This file is AUTO-GENERATED. Do not edit manually.")
    lines.append("**To update:** Run `python scripts/generate_method_index.py`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    lines.append(
        "- [BaseService Mixin Methods](#baseservice-mixin-methods) - Methods from 7 mixins"
    )
    lines.append("- [Activity Domain Facades](#activity-domain-facades) - Facade delegations")
    lines.append("- [Common Patterns](#common-patterns) - Usage examples")
    lines.append("")
    lines.append("---")
    lines.append("")

    # BaseService Mixin Methods
    lines.append("## BaseService Mixin Methods")
    lines.append("")
    lines.append("These methods are available on **all services that extend BaseService**.")
    lines.append("")

    mixin_methods = get_mixin_methods()

    mixin_descriptions = {
        "ConversionHelpersMixin": "DTO ↔ Domain model conversion and result handling",
        "CrudOperationsMixin": "CRUD operations with ownership verification",
        "SearchOperationsMixin": "Text search, filtering, and graph-aware queries",
        "RelationshipOperationsMixin": "Graph relationship operations and traversal",
        "TimeQueryMixin": "Calendar and scheduling queries",
        "UserProgressMixin": "Progress and mastery tracking",
        "ContextOperationsMixin": "Retrieve entities with enriched graph context",
    }

    for mixin_name, methods in mixin_methods.items():
        lines.append(f"### {mixin_name}")
        lines.append("")
        lines.append(f"**Purpose:** {mixin_descriptions.get(mixin_name, 'N/A')}")
        lines.append("")
        lines.append("| Method | Public |")
        lines.append("|--------|--------|")

        for method in methods:
            is_public = "✅" if not method.startswith("_") else "🔒 (internal)"
            lines.append(f"| `{method}()` | {is_public} |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Activity Domain Facades
    lines.append("## Activity Domain Facades")
    lines.append("")
    lines.append("Auto-generated delegation methods for each Activity Domain facade.")
    lines.append("")

    # Extract delegations from facade files
    facades = [
        ("TasksService", "tasks_service.py"),
        ("GoalsService", "goals_service.py"),
        ("HabitsService", "habits_service.py"),
        ("EventsService", "events_service.py"),
        ("ChoicesService", "choices_service.py"),
        ("PrinciplesService", "principles_service.py"),
    ]

    for facade_name, filename in facades:
        filepath = project_root / "core" / "services" / filename
        if filepath.exists():
            delegations = extract_delegations_from_file(filepath)

            lines.append(f"### {facade_name}")
            lines.append("")
            lines.append(f"**Total Delegated Methods:** {len(delegations)}")
            lines.append("")

            if delegations:
                # Group by sub-service
                by_service: dict[str, list[tuple[str, str]]] = {}
                for facade_method, (sub_service, target_method) in delegations.items():
                    if sub_service not in by_service:
                        by_service[sub_service] = []
                    by_service[sub_service].append((facade_method, target_method))

                for sub_service, methods in sorted(by_service.items()):
                    lines.append(
                        f"#### {sub_service.capitalize()} Delegations ({len(methods)} methods)"
                    )
                    lines.append("")
                    lines.append("| Facade Method | Target Method |")
                    lines.append("|---------------|---------------|")

                    for facade_method, target_method in sorted(methods):
                        lines.append(f"| `{facade_method}()` | `{sub_service}.{target_method}()` |")

                    lines.append("")

            lines.append("---")
            lines.append("")

    # Common Patterns
    lines.append("## Common Patterns")
    lines.append("")
    lines.append("### Facade Usage (Production)")
    lines.append("")
    lines.append("```python")
    lines.append("from core.services.tasks_service import TasksService")
    lines.append("")
    lines.append("# Auto-delegation to sub-services")
    lines.append("result = await tasks_service.create_task(request, user_uid)")
    lines.append("```")
    lines.append("")
    lines.append("### Direct Sub-Service Usage (Testing)")
    lines.append("")
    lines.append("```python")
    lines.append("from core.services.tasks import TasksCoreService")
    lines.append("")
    lines.append("core = TasksCoreService(backend=mock_backend)")
    lines.append("result = await core.create_task(request, user_uid)")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## See Also")
    lines.append("")
    lines.append(
        "- [Sub-Service Catalog](/docs/reference/SUB_SERVICE_CATALOG.md) - Which service does what"
    )
    lines.append("- [Quick Start Guide](/docs/guides/BASESERVICE_QUICK_START.md) - Usage patterns")
    lines.append(
        "- [Service Topology](/docs/architecture/SERVICE_TOPOLOGY.md) - Architecture diagrams"
    )
    lines.append("- [BaseService Source](/core/services/base_service.py) - Implementation")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Generate the method index documentation."""
    print("Generating BaseService Method Index...")

    content = generate_method_index()

    output_path = project_root / "docs" / "reference" / "BASESERVICE_METHOD_INDEX.md"
    output_path.write_text(content)

    print(f"✅ Generated: {output_path}")
    print(f"   Total lines: {len(content.splitlines())}")


if __name__ == "__main__":
    main()
