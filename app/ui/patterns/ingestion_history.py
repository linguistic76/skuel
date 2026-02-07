"""
Ingestion History Dashboard UI Components
==========================================

Paginated list of past ingestion operations with details.

Components:
- IngestionHistoryDashboard: Main history view with pagination
- IngestionHistoryRow: Single row in history table
- PaginationControls: Page navigation
"""

from typing import Any

from fasthtml.common import *


def IngestionHistoryDashboard(entries: list[Any], page: int, total_pages: int) -> FT:
    """
    Ingestion history with pagination.

    Args:
        entries: List of IngestionHistoryEntry objects or dicts
        page: Current page number (1-indexed)
        total_pages: Total number of pages

    Returns:
        FastHTML component
    """
    return Div(
        H2("Ingestion History", cls="text-2xl font-bold mb-4"),
        P(
            "Audit trail of all ingestion operations",
            cls="text-sm text-base-content/70 mb-4",
        ),
        # History table
        Div(
            Table(
                Thead(
                    Tr(
                        Th("Started"),
                        Th("Type"),
                        Th("Source"),
                        Th("Status"),
                        Th("Files"),
                        Th("Duration"),
                        Th("Actions"),
                    )
                ),
                Tbody(
                    *[IngestionHistoryRow(entry) for entry in entries]
                    if entries
                    else [
                        Tr(
                            Td(
                                "No ingestion history found",
                                colspan="7",
                                cls="text-center text-base-content/50 py-8",
                            )
                        )
                    ]
                ),
                cls="table table-zebra table-sm",
            ),
            cls="overflow-x-auto",
        ),
        # Pagination
        PaginationControls(page, total_pages, "/ingest/history") if total_pages > 1 else None,
        cls="ingestion-history-dashboard",
    )


def IngestionHistoryRow(entry: Any) -> FT:
    """
    Single row in ingestion history table.

    Args:
        entry: IngestionHistoryEntry object or dict

    Returns:
        FastHTML component (Tr)
    """
    # Handle both dataclass and dict inputs
    if hasattr(entry, "__dict__"):
        entry_dict = entry.__dict__
    else:
        entry_dict = entry

    operation_id = entry_dict.get("operation_id", "")
    operation_type = entry_dict.get("operation_type", "unknown")
    started_at = entry_dict.get("started_at")
    status = entry_dict.get("status", "unknown")
    source_path = entry_dict.get("source_path", "")
    stats = entry_dict.get("stats", {})

    # Format datetime
    if hasattr(started_at, "strftime"):
        started_str = started_at.strftime("%Y-%m-%d %H:%M")
    else:
        started_str = str(started_at)

    # Status badge styling
    status_badge_map = {
        "completed": "badge-success",
        "failed": "badge-error",
        "in_progress": "badge-warning",
    }
    status_badge = status_badge_map.get(status, "badge-ghost")

    # Get stats
    total_files = stats.get("total_files", 0)
    successful = stats.get("successful", 0)
    duration = stats.get("duration_seconds", 0.0)

    return Tr(
        Td(started_str, cls="font-mono text-xs"),
        Td(
            Span(
                operation_type.upper(),
                cls="badge badge-sm badge-outline",
            )
        ),
        Td(
            source_path,
            cls="font-mono text-xs max-w-xs truncate",
            title=source_path,
        ),
        Td(
            Span(
                status.replace("_", " ").title(),
                cls=f"badge badge-sm {status_badge}",
            )
        ),
        Td(f"{successful} / {total_files}", cls="text-right"),
        Td(f"{duration:.1f}s", cls="text-right"),
        Td(
            A(
                "View Details",
                href=f"/ingest/results/{operation_id}",
                cls="link link-primary text-sm",
            )
        ),
    )


def PaginationControls(page: int, total_pages: int, base_url: str) -> FT:
    """
    Page navigation controls.

    Args:
        page: Current page number (1-indexed)
        total_pages: Total number of pages
        base_url: Base URL for pagination links

    Returns:
        FastHTML component
    """
    if total_pages <= 1:
        return None

    # Calculate page range to show (max 5 pages)
    start_page = max(1, page - 2)
    end_page = min(total_pages, start_page + 4)
    if end_page - start_page < 4:
        start_page = max(1, end_page - 4)

    page_links = []

    # Previous button
    if page > 1:
        page_links.append(
            A(
                "« Previous",
                href=f"{base_url}?page={page - 1}",
                cls="btn btn-sm",
            )
        )
    else:
        page_links.append(
            Button(
                "« Previous",
                cls="btn btn-sm btn-disabled",
                disabled=True,
            )
        )

    # Page numbers
    for p in range(start_page, end_page + 1):
        if p == page:
            page_links.append(
                Button(
                    str(p),
                    cls="btn btn-sm btn-active",
                )
            )
        else:
            page_links.append(
                A(
                    str(p),
                    href=f"{base_url}?page={p}",
                    cls="btn btn-sm",
                )
            )

    # Next button
    if page < total_pages:
        page_links.append(
            A(
                "Next »",
                href=f"{base_url}?page={page + 1}",
                cls="btn btn-sm",
            )
        )
    else:
        page_links.append(
            Button(
                "Next »",
                cls="btn btn-sm btn-disabled",
                disabled=True,
            )
        )

    return Div(
        Div(
            *page_links,
            cls="join",
        ),
        cls="flex justify-center mt-4",
    )


__all__ = [
    "IngestionHistoryDashboard",
    "IngestionHistoryRow",
    "PaginationControls",
]
