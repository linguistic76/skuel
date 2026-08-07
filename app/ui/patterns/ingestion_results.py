"""
Ingestion Results UI Components
================================

Formatted ingestion results with cards and tables, replacing raw JSON displays.

Components:
- IngestionResultsSummary: Main results view with stats cards and breakdowns
- StatCard: Stat card for individual metrics
- EntityBreakdownTable: Table showing entities by type
- ErrorsTable: Table showing ingestion errors with suggestions
"""

from typing import Any

from fasthtml.common import FT, H3, Div

from ui.components.table import Td
from ui.data import TableFromDicts, TableT
from ui.feedback import Badge, BadgeT
from ui.patterns.stats_grid import IconStat


def IngestionResultsSummary(stats: Any) -> FT:
    """
    Formatted ingestion results with cards and tables.

    Args:
        stats: IngestionStats or dict with stats data

    Returns:
        FastHTML component with formatted results
    """
    # Handle both dataclass and dict inputs
    stats_dict = getattr(stats, "__dict__", stats)

    total_files = stats_dict.get("total_files", 0)
    successful = stats_dict.get("successful", 0) or stats_dict.get("files_ingested", 0)
    failed = stats_dict.get("failed", 0) or stats_dict.get("files_failed", 0)
    duration = stats_dict.get("duration_seconds", 0.0)
    nodes_created = stats_dict.get("nodes_created", 0)
    nodes_updated = stats_dict.get("nodes_updated", 0)
    relationships_created = stats_dict.get("relationships_created", 0)
    errors = stats_dict.get("errors") or []

    # Check if this has incremental ingestion fields (these are only rendered
    # inside the has_incremental_stats guard below).
    has_incremental_stats = "files_skipped" in stats_dict
    files_skipped = stats_dict.get("files_skipped", 0)
    ingestion_efficiency = stats_dict.get("skip_efficiency", 0.0)

    return Div(
        # Summary cards
        Div(
            IconStat("Total Files", total_files, "📁"),
            IconStat("Successful", successful, "✅", "text-success"),
            IconStat("Failed", failed, "❌", "text-error" if failed > 0 else ""),
            IconStat("Duration", f"{duration:.1f}s", "⏱️"),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 shadow-sm rounded-lg mb-4 w-full",
        ),
        # Incremental ingestion stats (if present)
        (
            Div(
                H3("Ingestion Efficiency", cls="text-lg font-semibold mb-2"),
                Div(
                    IconStat("Files Skipped", files_skipped, "⏭️", "text-info"),
                    IconStat("Efficiency", f"{ingestion_efficiency:.1f}%", "🎯", "text-success"),
                    cls="grid grid-cols-2 gap-4 shadow-sm rounded-lg mb-4 w-full",
                ),
            )
            if has_incremental_stats
            else None
        ),
        # Graph changes section
        H3("Neo4j Changes", cls="text-lg font-semibold mb-2 mt-4"),
        Div(
            IconStat("Nodes Created", nodes_created, "🔵"),
            IconStat("Nodes Updated", nodes_updated, "🔄"),
            IconStat("Edges Created", relationships_created, "🔗"),
            cls="grid grid-cols-3 gap-4 shadow-sm rounded-lg mb-4 w-full",
        ),
        # Errors table (if any)
        ErrorsTable(errors) if errors else None,
        cls="ingestion-results-summary",
    )


def EntityBreakdownTable(entity_counts: dict[str, int]) -> FT | None:
    """
    Table showing entities by type.

    Args:
        entity_counts: Dictionary mapping entity type to count

    Returns:
        FastHTML component
    """
    if not entity_counts:
        return None

    def _breakdown_cell_render(k: str, v: object) -> Any:
        if k == "Entity Type":
            return Td(v, cls="font-semibold")
        if k == "Count":
            return Td(v, cls="text-right")
        return Td(v)

    return Div(
        H3("Entity Breakdown", cls="text-lg font-semibold mb-2 mt-4"),
        Div(
            TableFromDicts(
                header_data=["Entity Type", "Count"],
                body_data=[
                    {"Entity Type": et.upper(), "Count": str(count)}
                    for et, count in sorted(entity_counts.items())
                ],
                body_cell_render=_breakdown_cell_render,
                cls=(TableT.striped, TableT.sm),
            ),
            cls="overflow-x-auto",
        ),
        cls="mb-4",
    )


def ErrorsTable(errors: list[dict[str, Any]]) -> FT | None:
    """
    Table showing ingestion errors with suggestions.

    Args:
        errors: List of error dicts

    Returns:
        FastHTML component
    """
    if not errors:
        return None

    def _error_cell_render(k: str, v: object) -> Any:
        styles = {
            "File": "font-mono text-xs max-w-xs truncate",
            "Error": "text-sm",
            "Suggestion": "text-sm text-muted-foreground",
        }
        return Td(v, cls=styles.get(k, ""))

    return Div(
        H3("Errors", cls="text-lg font-semibold mb-2 mt-4 text-error"),
        Div(
            TableFromDicts(
                header_data=["File", "Stage", "Error", "Suggestion"],
                body_data=[
                    {
                        "File": error.get("file", "unknown"),
                        "Stage": Badge(error.get("stage", "unknown"), variant=BadgeT.outline),
                        "Error": error.get("error", "Unknown error"),
                        "Suggestion": error.get("suggestion", "—"),
                    }
                    for error in errors
                ],
                body_cell_render=_error_cell_render,
                cls=(TableT.striped, TableT.sm),
            ),
            cls="overflow-x-auto",
        ),
        cls="mb-4",
    )


__all__ = [
    "IngestionResultsSummary",
    "EntityBreakdownTable",
    "ErrorsTable",
]
