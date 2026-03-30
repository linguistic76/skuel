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
        Span(f"{batch.successful} succeeded", cls="uk-text-success uk-text-bold"),
        " / " if batch.failed > 0 else "",
        Span(f"{batch.failed} failed", cls="uk-text-danger uk-text-bold")
        if batch.failed > 0
        else "",
        f" — {batch.total} file{'s' if batch.total != 1 else ''} processed",
        cls="uk-margin-small-bottom",
    )

    # Per-file results
    items = [_file_result_item(r) for r in batch.results]

    return Div(
        summary,
        Ul(*items, cls="uk-list uk-list-divider uk-margin-small-top"),
        cls="uk-margin-medium-top",
    )


def _file_result_item(result: FileUploadResult) -> Li:
    """Render a single file result as a list item."""
    if result.success:
        return Li(
            Span(result.filename, cls="uk-text-bold"),
            Span(f" [{result.entity_type}]", cls="uk-text-muted") if result.entity_type else "",
            Span(f" → {result.uid}", cls="uk-text-small uk-text-muted") if result.uid else "",
            cls="uk-text-success",
        )
    else:
        return Li(
            Span(result.filename, cls="uk-text-bold"),
            Span(f" [{result.entity_type}]", cls="uk-text-muted") if result.entity_type else "",
            Div(
                result.error or "Unknown error",
                cls="uk-text-small uk-text-danger",
            ),
        )


def UploadError(message: str) -> Div:
    """Render an upload error message."""
    return Div(
        Span(message, cls="uk-text-danger"),
        cls="uk-margin-medium-top",
    )
