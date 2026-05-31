"""Journal upload form and related UI components."""

from typing import Any

from fasthtml.common import Div, NotStr, P, Script, Span

from core.models.exercises.exercise import Exercise
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.forms import Input, Label, Radio
from ui.journals.cards import render_instruction_list
from ui.layout import Size


def render_upload_form(exercises: list[Exercise] | None = None) -> Any:
    """Render the file upload form — title + instruction selector + file."""
    exercises = exercises or []
    return Div(
        Card(
            # x-data on card-body so both Form and instruction file picker share scope
            CardBody(
                _build_upload_form_element(exercises),
                # Instruction file picker — sibling of Form, shares Alpine scope from card-body
                Input(
                    type="file",
                    id="instruction-file-picker",
                    name="instruction_file",
                    cls="hidden",
                    accept=".txt,.md,.rst,text/plain,text/markdown",
                    hx_post="/journals/instructions/upload",
                    hx_target="#instruction-file-list",
                    hx_swap="outerHTML",
                    hx_encoding="multipart/form-data",
                    hx_trigger="change",
                ),
                **{
                    "x-data": """{
                        selectedFile: null,
                        instructionMode: 'default',
                        handleFileSelect(event) {
                            const file = event.target.files[0];
                            if (file) {
                                this.selectedFile = file;
                                const labelText = document.getElementById('file-label-text');
                                const labelHint = document.getElementById('file-label-hint');
                                if (labelText) labelText.textContent = file.name;
                                if (labelHint) labelHint.textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
                            }
                        },
                        clearInstructionUid() {
                            const inp = document.getElementById('exercise-uid-input');
                            if (inp) inp.value = '';
                        },
                        autoSelectFirstInstruction() {
                            const card = document.querySelector('#instruction-file-list .instruction-card[data-uid]');
                            if (card) selectInstruction(card.dataset.uid, card);
                        }
                    }"""
                },
            ),
            cls="bg-background shadow-sm hover:shadow-md transition-shadow",
        ),
    )


def _build_upload_form_element(exercises: list[Exercise]) -> Any:
    """Build the inner Form element for journal upload."""
    from fasthtml.common import Form

    return Form(
        # Title input (optional — auto-generated if left blank)
        Div(
            Label("Title (optional)"),
            Input(
                type="text",
                name="title",
                placeholder="Leave blank to auto-generate (e.g. Journal — mike — Mar 02, 2026 — #1)",
            ),
            P(
                "Leave blank to use the auto-generated title",
                cls="text-xs text-muted-foreground mt-1",
            ),
            cls="mb-4",
        ),
        # Hidden exercise_uid — set by selectInstruction() JS, cleared on default mode
        Input(type="hidden", name="exercise_uid", id="exercise-uid-input", value=""),
        # Processing instructions section
        Div(
            Label("Processing Instructions"),
            Div(
                # Default radio
                Label(
                    Radio(
                        name="instruction_mode",
                        value="default",
                        **{  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
                            "x-model": "instructionMode",
                            "@change": "clearInstructionUid()",
                        },
                    ),
                    Span("Default instructions", cls="ml-2"),
                    cls="flex items-center cursor-pointer",
                ),
                # Custom file radio
                Label(
                    Radio(
                        name="instruction_mode",
                        value="custom",
                        **{  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
                            "x-model": "instructionMode",
                            "@change": "autoSelectFirstInstruction()",
                        },
                    ),
                    Span("Custom instruction file", cls="ml-2"),
                    cls="flex items-center cursor-pointer",
                ),
                # Custom mode panel (shown when custom radio selected)
                Div(
                    # Upload button triggers the instruction file picker (outside form)
                    Button(
                        "+ Upload instruction file",
                        type="button",
                        variant=ButtonT.outline,
                        size=Size.sm,
                        cls="mb-3",
                        **{"@click": "document.getElementById('instruction-file-picker').click()"},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
                    ),
                    # Saved instruction list (HTMX target)
                    render_instruction_list(exercises),
                    cls="mt-2",
                    **{"x-show": "instructionMode === 'custom'"},
                ),
                cls="flex flex-col gap-2",
            ),
            cls="mb-4",
        ),
        # Journal file picker (hidden, triggered by drop-zone click)
        Input(
            type="file",
            name="file",
            id="file-input",
            accept="audio/*,text/*,.pdf,.doc,.docx,image/*,video/*",
            cls="hidden",
            required=True,
            **{"x-on:change": "handleFileSelect($event)"},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
        ),
        # Drop-zone
        Div(
            Div(
                P("Select File", cls="text-center mb-0", id="file-label-text"),
                P(
                    "Click to browse (audio, text, PDF, images, video)",
                    cls="text-sm text-muted-foreground text-center mt-0",
                    id="file-label-hint",
                ),
                cls="p-4 text-center bg-muted rounded-lg cursor-pointer border-2 border-dashed border-border",
                **{"x-on:click": "document.getElementById('file-input').click()"},
            ),
            cls="mb-4",
        ),
        # Submit button
        Div(
            Button("Submit to AI", variant=ButtonT.primary, type="submit"),
            cls="text-center",
        ),
        # Upload status (HTMX target)
        Div(id="upload-status", cls="mt-4 text-center"),
        hx_post="/journals/upload",
        hx_target="#upload-status",
        hx_swap="outerHTML",
        hx_encoding="multipart/form-data",
        id="upload-form",
    )


