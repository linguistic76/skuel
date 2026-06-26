"""Journal upload form and related UI components."""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div, NotStr, P, Script, Span
from monsterui.franken import UkIcon

from ui.buttons import Button
from ui.cards import Card, CardBody
from ui.forms import Input
from ui.primitives import icon_tile, primary_btn, section_label

# Two hardcoded instruction files shown in the Instructions dropdown.
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
        "title": "Daily Notes — Single",
        "subtitle": "dnwf 1.md",
        "filename": "dnwf 1.md",
    },
    "group_notes": {
        "icon": "files",
        "tile_bg": "bg-slate-50",
        "icon_cls": "text-slate-600",
        "title": "Daily Notes — Group",
        "subtitle": "ddnwf group of notes.md",
        "filename": "ddnwf group of notes.md",
    },
}


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
        icon_tile(cfg["icon"], cfg["tile_bg"], cfg["icon_cls"]),
        Div(
            Span(cfg["title"], cls="text-[14px] font-semibold text-foreground"),
            Span(
                cfg["desc"], cls="block text-[12.5px] text-muted-foreground mt-[6px] leading-[1.35]"
            ),
            cls="flex-1 min-w-0",
        ),
        check,
        type="button",
        cls=(
            "w-full flex items-start gap-3 px-3 py-[14px] rounded-[9px] border-0 "
            "text-left font-[inherit] cursor-pointer transition-colors"
        ),
        **{"@click": f"selectMode('{mode_key}')"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
        **{
            ":class": f"processingMode === '{mode_key}' ? 'bg-blue-50' : 'bg-transparent hover:bg-slate-100'"
        },  # type: ignore[arg-type]  # boundary: fasthtml-elements
    )


