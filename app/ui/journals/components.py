"""Journal UI components — status alerts, filters, and grid containers."""

from typing import Any

from fasthtml.common import H4, H5, Code, Div, Option, P, Span, Template

from core.models.enums.entity_enums import EntityStatus
from ui.components import Button, ButtonT, Card, CardBody
from ui.feedback import Alert, AlertT
from ui.forms import Input, Label, Select
from ui.patterns.skeleton import SkeletonList


def render_upload_status(
    status: str,
    message: str,
    je_input_uid: str | None = None,
    is_error: bool = False,
    status_id: str = "upload-status",
) -> Any:
    """Render upload status as HTML fragment for HTMX swap.

    ``status_id`` lets callers target a non-default swap id; ``je_input_uid`` is
    retained for the rare entry-backed status card but is ``None`` on the
    zero-persistence journal paths (ADR-073), which report a ``je_out/`` outcome
    instead.
    """
    if is_error:
        return Div(
            Alert(
                H4("Upload Failed", cls="mb-0"),
                P(message, cls="mb-0"),
                variant=AlertT.error,
            ),
            id=status_id,
        )

    return Div(
        Alert(
            H4("Done", cls="mb-0"),
            P(f"Entry: {je_input_uid}", cls="mb-0") if je_input_uid else None,
            P(message or f"Status: {status}", cls="mb-0"),
            variant=AlertT.success,
        ),
        id=status_id,
    )


def render_filters_section() -> Any:
    """Render the status filter controls card."""
    return Card(
        CardBody(
            _build_filter_form(),
        ),
        cls="bg-background shadow-xs mb-6",
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
        SkeletonList(count=3),
        id="journals-grid-container",
        cls="mt-4",
        hx_get="/journals/grid",
        hx_trigger="load",
        hx_swap="outerHTML",
    )


def render_batch_transcription_panel(
    component_name: str = "batchTranscribe",
    readonly_dirs: bool = False,
) -> Any:
    """Batch audio→text transcription panel.

    Shared between the admin console (``component_name="batchTranscribe"``,
    ``POST /api/journals/batch-transcribe``) and the user journals submit page
    (``component_name="userFolderTranscribe"``,
    ``POST /api/journals/folder-transcribe``).  Default paths and the target
    endpoint are baked into the Alpine component; only the component name
    differs between the two surfaces.

    ``readonly_dirs=True`` renders the directory paths as display-only labels
    (used by the user panel — the server-side endpoint ignores client-supplied
    paths as a security measure, so editable fields would be misleading).

    "Preview Files" lists audio files in the input directory without
    transcribing; "Transcribe All" runs Deepgram and writes ``.txt`` files to
    the output directory.
    """
    if readonly_dirs:
        input_field = Div(
            Label("Audio Input Directory"),
            Code(
                "",
                cls="block text-sm font-mono bg-muted rounded-sm px-2 py-1 mt-1",
                **{"x-text": "inputDir"},
            ),
            cls="mb-3",
        )
        output_field = Div(
            Label("Output Directory"),
            Code(
                "",
                cls="block text-sm font-mono bg-muted rounded-sm px-2 py-1 mt-1",
                **{"x-text": "outputDir"},
            ),
            P(
                "Paths are configured on the server.",
                cls="text-xs text-muted-foreground mt-1",
            ),
            cls="mb-3",
        )
    else:
        input_field = Div(
            Label("Audio Input Directory"),
            Input(type="text", id="input-dir", **{"x-model": "inputDir"}),  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
            cls="mb-3",
        )
        output_field = Div(
            Label("Output Directory"),
            Input(type="text", id="output-dir", **{"x-model": "outputDir"}),  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
            cls="mb-3",
        )

    return Div(
        Card(
            CardBody(
                H5("Directories", cls="mb-3 font-semibold"),
                input_field,
                output_field,
                Label(
                    Input(
                        type="checkbox",
                        id="skip-existing",
                        full_width=False,
                        **{"x-model": "skipExisting"},
                    ),
                    Span("Skip files already transcribed", cls="ml-2"),
                    cls="flex items-center mb-3",
                ),
                Div(
                    Button(
                        "Preview Files",
                        cls=ButtonT.secondary,
                        type="button",
                        **{
                            "@click": "previewFiles()",
                            ":disabled": "loading",
                        },  # fasthtml dynamic-attr splat
                    ),
                    Button(
                        "Transcribe All",
                        cls=(ButtonT.primary, "ml-2"),
                        type="button",
                        **{
                            "@click": "transcribeAll()",
                            ":disabled": "loading",
                        },  # fasthtml dynamic-attr splat
                    ),
                    cls="flex gap-2",
                ),
                P(
                    "Supported audio: mp3, wav, m4a, ogg, flac, webm. "
                    "Transcribed .txt files are written to the output directory.",
                    cls="text-xs text-muted-foreground mt-3",
                ),
            ),
            cls="bg-background shadow-xs mb-4",
        ),
        _render_batch_results(),
        **{"x-data": component_name},
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