def upload_form_script() -> Any:
    """HTMX event handlers and helpers for the journal upload form."""
    return Script(
        NotStr("""
        // Global: highlight selected instruction card and store its uid
        function selectInstruction(uid, el) {
            document.querySelectorAll('.instruction-card').forEach(function(c) {
                c.classList.remove('ring-2', 'ring-primary', 'bg-muted');
            });
            if (el) el.classList.add('ring-2', 'ring-primary', 'bg-muted');
            var inp = document.getElementById('exercise-uid-input');
            if (inp) inp.value = uid || '';
        }

        // After instruction file upload: auto-select the first (newest) card
        document.body.addEventListener('htmx:afterSwap', function(evt) {
            if (evt.detail.target && evt.detail.target.id === 'instruction-file-list') {
                var firstCard = evt.detail.target.querySelector('.instruction-card[data-uid]');
                if (firstCard) selectInstruction(firstCard.dataset.uid, firstCard);
            }
        });

        document.body.addEventListener('htmx:beforeRequest', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form') {
                console.log('[Journals] Starting upload...');

                // Check if file is selected
                var fileInput = document.getElementById('file-input');
                if (fileInput && fileInput.files.length === 0) {
                    console.error('[Journals] No file selected');
                    evt.preventDefault();
                    alert('Please select a file first');
                    return;
                }

                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = true;
                    btn.textContent = 'Processing...';
                }
            }
        });

        document.body.addEventListener('htmx:afterRequest', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form') {
                console.log('[Journals] Upload request completed');

                // Reset form (file input will be cleared)
                form.reset();

                // Clear custom file label
                var labelText = document.getElementById('file-label-text');
                var labelHint = document.getElementById('file-label-hint');
                if (labelText) labelText.textContent = 'Select File';
                if (labelHint) labelHint.textContent = 'Click to browse (audio, text, PDF, images, video)';

                var btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Submit to AI';
                }
            }
        });

        document.body.addEventListener('htmx:responseError', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form') {
                console.error('[Journals] Upload failed:', evt.detail.xhr.status, evt.detail.xhr.statusText);
                alert('Upload failed: ' + evt.detail.xhr.status + ' - ' + evt.detail.xhr.statusText);
            }
        });

        document.body.addEventListener('htmx:sendError', function(evt) {
            var form = evt.detail.elt;
            if (form.id === 'upload-form') {
                console.error('[Journals] Network error:', evt.detail.error);
                alert('Network error. Please check your connection and try again.');
            }
        });
    """)
    )
