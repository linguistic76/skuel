"""
Dry-Run Preview UI Components
==============================

Preview of sync changes before execution.

Components:
- DryRunPreviewComponent: Main preview view
- FilesToCreateTable: Table of files that would be created
- FilesToUpdateTable: Table of files that would be updated
- ValidationMessages: Warning and error messages
"""

from typing import Any

from fasthtml.common import *


def DryRunPreviewComponent(preview: Any, operation_id: str | None = None) -> FT:
    """
    Preview of sync changes before execution.

    Args:
        preview: DryRunPreview object or dict
        operation_id: Optional operation ID for executing the sync

    Returns:
        FastHTML component with preview
    """
    # Handle both dataclass and dict inputs
    if hasattr(preview, "__dict__"):
        preview_dict = preview.__dict__
    else:
        preview_dict = preview

    total_files = preview_dict.get("total_files", 0)
    files_to_create = preview_dict.get("files_to_create", [])
    files_to_update = preview_dict.get("files_to_update", [])
    files_to_skip = preview_dict.get("files_to_skip", [])
    relationships_to_create = preview_dict.get("relationships_to_create", [])
    validation_warnings = preview_dict.get("validation_warnings", [])
    validation_errors = preview_dict.get("validation_errors", [])

    return Div(
        H2("Dry-Run Preview", cls="text-2xl font-bold mb-4"),
        # Summary stats
        Div(
            Div(
                Div("📊", cls="stat-figure text-2xl"),
                Div("Total Files", cls="stat-title"),
                Div(str(total_files), cls="stat-value"),
                cls="stat",
            ),
            Div(
                Div("➕", cls="stat-figure text-2xl text-success"),
                Div("To Create", cls="stat-title"),
                Div(str(len(files_to_create)), cls="stat-value text-success"),
                cls="stat",
            ),
            Div(
                Div("🔄", cls="stat-figure text-2xl text-warning"),
                Div("To Update", cls="stat-title"),
                Div(str(len(files_to_update)), cls="stat-value text-warning"),
                cls="stat",
            ),
            Div(
                Div("⏭️", cls="stat-figure text-2xl text-base-content/50"),
                Div("To Skip", cls="stat-title"),
                Div(str(len(files_to_skip)), cls="stat-value text-base-content/50"),
                cls="stat",
            ),
            cls="stats stats-vertical lg:stats-horizontal shadow mb-4 w-full",
        ),
        # Relationship stats
        (
            Div(
                H3("Relationships", cls="text-lg font-semibold mb-2"),
                P(
                    f"Would create {len(relationships_to_create)} relationships between entities",
                    cls="text-sm text-base-content/70",
                ),
                cls="mb-4",
            )
            if relationships_to_create
            else None
        ),
        # Validation messages
        ValidationMessages(validation_warnings, validation_errors),
        # Files to create
        FilesToCreateTable(files_to_create) if files_to_create else None,
        # Files to update
        FilesToUpdateTable(files_to_update) if files_to_update else None,
        # Action buttons (if operation_id provided)
        (
            Div(
                Button(
                    "Execute Sync",
                    cls="btn btn-primary",
                    hx_post="/api/ingest/execute",
                    hx_vals=f'{{"operation_id": "{operation_id}"}}',
                    hx_target="#sync-results",
                ),
                Button("Cancel", cls="btn btn-ghost", onclick="window.history.back()"),
                cls="flex gap-2 mt-4",
            )
            if operation_id
            else None
        ),
        cls="dry-run-preview",
    )


