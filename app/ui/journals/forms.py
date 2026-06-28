"""Journal upload form — redesigned capture surface.

Layout: Processing → Source → Browse area → Process footer.
Replaces: drag-and-drop zone (removed by design), MODE selector (removed by design),
"Watch folder" renamed to "Upload Folder" (now client-side upload, not server folder).
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Button as RawButton
from fasthtml.common import Div, Form, Input, NotStr, P, Script, Span
from monsterui.franken import UkIcon

from ui.primitives import dropdown_menu, primary_btn, section_label

_MODE_CONFIGS: dict[str, dict[str, str]] = {
    "transcribe_only": {
        "icon": "mic",
        "title": "Transcribe only",
        "desc": "Convert audio or media to text",
    },
    "transcribe_and_instructions": {
        "icon": "sparkles",
        "title": "Transcribe + Instructions",
        "desc": "Transcribe audio then apply processing instructions",
    },
    "instructions_only": {
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
        is_default = mode_key == "transcribe_only"
        mode_spans.append(
            Span(
                Span(
                    UkIcon(cfg["icon"], cls="w-[22px] h-[22px]"),
                    cls=(
                        "w-12 h-12 flex-none rounded-xl bg-muted "
                        "flex items-center justify-center"
                    ),
                ),
                Span(
                    Span(cfg["title"], cls="block text-[18px] font-bold"),
                    Span(cfg["desc"], cls="block text-[15px] text-muted-foreground mt-0.5"),
                    cls="flex-1 min-w-0",
                ),
                cls="flex items-center gap-[18px] flex-1 min-w-0",
                **{"x-show": f"processingMode === '{mode_key}'"},
                **({} if is_default else {"x-cloak": True}),  # boundary: fasthtml-elements
            )
        )

    trigger = RawButton(
        *mode_spans,
        UkIcon("chevron-down", cls="w-5 h-5 text-muted-foreground"),
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
                    UkIcon(cfg["icon"], cls="w-[18px] h-[18px]"),
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
                    UkIcon("check", cls="w-4 h-4 text-primary"),
                    **{
                        "x-show": f"processingMode === '{mode_key}'",
                        "x-cloak": True,  # boundary: fasthtml-elements
                    },
                ),
                type="button",
                cls=(
                    "w-full flex items-center gap-3 p-3 rounded-[9px] text-left "
                    "cursor-pointer border-0 font-[inherit] transition-colors"
                ),
                **{
                    "@click": f"selectMode('{mode_key}')",  # boundary: fasthtml-elements
                    ":class": (
                        f"processingMode === '{mode_key}' "
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
            UkIcon(icon, cls="w-[18px] h-[18px]"),
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
                    UkIcon("file-up", cls="w-[26px] h-[26px]"),
                    **{"x-show": "source !== 'folder'"},
                ),
                Span(
                    UkIcon("folder-up", cls="w-[26px] h-[26px]"),
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
                UkIcon("folder-open", cls="w-[19px] h-[19px]"),
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


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------


def render_upload_form(exercises: list[Any] | None = None) -> Any:
    """Render journal capture form — Processing → Source → Browse → Process.

    Args:
        exercises: Unused — kept for call-site compatibility.
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


def upload_form_script() -> Any:
    """HTMX event handlers for the journal upload form."""
    return Script(
        NotStr("""
        document.body.addEventListener('htmx:beforeRequest', function(evt) {
            var form = evt.detail.elt;
            if (form.id !== 'upload-form') return;
            var fileInput = document.getElementById('file-input');
            var folderInput = document.getElementById('folder-input');
            var hasFiles = (fileInput && fileInput.files.length > 0) ||
                           (folderInput && folderInput.files.length > 0);
            if (!hasFiles) {
                evt.preventDefault();
                var status = document.getElementById('upload-status');
                if (status) status.innerHTML =
                    '<p class="text-destructive text-sm text-center mt-2">Please select a file first.</p>';
                return;
            }
            var count = (fileInput ? fileInput.files.length : 0) +
                        (folderInput ? folderInput.files.length : 0);
            var btn = form.querySelector('button[type="submit"]');
            if (btn) {
                btn.disabled = true;
                var label = btn.querySelector('.btn-label');
                if (label) label.textContent = count > 1
                    ? 'Processing ' + count + ' files...'
                    : 'Processing...';
            }
        });

        document.body.addEventListener('htmx:afterRequest', function(evt) {
            var form = evt.detail.elt;
            if (form.id !== 'upload-form') return;
            form.reset();
            var btn = form.querySelector('button[type="submit"]');
            if (btn) {
                btn.disabled = false;
                var label = btn.querySelector('.btn-label');
                if (label) label.textContent = 'Process';
            }
            window.dispatchEvent(new CustomEvent('journals:upload-complete'));
        });

        document.body.addEventListener('htmx:responseError', function(evt) {
            var form = evt.detail.elt;
            if (form.id !== 'upload-form') return;
            console.error('[Journals] Request failed:', evt.detail.xhr.status);
            var status = document.getElementById('upload-status');
            if (status) status.innerHTML =
                '<p class="text-destructive text-sm text-center mt-2">Upload failed (' +
                evt.detail.xhr.status + '). Please try again.</p>';
        });

        document.body.addEventListener('htmx:sendError', function(evt) {
            var form = evt.detail.elt;
            if (form.id !== 'upload-form') return;
            console.error('[Journals] Network error:', evt.detail.error);
            var status = document.getElementById('upload-status');
            if (status) status.innerHTML =
                '<p class="text-destructive text-sm text-center mt-2">Network error. Check your connection.</p>';
        });
    """)
    )
