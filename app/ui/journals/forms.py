"""Journal upload form and related UI components."""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div, NotStr, P, Script, Span
from monsterui.franken import UkIcon

from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.forms import Input

# Two hardcoded instruction files shown in the Instructions dropdown.
# These map filename → display name.
_FIXED_INSTRUCTIONS = [
    ("dnwf 1.md", "Daily Notes — Single"),
    ("ddnwf group of notes.md", "Daily Notes — Group"),
]

_MODE_CONFIGS: dict[str, dict[str, str]] = {
    "transcribe_only": {
        "icon": "mic",
        "tile_bg": "bg-blue-50",
        "icon_cls": "text-blue-600",
        "title": "Transcribe only",
        "desc": "Convert audio or media to text",
    },
    "transcribe_and_instructions": {
        "icon": "sparkles",
        "tile_bg": "bg-violet-50",
        "icon_cls": "text-violet-700",
        "title": "Transcribe + Instructions",
        "desc": "Transcribe audio then apply processing instructions",
    },
    "instructions_only": {
        "icon": "file-text",
        "tile_bg": "bg-emerald-50",
        "icon_cls": "text-emerald-700",
        "title": "Instructions only",
        "desc": "Apply instructions to an existing text file",
    },
}

_INSTRUCTION_CONFIGS: dict[str, dict[str, str]] = {
    "dnwf_1": {
        "icon": "file-text",
        "tile_bg": "bg-slate-50",
        "icon_cls": "text-slate-600",
        "title": "dnwf 1",
        "filename": "dnwf 1.md",
    },
    "group_notes": {
        "icon": "files",
        "tile_bg": "bg-slate-50",
        "icon_cls": "text-slate-600",
        "title": "ddnwf group of notes",
        "filename": "ddnwf group of notes.md",
    },
}


def _icon_tile(icon: str, bg_cls: str, icon_cls: str) -> Any:
    """Rounded icon tile used in dropdown rows."""
    return Div(
        UkIcon(icon, cls=f"w-[18px] h-[18px] {icon_cls}"),
        cls=f"w-[34px] h-[34px] rounded-[8px] flex-none flex items-center justify-center {bg_cls}",
    )


# ---------------------------------------------------------------------------
# Processing dropdown
# ---------------------------------------------------------------------------


