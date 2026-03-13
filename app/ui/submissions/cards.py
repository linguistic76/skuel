"""
Submission Card Components
==========================

Card renderers for submission lists, grids, and detail views.
"""

from typing import Any

from fasthtml.common import H4, A, Div, P

from ui.feedback import Badge, get_submission_status_badge_class

_get_status_badge_class = get_submission_status_badge_class


def get_submission_identifier(submission: Any) -> str:
    """Extract the identifier from submission metadata, falling back to report_type."""
    metadata = getattr(submission, "metadata", None)
    if isinstance(metadata, dict):
        identifier = metadata.get("identifier")
        if identifier:
            return str(identifier)
    return getattr(submission, "report_type", "unknown")


def render_submission_card(submission: Any, is_pinned: bool = False) -> Any:
    """Render a single submission card."""
    from ui.patterns.pin_button import PinButton

    file_size_mb = (submission.file_size / 1024 / 1024) if submission.file_size else 0
    identifier = get_submission_identifier(submission)
    return Div(
        Div(
            Div(
                Div(
                    H4(submission.original_filename, cls="mb-0 font-semibold"),
                    P(
                        f"{identifier} \u2022 {file_size_mb:.2f} MB",
                        cls="text-sm text-muted-foreground mb-0",
                    ),
                    cls="flex-1",
                ),
                Div(
                    Badge(
                        submission.status,
                        variant=None,
                        cls=_get_status_badge_class(submission.status),
                    ),
                ),
                Div(
                    PinButton(entity_uid=submission.uid, is_pinned=is_pinned, size="xs"),
                    A(
                        "View",
                        href=f"/submissions/{submission.uid}",
                        cls="btn btn-sm btn-ghost",
                    ),
                    cls="flex gap-2",
                ),
                cls="flex items-center gap-4",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-background shadow-sm mb-2",
    )


def render_submissions_grid(submissions: list[Any]) -> Any:
    """Render submissions grid as HTML fragment for HTMX swap."""
    if not submissions:
        return Div(
            P("No submissions found.", cls="text-center text-muted-foreground"),
            id="submissions-grid-container",
        )

    return Div(
        *[render_submission_card(a) for a in submissions],
        id="submissions-grid-container",
    )


def render_submission_detail(submission: Any) -> Any:
    """Render submission detail info as HTML fragment."""
    file_size_mb = (submission.file_size / 1024 / 1024) if submission.file_size else 0
    processing_duration = getattr(submission, "processing_duration_seconds", None)
    created_at = getattr(submission, "created_at", None)
    identifier = get_submission_identifier(submission)

    return Div(
        Div(
            Div(
                P("Filename", cls="text-xs text-muted-foreground mb-0"),
                P(submission.original_filename, cls="mb-0 font-bold"),
            ),
            Div(
                P("Identifier", cls="text-xs text-muted-foreground mb-0"),
                P(identifier, cls="mb-0 font-semibold"),
            ),
            Div(
                P("Status", cls="text-xs text-muted-foreground mb-0"),
                P(
                    Badge(
                        submission.status,
                        variant=None,
                        cls=_get_status_badge_class(submission.status),
                    ),
                    cls="mb-0",
                ),
            ),
            Div(
                P("File Size", cls="text-xs text-muted-foreground mb-0"),
                P(f"{file_size_mb:.2f} MB", cls="mb-0"),
            ),
            Div(
                P("Processing Duration", cls="text-xs text-muted-foreground mb-0"),
                P(f"{processing_duration or 'N/A'} seconds", cls="mb-0"),
            ),
            Div(
                P("Created", cls="text-xs text-muted-foreground mb-0"),
                P(str(created_at) if created_at else "N/A", cls="mb-0"),
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
        id="submission-info",
    )


def render_upload_status(
    status: str,
    message: str,
    submission_uid: str | None = None,
    is_error: bool = False,
) -> Any:
    """Render upload status as HTML fragment for HTMX swap."""
    if is_error:
        return Div(
            Div(
                H4("Upload Failed", cls="mb-0"),
                P(message, cls="mb-0"),
                cls="alert alert-error",
            ),
            id="upload-status",
        )

    return Div(
        Div(
            H4("File Uploaded Successfully!", cls="mb-0"),
            P(f"Submission ID: {submission_uid}", cls="mb-0") if submission_uid else None,
            P(f"Status: {status}", cls="mb-0"),
            cls="alert alert-success",
        ),
        id="upload-status",
    )


def render_processed_content(content: str | None, has_content: bool) -> Any:
    """Render processed content as HTML fragment."""
    if not has_content or not content:
        return Div(
            P("No processed content available.", cls="text-muted-foreground"),
            id="processed-content",
            cls="p-4 bg-muted rounded-lg",
        )

    return Div(
        Div(content, cls="text-sm", style="white-space: pre-wrap"),
        id="processed-content",
        cls="p-4 bg-muted rounded-lg",
        style="max-height: 600px; overflow-y: auto;",
    )
