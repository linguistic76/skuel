"""Journal UI components — status alerts, filters, and grid containers."""

from typing import Any

from fasthtml.common import H4, H5, Div, Option, P, Span, Template

from core.models.enums.entity_enums import EntityStatus
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Alert, AlertT
from ui.forms import Input, Label, Select
from ui.layout import Size


def render_upload_status(
    status: str,
    message: str,
    je_input_uid: str | None = None,
    is_error: bool = False,
) -> Any:
    """Render upload status as HTML fragment for HTMX swap."""
    if is_error:
        return Div(
            Alert(
                H4("Upload Failed", cls="mb-0"),
                P(message, cls="mb-0"),
                variant=AlertT.error,
            ),
            id="upload-status",
        )

    return Div(
        Alert(
            H4("Submitted to AI", cls="mb-0"),
            P(f"Entry: {je_input_uid}", cls="mb-0") if je_input_uid else None,
            P(f"Status: {status}", cls="mb-0"),
            ButtonLink(
                "Browse Journals",
                href="/journals/browse",
                variant=ButtonT.ghost,
                size=Size.sm,
                cls="mt-2",
            )
            if je_input_uid
            else None,
            variant=AlertT.success,
        ),
        id="upload-status",
    )


def render_filters_section() -> Any:
    """Render the status filter controls card."""
    return Card(
        CardBody(
            _build_filter_form(),
        ),
        cls="bg-background shadow-sm mb-6",
    )


def _build_filter_form() -> Any:
    """Build the filter form element."""
    from fasthtml.common import Form

    return Form(
        Div(
            Label("Status"),
            Select(
                Option("All Status", value="", selected=True),
                Option("Submitted", value=EntityStatus.SUBMITTED.value),
                Option("Queued", value=EntityStatus.QUEUED.value),
                Option("Processing", value=EntityStatus.PROCESSING.value),
                Option("Completed", value=EntityStatus.COMPLETED.value),
                Option("Failed", value=EntityStatus.FAILED.value),
                name="status",
            ),
            cls="mb-2",
        ),
        hx_get="/journals/grid",
        hx_target="#journals-grid-container",
        hx_swap="outerHTML",
        hx_trigger="change from:select",
        id="filter-form",
    )


def render_journals_grid_container() -> Any:
    """Render the HTMX-loading journals grid container."""
    return Div(
        P("Loading journals...", cls="text-center text-muted-foreground"),
        id="journals-grid-container",
        cls="mt-4",
        hx_get="/journals/grid",
        hx_trigger="load",
        hx_swap="outerHTML",
    )


def render_batch_transcription_panel() -> Any:
    """Admin batch audio→text transcription panel.

    Alpine-driven (``batchTranscribe`` in static/js/skuel.js): drives
    ``POST /api/journals/batch-transcribe``. "Preview Files" lists the audio
    files in the server-side input directory without transcribing; "Transcribe
    All" runs Deepgram over them and writes ``.txt`` files to the output
    directory. Operates on server-side paths — not browser-picked files.
    """
    return Div(
        Card(
            CardBody(
                H5("Directories", cls="mb-3 font-semibold"),
                Div(
                    Label("Audio Input Directory"),
                    Input(type="text", id="input-dir", **{"x-model": "inputDir"}),  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
                    cls="mb-3",
                ),
                Div(
                    Label("Output Directory"),
                    Input(type="text", id="output-dir", **{"x-model": "outputDir"}),  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
                    cls="mb-3",
                ),
                Label(
                    Input(
                        type="checkbox",
                        id="skip-existing",
                        full_width=False,
                        **{"x-model": "skipExisting"},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
                    ),
                    Span("Skip files already transcribed", cls="ml-2"),
                    cls="flex items-center mb-3",
                ),
                Div(
                    Button(
                        "Preview Files",
                        variant=ButtonT.outline,
                        type="button",
                        id="preview-btn",
                        **{"@click": "previewFiles()", ":disabled": "loading"},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
                    ),
                    Button(
                        "Transcribe All",
                        variant=ButtonT.primary,
                        type="button",
                        id="transcribe-btn",
                        cls="ml-2",
                        **{"@click": "transcribeAll()", ":disabled": "loading"},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
                    ),
                    cls="flex gap-2",
                ),
                P(
                    "Supported audio: mp3, wav, m4a, ogg, flac, webm. "
                    "Runs against the server-side directory above.",
                    cls="text-xs text-muted-foreground mt-3",
                ),
            ),
            cls="bg-background shadow-sm mb-4",
        ),
        _render_batch_results(),
        **{"x-data": "batchTranscribe"},
    )


def _render_batch_results() -> Any:
    """Alpine-bound results region for the batch transcription panel."""
    return Div(
        P(
            "Working…",
            cls="text-sm text-muted-foreground",
            **{"x-show": "loading"},
        ),
        Div(
            Alert(P("", cls="mb-0", **{"x-text": "error"}), variant=AlertT.error),
            cls="mb-4",
            **{"x-show": "error", "x-cloak": True},
        ),
        # Preview: file list without transcribing
        Div(
            H5("Preview", cls="font-semibold mb-2"),
            P("", cls="text-sm mb-2", **{"x-text": "previewSummary()"}),
            Template(
                Div(
                    Span("", **{"x-text": "f.name"}),
                    Span(
                        "",
                        cls="text-muted-foreground ml-2",
                        **{"x-text": "'(' + f.size_mb + ' MB)'"},
                    ),
                    cls="text-sm",
                ),
                # Null-safe: Alpine evaluates x-for at init even under a falsy
                # ancestor x-show, and preview/result start null.
                **{"x-for": "f in (preview && preview.files) || []", ":key": "f.name"},
            ),
            cls="mb-4",
            **{"x-show": "preview", "x-cloak": True},
        ),
        # Transcribe: aggregate result + per-file errors
        Div(
            H5("Transcription Result", cls="font-semibold mb-2"),
            P("", cls="text-sm mb-2", **{"x-text": "resultSummary()"}),
            Div(
                H5("Errors", cls="font-semibold text-destructive mb-1 text-sm"),
                Template(
                    P(
                        Span("", cls="font-medium", **{"x-text": "e.name"}),
                        Span(
                            "",
                            cls="text-muted-foreground",
                            **{"x-text": "': ' + e.error"},
                        ),
                        cls="text-sm",
                    ),
                    **{"x-for": "e in (result && result.errors) || []", ":key": "e.name"},
                ),
                **{"x-show": "result && result.errors && result.errors.length"},
            ),
            **{"x-show": "result", "x-cloak": True},
        ),
        cls="mt-4",
    )