def _mode_option_row(mode_key: str, cfg: dict[str, str]) -> Any:
    """One row in the processing mode dropdown."""
    check = Span(
        UkIcon("check", cls="w-4 h-4 text-blue-600"),
        cls="flex-none pt-[3px] flex",
        **{"x-show": f"processingMode === '{mode_key}'"},
        **{"x-cloak": True},
    )
    return Button(
        _icon_tile(cfg["icon"], cfg["tile_bg"], cfg["icon_cls"]),
        Div(
            Span(cfg["title"], cls="text-sm font-semibold text-foreground"),
            Span(cfg["desc"], cls="block text-[12.5px] text-muted-foreground mt-[1px]"),
            cls="flex-1 min-w-0 pt-[1px]",
        ),
        check,
        type="button",
        cls=(
            "w-full flex items-start gap-3 p-[11px] rounded-[9px] border-0 "
            "bg-transparent text-left font-[inherit] cursor-pointer hover:bg-slate-50"
        ),
        **{"@click": f"selectMode('{mode_key}')"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
    )


def _mode_trigger() -> Any:
    """Full-width trigger showing the currently selected processing mode."""
    options = []
    for mode_key, cfg in _MODE_CONFIGS.items():
        options.append(
            Span(
                _icon_tile(cfg["icon"], cfg["tile_bg"], cfg["icon_cls"]),
                Span(
                    Span(cfg["title"], cls="block text-[14.5px] font-semibold text-foreground"),
                    Span(cfg["desc"], cls="block text-[12.5px] text-muted-foreground mt-[1px]"),
                    cls="flex-1 min-w-0",
                ),
                cls="flex items-center gap-[13px] w-full",
                **{"x-show": f"processingMode === '{mode_key}'"},
                **{} if mode_key == "transcribe_only" else {"x-cloak": True},
            )
        )
    return Button(
        *options,
        UkIcon("chevron-down", cls="w-[18px] h-[18px] text-slate-400 flex-none"),
        type="button",
        cls=(
            "w-full flex items-center gap-[13px] px-[14px] py-3 "
            "border border-border rounded-[11px] bg-card cursor-pointer "
            "text-left font-[inherit] hover:border-slate-300 transition-colors"
        ),
        **{"@click": "modeMenuOpen = !modeMenuOpen"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
    )


def _build_mode_dropdown() -> Any:
    """Processing mode selector (trigger + dropdown menu)."""
    menu = Div(
        *[_mode_option_row(key, cfg) for key, cfg in _MODE_CONFIGS.items()],
        cls=(
            "absolute top-[calc(100%+6px)] left-0 right-0 z-30 "
            "bg-card border border-border rounded-[13px] p-[6px] "
            "shadow-[0_12px_32px_rgba(15,23,42,0.13)]"
        ),
        **{"x-show": "modeMenuOpen"},
        **{"x-cloak": True},
        **{"@click.outside": "modeMenuOpen = false"},
    )
    return Div(
        P(
            "Processing",
            cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
        ),
        Div(_mode_trigger(), menu, cls="relative"),
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Instructions dropdown
# ---------------------------------------------------------------------------


def _instruction_option_row(mode_key: str, cfg: dict[str, str]) -> Any:
    """One row in the instructions dropdown."""
    check = Span(
        UkIcon("check", cls="w-4 h-4 text-blue-600"),
        cls="flex-none pt-[3px] flex",
        **{"x-show": f"instructionMode === '{mode_key}'"},
        **{"x-cloak": True},
    )
    return Button(
        _icon_tile(cfg["icon"], cfg["tile_bg"], cfg["icon_cls"]),
        Div(
            Span(cfg["title"], cls="text-sm font-semibold text-foreground"),
            cls="flex-1 min-w-0 pt-[1px]",
        ),
        check,
        type="button",
        cls=(
            "w-full flex items-start gap-3 p-[11px] rounded-[9px] border-0 "
            "bg-transparent text-left font-[inherit] cursor-pointer hover:bg-slate-50"
        ),
        **{"@click": f"selectInstruction('{mode_key}', '{cfg['filename']}')"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
    )


def _instruction_trigger() -> Any:
    """Full-width trigger showing the currently selected instruction set."""
    # Spans for the two fixed options
    fixed_spans = []
    for mode_key, cfg in _INSTRUCTION_CONFIGS.items():
        fixed_spans.append(
            Span(
                _icon_tile(cfg["icon"], cfg["tile_bg"], cfg["icon_cls"]),
                Span(
                    Span(cfg["title"], cls="block text-[14.5px] font-semibold text-foreground"),
                    cls="flex-1 min-w-0",
                ),
                cls="flex items-center gap-[13px] w-full",
                **{"x-show": f"instructionMode === '{mode_key}'"},
                **{"x-cloak": True},
            )
        )
    # Span for custom file
    fixed_spans.append(
        Span(
            _icon_tile("upload", "bg-slate-50", "text-slate-600"),
            Span(
                Span(
                    cls="block text-[14.5px] font-semibold text-foreground truncate",
                    **{"x-text": "customInstructionFilename || 'Custom file'"},
                ),
                cls="flex-1 min-w-0",
            ),
            cls="flex items-center gap-[13px] w-full",
            **{"x-show": "instructionMode === 'custom'"},
            **{"x-cloak": True},
        )
    )
    return Button(
        *fixed_spans,
        UkIcon("chevron-down", cls="w-[18px] h-[18px] text-slate-400 flex-none"),
        type="button",
        cls=(
            "w-full flex items-center gap-[13px] px-[14px] py-3 "
            "border border-border rounded-[11px] bg-card cursor-pointer "
            "text-left font-[inherit] hover:border-slate-300 transition-colors"
        ),
        **{"@click": "instructionMenuOpen = !instructionMenuOpen"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
    )


def _build_instructions_dropdown() -> Any:
    """Instructions selector — two fixed files + choose-a-file option."""
    separator = Div(cls="h-px bg-slate-100 my-1 mx-2")
    choose_row = Button(
        _icon_tile("upload", "bg-slate-50", "text-slate-600"),
        Div(
            Span("Choose a file…", cls="text-sm font-semibold text-foreground"),
            cls="flex-1 min-w-0 pt-[1px]",
        ),
        type="button",
        cls=(
            "w-full flex items-start gap-3 p-[11px] rounded-[9px] border-0 "
            "bg-transparent text-left font-[inherit] cursor-pointer hover:bg-slate-50"
        ),
        **{"@click": "openCustomFile()"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
    )
    menu = Div(
        *[_instruction_option_row(key, cfg) for key, cfg in _INSTRUCTION_CONFIGS.items()],
        separator,
        choose_row,
        cls=(
            "absolute top-[calc(100%+6px)] left-0 right-0 z-30 "
            "bg-card border border-border rounded-[13px] p-[6px] "
            "shadow-[0_12px_32px_rgba(15,23,42,0.13)]"
        ),
        **{"x-show": "instructionMenuOpen"},
        **{"x-cloak": True},
        **{"@click.outside": "instructionMenuOpen = false"},
    )
    return Div(
        P(
            "Instructions",
            cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
        ),
        Div(_instruction_trigger(), menu, cls="relative"),
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Shared hidden inputs (included inside each form)
# ---------------------------------------------------------------------------


def _shared_hidden_inputs() -> list[Any]:
    """Hidden inputs that bind Alpine state to form fields for submission."""
    return [
        Input(
            type="hidden",
            name="processing_mode",
            **{"x-bind:value": "processingMode"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
        ),
        Input(
            type="hidden",
            name="instruction_filename",
            **{"x-bind:value": "instructionFilename"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
        ),
        Input(
            type="hidden",
            name="instruction_content",
            **{"x-bind:value": "customInstructionContent"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
        ),
    ]


# ---------------------------------------------------------------------------
# Files mode form body
# ---------------------------------------------------------------------------


def _build_files_form_body() -> Any:
    """File picker section + submit button for 'Upload Files' mode."""
    from fasthtml.common import Form

    return Form(
        *_shared_hidden_inputs(),

        # File picker label
        P(
            "Your file",
            cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
        ),

        # Hidden file input (triggered by dropzone click)
        Input(
            type="file",
            name="file",
            id="file-input",
            accept="audio/*,text/*,.pdf,.doc,.docx,image/*,video/*",
            cls="hidden",
            required=True,
            multiple=True,
            **{"x-on:change": "handleFileSelect($event)"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
        ),

        # Drop zone
        Div(
            Div(
                P("Select Files", cls="text-center mb-0", id="file-label-text"),
                P(
                    "Click to browse — audio, text, PDF, images, video. Multiple files supported.",
                    cls="text-sm text-muted-foreground text-center mt-0",
                    id="file-label-hint",
                ),
                cls="p-4 text-center bg-muted rounded-lg cursor-pointer border-2 border-dashed border-border",
                **{"x-on:click": "document.getElementById('file-input').click()"},
            ),
            cls="mb-6",
        ),

        # Submit
        Div(
            Button("Process", variant=ButtonT.primary, type="submit"),
            cls="text-center",
        ),

        hx_post="/submit/journals/upload",
        hx_target="#upload-status",
        hx_swap="outerHTML",
        hx_encoding="multipart/form-data",
        id="upload-form",
        **{"@journals:upload-complete.window": "fileCount = 0; selectedFile = null"},
    )


# ---------------------------------------------------------------------------
# Folder mode form body
# ---------------------------------------------------------------------------


def _build_folder_form_body() -> Any:
    """Folder info + submit button for 'Upload Folder' mode."""
    from fasthtml.common import Code, Form

    return Form(
        *_shared_hidden_inputs(),

        # Folder info
        Div(
            P(
                "Source folder",
                cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
            ),
            Div(
                Code(
                    "je_in/",
                    cls="text-sm font-mono text-foreground",
                ),
                P(
                    "All files in this folder will be processed. Results are written to je_out/.",
                    cls="text-xs text-muted-foreground mt-2",
                ),
                cls="p-4 bg-muted rounded-lg border border-border",
            ),
            cls="mb-6",
        ),

        # Submit
        Div(
            Button("Process Folder", variant=ButtonT.primary, type="submit"),
            cls="text-center",
        ),

        hx_post="/submit/journals/folder-process",
        hx_target="#upload-status",
        hx_swap="outerHTML",
        id="folder-form",
    )


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------


def render_upload_form(exercises: list[Any] | None = None) -> Any:
    """Render journal upload form with Files and Folder upload modes.

    Args:
        exercises: Unused — kept for call-site compatibility.
    """
    default_instruction_mode = "dnwf_1"
    default_instruction_filename = _FIXED_INSTRUCTIONS[0][0]

    alpine_data = f"""{{
        uploadMode: 'files',

        processingMode: 'transcribe_only',
        modeMenuOpen: false,

        instructionMode: '{default_instruction_mode}',
        instructionMenuOpen: false,
        instructionFilename: '{default_instruction_filename}',
        customInstructionContent: '',
        customInstructionFilename: '',

        selectedFile: null,
        fileCount: 0,

        handleFileSelect(event) {{
            const files = event.target.files;
            this.fileCount = files.length;
            if (files.length > 0) {{
                this.selectedFile = files[0];
                const labelText = document.getElementById('file-label-text');
                const labelHint = document.getElementById('file-label-hint');
                if (labelText) labelText.textContent = files.length === 1
                    ? files[0].name
                    : files.length + ' files selected';
                if (labelHint) {{
                    const totalMB = Array.from(files)
                        .reduce((s, f) => s + f.size, 0) / 1024 / 1024;
                    labelHint.textContent = files.length === 1
                        ? (files[0].size / 1024 / 1024).toFixed(2) + ' MB'
                        : totalMB.toFixed(2) + ' MB total';
                }}
            }}
        }},

        selectMode(mode) {{
            this.processingMode = mode;
            this.modeMenuOpen = false;
            if (mode !== 'transcribe_only' && !this.instructionFilename && !this.customInstructionContent) {{
                this.instructionFilename = '{default_instruction_filename}';
            }}
        }},

        selectInstruction(mode, filename) {{
            this.instructionMode = mode;
            this.instructionFilename = filename;
            this.customInstructionContent = '';
            this.customInstructionFilename = '';
            this.instructionMenuOpen = false;
        }},

        openCustomFile() {{
            this.instructionMenuOpen = false;
            const el = document.getElementById('custom-instruction-input');
            if (el) el.click();
        }},

        onCustomFileChange(event) {{
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (e) => {{
                this.customInstructionContent = e.target.result;
                this.customInstructionFilename = file.name;
                this.instructionFilename = '';
                this.instructionMode = 'custom';
            }};
            reader.readAsText(file);
        }}
    }}"""

    from fasthtml.common import Button as RawButton

    return Div(
        Card(
            CardBody(
                # Processing dropdown
                _build_mode_dropdown(),

                # Instructions dropdown (always visible)
                _build_instructions_dropdown(),

                # Hidden file input for custom instruction content
                Input(
                    type="file",
                    id="custom-instruction-input",
                    accept=".md,.txt,.rst",
                    cls="hidden",
                    **{"@change": "onCustomFileChange($event)"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
                ),

                # Pill-style mode toggle — inside the card so the change below is
                # immediately visible when the user switches modes
                Div(
                    RawButton(
                        "Upload Files",
                        type="button",
                        cls=(
                            "flex-1 py-[7px] text-sm font-medium rounded-[7px] "
                            "transition-colors cursor-pointer border-0"
                        ),
                        **{
                            "@click": "uploadMode = 'files'",
                            ":class": (
                                "uploadMode === 'files' "
                                "? 'bg-foreground text-background' "
                                ": 'bg-transparent text-muted-foreground hover:text-foreground'"
                            ),
                        },
                    ),
                    RawButton(
                        "Upload Folder",
                        type="button",
                        cls=(
                            "flex-1 py-[7px] text-sm font-medium rounded-[7px] "
                            "transition-colors cursor-pointer border-0"
                        ),
                        **{
                            "@click": "uploadMode = 'folder'",
                            ":class": (
                                "uploadMode === 'folder' "
                                "? 'bg-foreground text-background' "
                                ": 'bg-transparent text-muted-foreground hover:text-foreground'"
                            ),
                        },
                    ),
                    cls="flex border border-border rounded-[10px] p-1 mb-6",
                ),

                # Files mode
                Div(
                    _build_files_form_body(),
                    **{"x-show": "uploadMode === 'files'"},
                ),

                # Folder mode
                Div(
                    _build_folder_form_body(),
                    **{"x-show": "uploadMode === 'folder'", "x-cloak": True},
                ),

                # HTMX status target (shared between both modes)
                Div(id="upload-status", cls="mt-4 text-center"),

                cls="bg-background shadow-sm hover:shadow-md transition-shadow",
            ),
        ),

        **{"x-data": alpine_data},
    )


def upload_form_script() -> Any:
    """HTMX event handlers for the journal upload form."""
    return Script(
        NotStr("""
        document.body.addEventListener('htmx:beforeRequest', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form') {
                var fileInput = document.getElementById('file-input');
                if (fileInput && fileInput.files.length === 0) {
                    evt.preventDefault();
                    alert('Please select a file first');
                    return;
                }
                var count = fileInput ? fileInput.files.length : 0;
                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = true;
                    btn.textContent = count > 1 ? 'Processing ' + count + ' files...' : 'Processing...';
                }
            }
            if (form.id === 'folder-form') {
                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = true;
                    btn.textContent = 'Processing folder...';
                }
            }
        });

        document.body.addEventListener('htmx:afterRequest', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form') {
                form.reset();
                var labelText = document.getElementById('file-label-text');
                var labelHint = document.getElementById('file-label-hint');
                if (labelText) labelText.textContent = 'Select Files';
                if (labelHint) labelHint.textContent = 'Click to browse — audio, text, PDF, images, video. Multiple files supported.';
                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Process';
                }
                window.dispatchEvent(new CustomEvent('journals:upload-complete'));
            }
            if (form.id === 'folder-form') {
                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Process Folder';
                }
            }
        });

        document.body.addEventListener('htmx:responseError', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form' || form.id === 'folder-form') {
                console.error('[Journals] Request failed:', evt.detail.xhr.status, evt.detail.xhr.statusText);
                alert('Failed: ' + evt.detail.xhr.status + ' - ' + evt.detail.xhr.statusText);
            }
        });

        document.body.addEventListener('htmx:sendError', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form' || form.id === 'folder-form') {
                console.error('[Journals] Network error:', evt.detail.error);
                alert('Network error. Please check your connection and try again.');
            }
        });
    """)
    )
