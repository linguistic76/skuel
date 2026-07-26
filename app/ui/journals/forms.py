"""Journal upload form — redesigned capture surface.

Layout: Processing → Source → Browse area → Process footer.
Replaces: drag-and-drop zone (removed by design), MODE selector (removed by design),
"Watch folder" renamed to "Upload Folder" (now client-side upload, not server folder).
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Button as RawButton
from fasthtml.common import Div, Form, Input, Label, P, Script, Span

from core.models.enums.pipeline import ProcessingMode
from ui.components import Icon
from ui.primitives import dropdown_menu, primary_btn, section_label

# Keyed by the enum so a new ProcessingMode member cannot ship without a card
# here (enforced by tests/unit/ui/test_journals_form_modes.py).
_MODE_CONFIGS: dict[ProcessingMode, dict[str, str]] = {
    ProcessingMode.TRANSCRIBE_ONLY: {
        "icon": "mic",
        "title": "Transcribe only",
        "desc": "Convert audio or media to text",
    },
    ProcessingMode.TRANSCRIBE_AND_INSTRUCTIONS: {
        "icon": "sparkles",
        "title": "Transcribe + Instructions",
        "desc": "Transcribe audio then apply processing instructions",
    },
    ProcessingMode.INSTRUCTIONS_ONLY: {
        "icon": "file-text",
        "title": "Instructions only",
        "desc": "Apply instructions to an existing text file",
    },
}


# ---------------------------------------------------------------------------
# Processing section
# ---------------------------------------------------------------------------


def _build_processing_section() -> Any:
    """Full-width trigger showing the current processing mode + dropdown."""
    mode_spans = []
    for mode_key, cfg in _MODE_CONFIGS.items():
        is_default = mode_key == ProcessingMode.default()
        mode_spans.append(
            Span(
                Span(
                    Icon(cfg["icon"], cls="w-[22px] h-[22px]"),
                    cls=(
                        "w-12 h-12 flex-none rounded-xl bg-muted flex items-center justify-center"
                    ),
                ),
                Span(
                    Span(cfg["title"], cls="block text-[18px] font-bold"),
                    Span(cfg["desc"], cls="block text-[15px] text-muted-foreground mt-0.5"),
                    cls="flex-1 min-w-0",
                ),
                cls="flex items-center gap-[18px] flex-1 min-w-0",
                **{"x-show": f"processingMode === '{mode_key.value}'"},
                **({} if is_default else {"x-cloak": True}),  # boundary: fasthtml-elements
            )
        )

    trigger = RawButton(
        *mode_spans,
        Icon("chevron-down", cls="w-5 h-5 text-muted-foreground"),
        type="button",
        cls=(
            "w-full flex items-center gap-[18px] px-5 py-[18px] border border-border "
            "rounded-xl bg-card hover:bg-muted/60 text-left cursor-pointer"
        ),
        **{"@click": "modeMenuOpen = !modeMenuOpen"},  # boundary: fasthtml-elements
    )

    option_rows = []
    for mode_key, cfg in _MODE_CONFIGS.items():
        option_rows.append(
            RawButton(
                Span(
                    Icon(cfg["icon"], cls="w-[18px] h-[18px]"),
                    cls="w-8 h-8 flex-none rounded-lg bg-muted flex items-center justify-center",
                ),
                Span(
                    Span(cfg["title"], cls="block text-[14px] font-semibold text-foreground"),
                    Span(
                        cfg["desc"],
                        cls="block text-[12.5px] text-muted-foreground mt-0.5",
                    ),
                    cls="flex-1 min-w-0",
                ),
                Span(
                    Icon("check", cls="w-4 h-4 text-primary"),
                    **{
                        "x-show": f"processingMode === '{mode_key.value}'",
                        "x-cloak": True,  # boundary: fasthtml-elements
                    },
                ),
                type="button",
                cls=(
                    "w-full flex items-center gap-3 p-3 rounded-[9px] text-left "
                    "cursor-pointer border-0 font-[inherit] transition-colors"
                ),
                **{
                    "@click": f"selectMode('{mode_key.value}')",  # boundary: fasthtml-elements
                    ":class": (
                        f"processingMode === '{mode_key.value}' "
                        "? 'bg-muted' : 'bg-transparent hover:bg-muted/50'"
                    ),
                },
            )
        )

    menu = dropdown_menu(
        *option_rows,
        **{
            "x-show": "modeMenuOpen",
            "x-cloak": True,  # type: ignore[arg-type]  # boundary: fasthtml-elements
            "@click.outside": "modeMenuOpen = false",
        },
    )

    return Div(
        section_label("Processing"),
        Div(trigger, menu, cls="relative"),
        cls="mb-5",
    )


# ---------------------------------------------------------------------------
# Source segmented control
# ---------------------------------------------------------------------------


def _build_source_section() -> Any:
    """Two-tab segmented control: Upload files / Upload Folder."""

    def _tab(label: str, icon: str, value: str) -> Any:
        return RawButton(
            Icon(icon, cls="w-[18px] h-[18px]"),
            Span(label),
            type="button",
            cls=(
                "flex items-center justify-center gap-2.5 px-3 py-3 rounded-lg "
                "text-[16px] font-semibold whitespace-nowrap transition-colors "
                "cursor-pointer border-0 font-[inherit]"
            ),
            **{
                "@click": f"source = '{value}'",  # boundary: fasthtml-elements
                ":aria-pressed": f"source === '{value}'",
                ":class": (
                    f"source === '{value}' "
                    "? 'bg-primary text-primary-foreground shadow-[0_1px_2px_rgba(0,0,0,0.08)]' "
                    ": 'text-muted-foreground'"
                ),
            },
        )

    return Div(
        section_label("Source"),
        Div(
            _tab("Upload files", "file-up", "files"),
            _tab("Upload Folder", "folder-up", "folder"),
            cls="grid grid-cols-2 gap-1.5 p-1.5 bg-muted rounded-xl",
        ),
        cls="mb-4",
    )


# ---------------------------------------------------------------------------
# Browse area
# ---------------------------------------------------------------------------


def _build_browse_area() -> Any:
    """Centered browse badge + browse button + helper text (no drag-and-drop)."""
    return Div(
        Div(
            # Icon badge — swaps with active source tab
            Span(
                Span(
                    Icon("file-up", cls="w-[26px] h-[26px]"),
                    **{"x-show": "source !== 'folder'"},
                ),
                Span(
                    Icon("folder-up", cls="w-[26px] h-[26px]"),
                    **{
                        "x-show": "source === 'folder'",
                        "x-cloak": True,  # boundary: fasthtml-elements
                    },
                ),
                cls=(
                    "w-[60px] h-[60px] rounded-[14px] bg-card border border-border "
                    "flex items-center justify-center shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
                ),
            ),
            # Browse button — triggers appropriate hidden file input
            RawButton(
                Icon("folder-open", cls="w-[19px] h-[19px]"),
                Span("Browse "),
                Span("", **{"x-text": "source === 'folder' ? 'folder' : 'files'"}),
                type="button",
                cls=(
                    "inline-flex items-center gap-2.5 px-7 py-3.5 rounded-[11px] "
                    "bg-primary text-primary-foreground text-[17px] font-bold tracking-tight "
                    "whitespace-nowrap hover:opacity-90 cursor-pointer border-0 font-[inherit]"
                ),
                **{"@click": "openPicker()"},  # boundary: fasthtml-elements
            ),
            # File-count confirmation
            P(
                "",
                cls="text-sm text-primary font-medium",
                **{
                    "x-show": "fileCount > 0",
                    "x-cloak": True,  # boundary: fasthtml-elements
                    "x-text": "fileCount + (fileCount === 1 ? ' file selected' : ' files selected')",
                },
            ),
            P("audio, text, PDF, images, video", cls="text-sm text-muted-foreground"),
            cls="flex flex-col items-center text-center gap-3 px-6 py-6",
        ),
        cls="bg-muted/50 border border-border rounded-2xl mb-5",
    )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------


def _build_footer() -> Any:
    """Card footer — file-size limit and Process submit button."""
    return Div(
        P("Up to 100 MB per file.", cls="text-[15px] text-muted-foreground"),
        primary_btn("Process", icon="send", type="submit"),
        cls="border-t border-border pt-[22px] flex items-center justify-between",
    )


def _build_summon_toggle(field_name: str, label: str, *, compact: bool = False) -> Any:
    """FOUNDER-only grounding checkbox for the file compile (shared shape).

    The file path has no per-stage review gate, so the grounding dials ride the
    upload form here. Shown only in ``instructions_only`` mode with a single
    file selected (``fileCount <= 1``) — the sole upload shape that reaches the
    FOUNDER DNWF compile (``run_compiled``). A multi-file / folder upload takes
    the batch path (``JournalBatchService.run_batch_over_dir``), which never reaches
    ``run_compiled``, so the toggle hides itself rather than submit a flag the
    server would silently ignore. Unchecked → the field is omitted and the
    compile is ungrounded (default). Rendered ONLY when the caller is FOUNDER.
    Mirrors the review-gate checkboxes on the interactive stages.
    """
    supported = f"processingMode === '{ProcessingMode.INSTRUCTIONS_ONLY.value}' && fileCount <= 1"
    return Label(
        Input(
            type="checkbox",
            name=field_name,
            value="true",
            cls="mr-2 align-middle",
            # Disable (not just hide) when unsupported: a display:none checkbox
            # still POSTs its value, so a box checked then invalidated by adding
            # files would leak the flag onto the ignored batch path.
            # Same x-show + :disabled pairing the file inputs above use.
            **{":disabled": f"!({supported})"},  # boundary: fasthtml-elements
        ),
        label,
        cls=(
            "flex items-center text-sm text-muted-foreground cursor-pointer "
            + ("mt-3" if compact else "mb-1")
        ),
        **{
            "x-show": supported,
            "x-cloak": True,  # boundary: fasthtml-elements
        },
    )


def _build_canon_toggle(*, compact: bool = False) -> Any:
    """The "Summon the canon shelf" dial (curated books — ADR-076)."""
    return _build_summon_toggle("summon_canon", "Summon the canon shelf", compact=compact)


def _build_vault_toggle(*, compact: bool = False) -> Any:
    """The "Draw on my vault" dial (own non-private notes — canon P3)."""
    return _build_summon_toggle("summon_vault", "Draw on my vault", compact=compact)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------


def render_upload_form(exercises: list[Any] | None = None, *, is_founder: bool = False) -> Any:
    """Render journal capture form — Processing → Source → Browse → Process.

    Args:
        exercises: Unused — kept for call-site compatibility.
        is_founder: Whether the caller is a FOUNDER — gates the canon "summon"
            checkbox (file-path parity with the interactive stage dial).
    """
    alpine_data = """{
        source: 'files',
        processingMode: 'transcribe_only',
        modeMenuOpen: false,
        fileCount: 0,

        handleFileSelect(event) {
            this.fileCount = event.target.files.length;
        },

        openPicker() {
            const id = this.source === 'folder' ? 'folder-input' : 'file-input';
            const el = document.getElementById(id);
            if (el) el.click();
        },

        selectMode(mode) {
            this.processingMode = mode;
            this.modeMenuOpen = false;
        },
    }"""

    return Div(
        # Capture card
        Div(
            Form(
                # Hidden form state bindings
                Input(
                    type="hidden",
                    name="processing_mode",
                    **{"x-bind:value": "processingMode"},  # boundary: fasthtml-elements
                ),
                Input(type="hidden", name="instruction_filename", value=""),
                Input(type="hidden", name="instruction_content", value=""),
                # File picker — standard multi-file
                Input(
                    type="file",
                    name="file",
                    id="file-input",
                    multiple=True,
                    accept="audio/*,text/*,.pdf,.doc,.docx,image/*,video/*",
                    cls="hidden",
                    **{
                        "x-show": "source === 'files'",
                        ":disabled": "source !== 'files'",  # boundary: fasthtml-elements
                        "x-on:change": "handleFileSelect($event)",  # boundary: fasthtml-elements
                    },
                ),
                # Folder picker — webkitdirectory for local folder upload
                Input(
                    type="file",
                    name="file",
                    id="folder-input",
                    multiple=True,
                    webkitdirectory="",
                    cls="hidden",
                    **{
                        "x-show": "source === 'folder'",
                        ":disabled": "source !== 'folder'",  # boundary: fasthtml-elements
                        "x-on:change": "handleFileSelect($event)",  # boundary: fasthtml-elements
                    },
                ),
                _build_processing_section(),
                _build_source_section(),
                _build_browse_area(),
                *([_build_canon_toggle(), _build_vault_toggle()] if is_founder else []),
                _build_footer(),
                hx_post="/journals/upload",
                hx_target="#upload-status",
                hx_swap="outerHTML",
                hx_encoding="multipart/form-data",
                id="upload-form",
                **{
                    "@journals:upload-complete.window": "fileCount = 0"  # boundary: fasthtml-elements
                },
            ),
            cls=(
                "max-w-[840px] mx-auto bg-card border border-border rounded-2xl "
                "shadow-[0_1px_3px_rgba(0,0,0,0.04)] px-10 py-7"
            ),
        ),
        # HTMX swap target — below the card
        Div(id="upload-status", cls="mt-4 max-w-[840px] mx-auto"),
        **{"x-data": alpine_data},
    )


# ---------------------------------------------------------------------------
# Compact right-panel variants (for /journals landing 3-column layout)
# ---------------------------------------------------------------------------


def _build_compact_processing_section() -> Any:
    """Compact processing mode selector for the 320px right panel."""
    mode_spans = []
    for mode_key, cfg in _MODE_CONFIGS.items():
        is_default = mode_key == ProcessingMode.default()
        mode_spans.append(
            Span(
                Span(
                    Icon(cfg["icon"], cls="w-[18px] h-[18px]"),
                    cls="w-9 h-9 flex-none rounded-lg bg-muted flex items-center justify-center",
                ),
                Span(
                    Span(cfg["title"], cls="block text-[14px] font-semibold"),
                    Span(cfg["desc"], cls="block text-[12px] text-muted-foreground mt-0.5"),
                    cls="flex-1 min-w-0",
                ),
                cls="flex items-center gap-3 flex-1 min-w-0",
                **{"x-show": f"processingMode === '{mode_key.value}'"},
                **({} if is_default else {"x-cloak": True}),  # boundary: fasthtml-elements
            )
        )

    trigger = RawButton(
        *mode_spans,
        Icon("chevron-down", cls="w-4 h-4 text-muted-foreground"),
        type="button",
        cls=(
            "w-full flex items-center gap-3 px-3 py-3 border border-border "
            "rounded-xl bg-card hover:bg-muted/60 text-left cursor-pointer"
        ),
        **{"@click": "modeMenuOpen = !modeMenuOpen"},  # boundary: fasthtml-elements
    )

    option_rows = []
    for mode_key, cfg in _MODE_CONFIGS.items():
        option_rows.append(
            RawButton(
                Span(
                    Icon(cfg["icon"], cls="w-4 h-4"),
                    cls="w-7 h-7 flex-none rounded-md bg-muted flex items-center justify-center",
                ),
                Span(
                    Span(cfg["title"], cls="block text-[13px] font-semibold text-foreground"),
                    Span(cfg["desc"], cls="block text-[11.5px] text-muted-foreground mt-0.5"),
                    cls="flex-1 min-w-0",
                ),
                Span(
                    Icon("check", cls="w-3.5 h-3.5 text-primary"),
                    **{
                        "x-show": f"processingMode === '{mode_key.value}'",
                        "x-cloak": True,  # boundary: fasthtml-elements
                    },
                ),
                type="button",
                cls=(
                    "w-full flex items-center gap-2.5 p-2.5 rounded-[9px] text-left "
                    "cursor-pointer border-0 font-[inherit] transition-colors"
                ),
                **{
                    "@click": f"selectMode('{mode_key.value}')",  # boundary: fasthtml-elements
                    ":class": (
                        f"processingMode === '{mode_key.value}' "
                        "? 'bg-muted' : 'bg-transparent hover:bg-muted/50'"
                    ),
                },
            )
        )

    menu = dropdown_menu(
        *option_rows,
        **{
            "x-show": "modeMenuOpen",
            "x-cloak": True,  # type: ignore[arg-type]  # boundary: fasthtml-elements
            "@click.outside": "modeMenuOpen = false",
        },
    )

    return Div(
        section_label("Processing"),
        Div(trigger, menu, cls="relative"),
        cls="mb-4",
    )


def _build_compact_source_section() -> Any:
    """Compact two-tab source selector for the right panel."""

    def _tab(label: str, icon: str, value: str) -> Any:
        return RawButton(
            Icon(icon, cls="w-4 h-4"),
            Span(label),
            type="button",
            cls=(
                "flex items-center justify-center gap-2 px-2 py-2 rounded-lg "
                "text-[14px] font-medium whitespace-nowrap transition-colors "
                "cursor-pointer border-0 font-[inherit]"
            ),
            **{
                "@click": f"source = '{value}'",  # boundary: fasthtml-elements
                ":aria-pressed": f"source === '{value}'",
                ":class": (
                    f"source === '{value}' "
                    "? 'bg-primary text-primary-foreground shadow-[0_1px_2px_rgba(0,0,0,0.08)]' "
                    ": 'text-muted-foreground'"
                ),
            },
        )

    return Div(
        section_label("Source"),
        Div(
            _tab("Upload files", "file-up", "files"),
            _tab("Upload Folder", "folder-up", "folder"),
            cls="grid grid-cols-2 gap-1 p-1 bg-muted rounded-xl",
        ),
        cls="mb-4",
    )


def _build_compact_browse_area() -> Any:
    """Compact browse area for the right panel."""
    return Div(
        Div(
            Span(
                Span(
                    Icon("file-up", cls="w-[20px] h-[20px]"),
                    **{"x-show": "source !== 'folder'"},
                ),
                Span(
                    Icon("folder-up", cls="w-[20px] h-[20px]"),
                    **{
                        "x-show": "source === 'folder'",
                        "x-cloak": True,  # boundary: fasthtml-elements
                    },
                ),
                cls=(
                    "w-[44px] h-[44px] rounded-[12px] bg-card border border-border "
                    "flex items-center justify-center shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
                ),
            ),
            RawButton(
                Icon("folder-open", cls="w-4 h-4"),
                Span("Browse "),
                Span("", **{"x-text": "source === 'folder' ? 'folder' : 'files'"}),
                type="button",
                cls=(
                    "inline-flex items-center gap-2 px-5 py-2.5 rounded-[11px] "
                    "bg-primary text-primary-foreground text-[15px] font-semibold tracking-tight "
                    "whitespace-nowrap hover:opacity-90 cursor-pointer border-0 font-[inherit]"
                ),
                **{"@click": "openPicker()"},  # boundary: fasthtml-elements
            ),
            P(
                "",
                cls="text-xs text-primary font-medium",
                **{
                    "x-show": "fileCount > 0",
                    "x-cloak": True,  # boundary: fasthtml-elements
                    "x-text": "fileCount + (fileCount === 1 ? ' file selected' : ' files selected')",
                },
            ),
            P("audio, text, PDF, images, video", cls="text-xs text-muted-foreground"),
            cls="flex flex-col items-center text-center gap-2.5 px-4 py-5",
        ),
        cls="bg-muted/50 border border-border rounded-2xl mb-4",
    )


def _build_compact_process_btn() -> Any:
    """Full-width Process button for the right panel."""
    return primary_btn("Process", icon="send", type="submit", cls="w-full justify-center")


def render_right_panel(*, is_founder: bool = False) -> Any:
    """Compact upload panel for the 320px right column on /journals landing.

    Shares DOM IDs (upload-form, upload-status, file-input, folder-input) with
    render_upload_form() so upload_form_script() works without changes. Only one
    of these two forms will be present on any given page.

    Args:
        is_founder: Whether the caller is a FOUNDER — gates the canon "summon"
            checkbox (shown only in ``instructions_only`` mode).
    """
    alpine_data = """{
        source: 'files',
        processingMode: 'transcribe_only',
        modeMenuOpen: false,
        fileCount: 0,

        handleFileSelect(event) {
            this.fileCount = event.target.files.length;
        },

        openPicker() {
            const id = this.source === 'folder' ? 'folder-input' : 'file-input';
            const el = document.getElementById(id);
            if (el) el.click();
        },

        selectMode(mode) {
            this.processingMode = mode;
            this.modeMenuOpen = false;
        },
    }"""

    return Div(
        Form(
            Input(
                type="hidden",
                name="processing_mode",
                **{"x-bind:value": "processingMode"},  # boundary: fasthtml-elements
            ),
            Input(type="hidden", name="instruction_filename", value=""),
            Input(type="hidden", name="instruction_content", value=""),
            Input(
                type="file",
                name="file",
                id="file-input",
                multiple=True,
                accept="audio/*,text/*,.pdf,.doc,.docx,image/*,video/*",
                cls="hidden",
                **{
                    "x-show": "source === 'files'",
                    ":disabled": "source !== 'files'",  # boundary: fasthtml-elements
                    "x-on:change": "handleFileSelect($event)",  # boundary: fasthtml-elements
                },
            ),
            Input(
                type="file",
                name="file",
                id="folder-input",
                multiple=True,
                webkitdirectory="",
                cls="hidden",
                **{
                    "x-show": "source === 'folder'",
                    ":disabled": "source !== 'folder'",  # boundary: fasthtml-elements
                    "x-on:change": "handleFileSelect($event)",  # boundary: fasthtml-elements
                },
            ),
            _build_compact_processing_section(),
            _build_compact_source_section(),
            _build_compact_browse_area(),
            *(
                [_build_canon_toggle(compact=True), _build_vault_toggle(compact=True)]
                if is_founder
                else []
            ),
            _build_compact_process_btn(),
            # Signals that this layout has a #journal-workspace (landing centre
            # column), so a successful single-file upload should retarget its
            # result there. The /submissions/journal form omits this and keeps
            # its result in #upload-status (ADR-073; Codex #478).
            Input(type="hidden", name="workspace_target", value="1"),
            hx_post="/journals/upload",
            hx_target="#upload-status",
            hx_swap="outerHTML",
            hx_encoding="multipart/form-data",
            id="upload-form",
            **{"@journals:upload-complete.window": "fileCount = 0"},  # boundary: fasthtml-elements
        ),
        Div(id="upload-status", cls="mt-3"),
        **{"x-data": alpine_data},
    )


def upload_form_script() -> Any:
    """HTMX event handlers for the journal upload form (static/js/journals-upload.js)."""
    return Script(src="/static/js/journals-upload.js")
