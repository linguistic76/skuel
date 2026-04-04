"""
Upload Results Component
========================

FastHTML component for displaying per-file upload results.
Used by the HTMX upload endpoint to render results inline.
"""

from fasthtml.common import Div, Li, Span, Ul

from core.services.ingestion.user_upload_service import FileUploadResult, UploadBatchResult


def UploadResultsSummary(batch: UploadBatchResult) -> Div:
    """Render upload batch results as a summary + per-file list."""
    # Summary stats
    summary = Div(
        Span(f"{batch.successful} succeeded", cls="text-green-600 font-bold"),
        " / " if batch.failed > 0 else "",
        Span(f"{batch.failed} failed", cls="text-destructive font-bold")
        if batch.failed > 0
        else "",
        f" — {batch.total} file{'s' if batch.total != 1 else ''} processed",
        cls="mb-2",
    )

    # Per-file results
    items = [_file_result_item(r) for r in batch.results]

    return Div(
        summary,
        Ul(*items, cls="divide-y mt-2"),
        cls="mt-6",
    )


def _file_result_item(result: FileUploadResult) -> Li:
    """Render a single file result as a list item."""
    if result.success:
        return Li(
            Span(result.filename, cls="font-bold"),
            Span(f" [{result.entity_type}]", cls="text-muted-foreground")
            if result.entity_type
            else "",
            Span(f" → {result.uid}", cls="text-sm text-muted-foreground") if result.uid else "",
            cls="text-green-600 py-2",
        )
    else:
        return Li(
            Span(result.filename, cls="font-bold"),
            Span(f" [{result.entity_type}]", cls="text-muted-foreground")
            if result.entity_type
            else "",
            Div(
                result.error or "Unknown error",
                cls="text-sm text-destructive",
            ),
            cls="py-2",
        )


def UploadError(message: str) -> Div:
    """Render an upload error message."""
    return Div(
        Span(message, cls="text-destructive"),
        cls="mt-6",
    )
