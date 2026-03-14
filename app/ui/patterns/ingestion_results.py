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

from fasthtml.common import FT, H3, Div, Span, Strong, Td

from ui.data import TableFromDicts, TableT
from ui.feedback import Badge, BadgeT


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

    # Check if this has incremental ingestion fields
    has_incremental_stats = "files_skipped" in stats_dict
    files_skipped = stats_dict.get("files_skipped", 0) if has_incremental_stats else None
    ingestion_efficiency = stats_dict.get("skip_efficiency", 0.0) if has_incremental_stats else None

    return Div(
        # Summary cards
        Div(
            StatCard("Total Files", total_files, "📁"),
            StatCard("Successful", successful, "✅", "text-success"),
            StatCard("Failed", failed, "❌", "text-error" if failed > 0 else ""),
            StatCard("Duration", f"{duration:.1f}s", "⏱️"),
            cls="stats stats-vertical lg:stats-horizontal shadow mb-4 w-full",
        ),
        # Incremental ingestion stats (if present)
        (
            Div(
                H3("Ingestion Efficiency", cls="text-lg font-semibold mb-2"),
                Div(
                    StatCard("Files Skipped", files_skipped, "⏭️", "text-info"),
                    StatCard("Efficiency", f"{ingestion_efficiency:.1f}%", "🎯", "text-success"),
                    cls="stats stats-vertical lg:stats-horizontal shadow mb-4 w-full",
                ),
            )
            if has_incremental_stats
            else None
        ),
        # Graph changes section
        H3("Neo4j Changes", cls="text-lg font-semibold mb-2 mt-4"),
        Div(
            StatCard("Nodes Created", nodes_created, "🔵"),
            StatCard("Nodes Updated", nodes_updated, "🔄"),
            StatCard("Edges Created", relationships_created, "🔗"),
            cls="stats stats-vertical lg:stats-horizontal shadow mb-4 w-full",
        ),
        # Errors table (if any)
        ErrorsTable(errors) if errors else None,
        cls="ingestion-results-summary",
    )


def StatCard(label: str, value: Any, icon: str, color_class: str = "") -> FT:
    """
    Stat card for displaying a single metric.

    Args:
        label: Stat label
        value: Stat value
        icon: Emoji icon
        color_class: Optional Tailwind color class (e.g., "text-success")

    Returns:
        FastHTML component
    """
    return Div(
        Div(icon, cls="stat-figure text-2xl"),
        Div(label, cls="stat-title"),
        Div(str(value), cls=f"stat-value {color_class}"),
        cls="stat",
    )


def EntityBreakdownTable(entity_counts: dict[str, int]) -> FT:
    """
    Table showing entities by type.

    Args:
        entity_counts: Dictionary mapping entity type to count

    Returns:
        FastHTML component
    """
    if not entity_counts:
        return None

    def _breakdown_cell_render(k: str, v: object) -> Td:
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


def ErrorsTable(errors: list[dict[str, Any]]) -> FT:
    """
    Table showing ingestion errors with suggestions.

    Args:
        errors: List of error dicts

    Returns:
        FastHTML component
    """
    if not errors:
        return None

    def _error_cell_render(k: str, v: object) -> Td:
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


def ProgressIndicator(operation_id: str) -> FT:
    """
    Real-time progress bar with Alpine.js WebSocket connection.

    Args:
        operation_id: UUID of the ingestion operation

    Returns:
        FastHTML component with Alpine.js data binding
    """
    return Div(
        # Connection status
        Div(
            Span(
                "🟢 Connected",
                **{"x-show": "connected"},
                cls="text-success text-sm",
            ),
            Span(
                "🔴 Disconnected",
                **{"x-show": "!connected"},
                cls="text-error text-sm",
            ),
            cls="mb-2",
        ),
        # Progress bar
        Div(
            Div(
                cls="bg-primary h-4 rounded transition-all duration-300",
                **{"x-bind:style": "{ width: percentage + '%' }"},
            ),
            cls="w-full bg-secondary rounded h-4 mb-2 overflow-hidden",
        ),
        # Stats
        Div(
            Span("Progress: ", cls="font-semibold"),
            Span(**{"x-text": "`${current} / ${total}`"}),
            Span(" (", **{"x-text": "percentage + '%'"}),
            Span(")"),
            cls="text-sm mb-2",
        ),
        # Current file
        Div(
            Strong("Current: "),
            Span(**{"x-text": "currentFile"}, cls="font-mono text-xs"),
            cls="text-sm text-muted-foreground mb-2 truncate",
        ),
        # ETA
        Div(
            Strong("ETA: "),
            Span(**{"x-text": "formatEta()"}),
            cls="text-sm",
        ),
        # Error message (if any)
        Div(
            Strong("Error: ", cls="text-error"),
            Span(**{"x-text": "error"}, cls="text-error"),
            **{"x-show": "error"},
            cls="text-sm mt-2",
        ),
        **{"x-data": f"ingestionProgress('{operation_id}')"},
        cls="ingestion-progress-indicator p-4 bg-muted rounded-lg",
    )


__all__ = [
    "IngestionResultsSummary",
    "StatCard",
    "EntityBreakdownTable",
    "ErrorsTable",
    "ProgressIndicator",
]