def FilesToCreateTable(files_to_create: list[dict[str, Any]]) -> FT:
    """
    Table showing files that would be created.

    Args:
        files_to_create: List of file dicts with uid, title, entity_type, file_path

    Returns:
        FastHTML component
    """
    if not files_to_create:
        return None

    return Div(
        H3("Files to Create", cls="text-lg font-semibold mb-2 mt-4 text-success"),
        P(f"{len(files_to_create)} new entities", cls="text-sm text-base-content/70 mb-2"),
        Div(
            Table(
                Thead(
                    Tr(
                        Th("UID"),
                        Th("Title"),
                        Th("Type"),
                        Th("File"),
                    )
                ),
                Tbody(
                    *[
                        Tr(
                            Td(
                                file.get("uid", ""),
                                cls="font-mono text-xs",
                            ),
                            Td(file.get("title", "Untitled")),
                            Td(
                                Span(
                                    file.get("entity_type", "unknown").upper(),
                                    cls="badge badge-sm badge-outline badge-success",
                                )
                            ),
                            Td(
                                file.get("file_path", ""),
                                cls="font-mono text-xs max-w-xs truncate",
                                title=file.get("file_path", ""),
                            ),
                        )
                        for file in files_to_create[:100]  # Limit to 100 for performance
                    ]
                ),
                cls="table table-zebra table-sm",
            ),
            cls="overflow-x-auto",
        ),
        (
            P(
                f"Showing first 100 of {len(files_to_create)} files",
                cls="text-sm text-base-content/70 mt-2",
            )
            if len(files_to_create) > 100
            else None
        ),
        cls="mb-4",
    )


def FilesToUpdateTable(files_to_update: list[dict[str, Any]]) -> FT:
    """
    Table showing files that would be updated.

    Args:
        files_to_update: List of file dicts with uid, title, changes_summary

    Returns:
        FastHTML component
    """
    if not files_to_update:
        return None

    return Div(
        H3("Files to Update", cls="text-lg font-semibold mb-2 mt-4 text-warning"),
        P(
            f"{len(files_to_update)} existing entities",
            cls="text-sm text-base-content/70 mb-2",
        ),
        Div(
            Table(
                Thead(
                    Tr(
                        Th("UID"),
                        Th("Title"),
                        Th("Type"),
                        Th("Changes"),
                    )
                ),
                Tbody(
                    *[
                        Tr(
                            Td(
                                file.get("uid", ""),
                                cls="font-mono text-xs",
                            ),
                            Td(file.get("title", "Untitled")),
                            Td(
                                Span(
                                    file.get("entity_type", "unknown").upper(),
                                    cls="badge badge-sm badge-outline badge-warning",
                                )
                            ),
                            Td(
                                file.get("changes_summary", "Content updated"),
                                cls="text-sm text-base-content/70",
                            ),
                        )
                        for file in files_to_update[:100]  # Limit to 100 for performance
                    ]
                ),
                cls="table table-zebra table-sm",
            ),
            cls="overflow-x-auto",
        ),
        (
            P(
                f"Showing first 100 of {len(files_to_update)} files",
                cls="text-sm text-base-content/70 mt-2",
            )
            if len(files_to_update) > 100
            else None
        ),
        cls="mb-4",
    )


def ValidationMessages(warnings: list[str], errors: list[str]) -> FT:
    """
    Display validation warnings and errors.

    Args:
        warnings: List of warning messages
        errors: List of error messages

    Returns:
        FastHTML component
    """
    if not warnings and not errors:
        return None

    return Div(
        # Warnings
        (
            Div(
                Div(
                    "⚠️",
                    cls="text-warning text-2xl mr-2",
                ),
                Div(
                    H4("Warnings", cls="font-semibold text-warning mb-1"),
                    Ul(
                        *[Li(warning, cls="text-sm") for warning in warnings],
                        cls="list-disc list-inside",
                    ),
                    cls="flex-1",
                ),
                cls="flex items-start",
            )
            if warnings
            else None
        ),
        # Errors
        (
            Div(
                Div(
                    "❌",
                    cls="text-error text-2xl mr-2",
                ),
                Div(
                    H4("Errors", cls="font-semibold text-error mb-1"),
                    Ul(
                        *[Li(error, cls="text-sm") for error in errors],
                        cls="list-disc list-inside",
                    ),
                    cls="flex-1",
                ),
                cls="flex items-start mt-2" if warnings else "flex items-start",
            )
            if errors
            else None
        ),
        cls="alert alert-warning mb-4" if warnings and not errors else "alert alert-error mb-4",
    )


__all__ = [
    "DryRunPreviewComponent",
    "FilesToCreateTable",
    "FilesToUpdateTable",
    "ValidationMessages",
]
