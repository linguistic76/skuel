"""Journal UI components — status alerts, filters, and grid containers."""

from typing import Any

from fasthtml.common import H4, H5, Div, Option, P, Textarea

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.user_entry_enums import EnrichmentMode
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


def render_batch_directories_card() -> Any:
    """Render the batch operations directories card."""
    return Card(
        CardBody(
            H5("Directories", cls="mb-3 font-semibold"),
            Div(
                Label("Audio Input Directory"),
                Input(type="text", id="input-dir", value="data/je_inputs"),
                cls="mb-3",
            ),
            Div(
                Label("Output Directory"),
                Input(type="text", id="output-dir", value="data/je_outputs"),
                cls="mb-3",
            ),
            Div(
                Button(
                    "Preview Files",
                    variant=ButtonT.outline,
                    type="button",
                    id="preview-btn",
                ),
                Button(
                    "Transcribe All",
                    variant=ButtonT.primary,
                    type="button",
                    id="transcribe-btn",
                    cls="ml-2",
                ),
                cls="flex gap-2",
            ),
        ),
        cls="bg-background shadow-sm mb-4",
    )


def render_batch_processing_card() -> Any:
    """Render the batch LLM processing options card."""
    return Card(
        CardBody(
            H5("LLM Processing Options", cls="mb-3 font-semibold"),
            Div(
                Label("Enrichment Mode"),
                Select(
                    Option(
                        "Activity Tracking",
                        value=EnrichmentMode.ACTIVITY_TRACKING.value,
                        selected=True,
                    ),
                    Option("Idea Articulation", value=EnrichmentMode.IDEA_ARTICULATION.value),
                    Option("Critical Thinking", value=EnrichmentMode.CRITICAL_THINKING.value),
                    id="enrichment-mode",
                    name="enrichment_mode",
                ),
                cls="mb-3",
            ),
            Div(
                Label("Model"),
                Select(
                    Option("GPT-4o Mini", value="gpt-4o-mini", selected=True),
                    Option("GPT-4o", value="gpt-4o"),
                    id="llm-model",
                    name="model",
                ),
                cls="mb-3",
            ),
            Div(
                Label("Custom Instructions (optional — overrides mode)"),
                Textarea(
                    id="custom-instructions",
                    name="custom_instructions",
                    rows="3",
                    placeholder="Leave blank to use the enrichment mode template",
                    cls="w-full",
                ),
                cls="mb-3",
            ),
            Div(
                Button(
                    "Process Transcripts",
                    variant=ButtonT.outline,
                    type="button",
                    id="process-btn",
                ),
                Button(
                    "Transcribe + Process",
                    variant=ButtonT.primary,
                    type="button",
                    id="combined-btn",
                    cls="ml-2",
                ),
                cls="flex gap-2",
            ),
        ),
        cls="bg-background shadow-sm mb-4",
    )