def _mode_trigger() -> Any:
    """Full-width trigger showing the currently selected processing mode."""
    options = []
    for mode_key, cfg in _MODE_CONFIGS.items():
        options.append(
            Span(
                icon_tile(cfg["icon"], cfg["tile_bg"], cfg["icon_cls"]),
                Span(
                    Span(cfg["title"], cls="block text-[14.5px] font-semibold text-foreground"),
                    Span(cfg["desc"], cls="block text-[12.5px] text-muted-foreground mt-[3px]"),
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
            "bg-card border border-border rounded-[13px] p-[6px] flex flex-col gap-[3px] "
            "shadow-[0_12px_32px_rgba(15,23,42,0.13)]"
        ),
        **{"x-show": "modeMenuOpen"},
        **{"x-cloak": True},
        **{"@click.outside": "modeMenuOpen = false"},
    )
    return Div(
        section_label("Processing"),
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
    subtitle = cfg.get("subtitle", "")
    return Button(
        icon_tile(cfg["icon"], cfg["tile_bg"], cfg["icon_cls"]),
        Div(
            Span(cfg["title"], cls="text-[14px] font-semibold text-foreground"),
            Span(subtitle, cls="block text-[12px] text-slate-400 font-mono mt-[6px]")
            if subtitle
            else None,
            cls="flex-1 min-w-0",
        ),
        check,
        type="button",
        cls=(
            "w-full flex items-start gap-3 px-3 py-[14px] rounded-[9px] border-0 "
            "text-left font-[inherit] cursor-pointer transition-colors"
        ),
        **{"@click": f"selectInstruction('{mode_key}', '{cfg['filename']}')"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
        **{
            ":class": f"instructionMode === '{mode_key}' ? 'bg-blue-50' : 'bg-transparent hover:bg-slate-100'"
        },  # type: ignore[arg-type]  # boundary: fasthtml-elements
    )


def _instruction_trigger() -> Any:
    """Full-width trigger showing the currently selected instruction set."""
    fixed_spans = []
    for mode_key, cfg in _INSTRUCTION_CONFIGS.items():
        subtitle = cfg.get("subtitle", "")
        fixed_spans.append(
            Span(
                icon_tile(cfg["icon"], cfg["tile_bg"], cfg["icon_cls"]),
                Span(
                    Span(cfg["title"], cls="block text-[14.5px] font-semibold text-foreground"),
                    Span(subtitle, cls="block text-[12px] text-slate-400 font-mono mt-[3px]")
                    if subtitle
                    else None,
                    cls="flex-1 min-w-0",
                ),
                cls="flex items-center gap-[13px] w-full",
                **{"x-show": f"instructionMode === '{mode_key}'"},
                **{"x-cloak": True},
            )
        )
    # Custom file trigger: blue upload tile + filename + "Your file" subtitle
    fixed_spans.append(
        Span(
            icon_tile("upload", "bg-blue-50", "text-blue-600"),
            Span(
                Span(
                    cls="block text-[14.5px] font-semibold text-foreground truncate",
                    **{"x-text": "customInstructionFilename || 'Custom file'"},
                ),
                Span("Your file", cls="block text-[12px] text-slate-400 font-mono mt-[3px]"),
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
    """Instructions selector — conditional on processingMode (hidden for transcribe_only)."""
    separator = Div(cls="h-px bg-slate-100 my-1 mx-2")
    choose_row = Button(
        icon_tile("upload", "bg-blue-50", "text-blue-600"),
        Div(
            Span("Choose a file…", cls="text-[14px] font-semibold text-foreground"),
            Span(
                "Upload your own .md, .txt or .rst",
                cls="block text-[12.5px] text-muted-foreground mt-[6px] leading-[1.35]",
            ),
            cls="flex-1 min-w-0",
        ),
        type="button",
        cls=(
            "w-full flex items-start gap-3 p-3 rounded-[9px] border-0 "
            "text-left font-[inherit] cursor-pointer transition-colors"
        ),
        **{"@click": "openCustomFile()"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
        **{
            ":class": "instructionMode === 'custom' ? 'bg-blue-50' : 'bg-transparent hover:bg-slate-100'"
        },  # type: ignore[arg-type]  # boundary: fasthtml-elements
    )
    menu = Div(
        *[_instruction_option_row(key, cfg) for key, cfg in _INSTRUCTION_CONFIGS.items()],
        separator,
        choose_row,
        cls=(
            "absolute top-[calc(100%+6px)] left-0 right-0 z-30 "
            "bg-card border border-border rounded-[13px] p-[6px] flex flex-col gap-[3px] "
            "shadow-[0_12px_32px_rgba(15,23,42,0.13)]"
        ),
        **{"x-show": "instructionMenuOpen"},
        **{"x-cloak": True},
        **{"@click.outside": "instructionMenuOpen = false"},
    )
    return Div(
        Div(
            Span(
                "Instructions",
                cls="text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground",
            ),
            Span("Pick a preset or your own file", cls="text-[11.5px] text-slate-400"),
            cls="flex items-center justify-between mb-[9px]",
        ),
        Div(_instruction_trigger(), menu, cls="relative"),
        cls="mb-6",
        **{"x-show": "processingMode !== 'transcribe_only'"},
        **{"x-cloak": True},
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
    """File picker with empty dropzone / filled file-card states and submit footer."""
    from fasthtml.common import Button as RawButton
    from fasthtml.common import Form

    empty_state = Div(
        Div(
            UkIcon("upload", cls="w-6 h-6 text-blue-600"),
            cls=(
                "w-[46px] h-[46px] rounded-[12px] border border-border bg-background "
                "flex items-center justify-center mb-3"
            ),
        ),
        P("Drag & drop your file here", cls="text-[14.5px] font-semibold text-foreground mb-1"),
        P(
            Span("or "),
            Span("browse", cls="text-blue-600 font-semibold"),
            Span(" — audio, text, PDF, images, video"),
            cls="text-[13px] text-muted-foreground",
        ),
        cls=(
            "border-[1.5px] border-dashed border-slate-300 rounded-[12px] bg-slate-50 "
            "px-6 py-[34px] text-center cursor-pointer flex flex-col items-center "
            "hover:border-blue-600 hover:bg-blue-50 transition-colors mb-6"
        ),
        **{
            "x-show": "!selectedFile",
            "@click": "document.getElementById('file-input').click()",
        },
    )

    filled_state = Div(
        Div(
            UkIcon("file-text", cls="w-5 h-5 text-blue-600"),
            cls="w-[42px] h-[42px] rounded-[10px] bg-blue-50 flex items-center justify-center flex-none",
        ),
        Div(
            P(
                cls="text-[14px] font-semibold text-foreground truncate leading-snug",
                **{"x-text": "selectedFile ? selectedFile.name : ''"},
            ),
            P("ready to process", cls="text-[12px] text-slate-400 font-mono mt-0.5"),
            cls="flex-1 min-w-0",
        ),
        RawButton(
            "Replace",
            type="button",
            cls=(
                "text-[13px] font-medium text-foreground border border-border "
                "rounded-[8px] px-3 py-[7px] hover:bg-slate-50 transition-colors flex-none"
            ),
            **{"@click": "document.getElementById('file-input').click()"},
        ),
        RawButton(
            UkIcon("x", cls="w-4 h-4"),
            type="button",
            cls=(
                "w-8 h-8 flex items-center justify-center rounded-lg "
                "text-muted-foreground hover:bg-slate-100 hover:text-foreground transition-colors flex-none"
            ),
            **{"@click": "clearFile()"},
        ),
        cls="flex items-center gap-[14px] px-4 py-[14px] border border-border rounded-[12px] bg-card mb-6",
        **{"x-show": "selectedFile", "x-cloak": True},
    )

    return Form(
        *_shared_hidden_inputs(),
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
        empty_state,
        filled_state,
        Div(
            P("Up to 100 MB per file.", cls="text-[12.5px] text-slate-400"),
            primary_btn("Process", type="submit"),
            cls="flex items-center justify-between pt-[22px] mt-[26px] border-t border-border",
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
    """Folder info with je_in/ → je_out/ layout and submit footer."""
    from fasthtml.common import Code, Form

    return Form(
        *_shared_hidden_inputs(),
        Div(
            UkIcon("folder", cls="w-5 h-5 text-muted-foreground flex-none"),
            Code("je_in/", cls="text-sm font-mono text-foreground"),
            UkIcon("arrow-right", cls="w-4 h-4 text-slate-400 flex-none"),
            Code("je_out/", cls="text-sm font-mono text-muted-foreground"),
            Span("All files processed", cls="ml-auto text-[12px] text-slate-400"),
            cls="flex items-center gap-[13px] px-4 py-[14px] bg-slate-50 border border-border rounded-[12px]",
        ),
        Div(
            P("Watches je_in/ continuously.", cls="text-[12.5px] text-slate-400"),
            primary_btn("Process folder", type="submit"),
            cls="flex items-center justify-between pt-[22px] mt-[26px] border-t border-border",
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
            this.selectedFile = files.length > 0 ? files[0] : null;
        }},

        clearFile() {{
            this.selectedFile = null;
            this.fileCount = 0;
            const fi = document.getElementById('file-input');
            if (fi) fi.value = '';
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
                _build_mode_dropdown(),
                _build_instructions_dropdown(),
                # Hidden file input for custom instruction content
                Input(
                    type="file",
                    id="custom-instruction-input",
                    accept=".md,.txt,.rst",
                    cls="hidden",
                    **{"@change": "onCustomFileChange($event)"},  # type: ignore[arg-type]  # boundary: fasthtml-elements
                ),
                # Source section
                Div(
                    section_label("Source"),
                    Div(
                        RawButton(
                            "Upload files",
                            type="button",
                            cls=(
                                "flex-1 py-[8px] text-[13.5px] font-semibold rounded-[7px] "
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
                            "Watch folder",
                            type="button",
                            cls=(
                                "flex-1 py-[8px] text-[13.5px] font-semibold rounded-[7px] "
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
                        cls="flex border border-border rounded-[10px] p-1",
                    ),
                    cls="mb-6",
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
                    var label = btn.querySelector('.btn-label');
                    if (label) label.textContent = count > 1 ? 'Processing ' + count + ' files...' : 'Processing...';
                }
            }
            if (form.id === 'folder-form') {
                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = true;
                    var label = btn.querySelector('.btn-label');
                    if (label) label.textContent = 'Processing folder...';
                }
            }
        });

        document.body.addEventListener('htmx:afterRequest', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form') {
                form.reset();
                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = false;
                    var label = btn.querySelector('.btn-label');
                    if (label) label.textContent = 'Process';
                }
                window.dispatchEvent(new CustomEvent('journals:upload-complete'));
            }
            if (form.id === 'folder-form') {
                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = false;
                    var label = btn.querySelector('.btn-label');
                    if (label) label.textContent = 'Process folder';
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
