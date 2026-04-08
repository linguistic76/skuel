"""
Journals UI Routes — Personal AI-Processed Journal Entries
===========================================================

Standalone journal UI routes for JeInput + JeOutput entities.
Users upload files here to be processed by AI using default or custom instructions.
Route config in journals_routes.py. All service access goes through JournalOrchestrator.

Layout: Unified sidebar (Tailwind + Alpine) with 3 nav items.
Desktop: collapsible sidebar. Mobile: horizontal tabs.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from fasthtml.common import (
    H4,
    H5,
    Div,
    Form,
    NotStr,
    Option,
    P,
    Script,
    Span,
    Textarea,
)
from starlette.datastructures import UploadFile
from starlette.responses import FileResponse

from adapters.inbound.auth import require_admin, require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.submissions_enums import EnrichmentMode
from core.models.exercises.exercise import Exercise
from core.models.journal.je_input import JeInput
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory, Errors, Result
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Alert, AlertT
from ui.forms import Input, Label, Radio, Select
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_inline_error
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

logger = get_logger("skuel.routes.journals.ui")


# ============================================================================
# HTMX FRAGMENT RENDERING
# ============================================================================


def _render_upload_status(
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


def _render_journal_card(je_input: JeInput) -> Any:
    """Render a single journal entry card for the browse grid using CardGenerator."""
    from ui.patterns.card_generator import CardGenerator

    file_size = je_input.file_size or 0
    file_size_mb = file_size / 1024 / 1024 if file_size else 0

    status = je_input.status
    status_str = (
        status.value if isinstance(status, EntityStatus) else str(status) if status else None
    )

    # Build metadata line
    meta_parts: list[str] = []
    if je_input.original_filename:
        meta_parts.append(je_input.original_filename)
    if file_size_mb > 0:
        meta_parts.append(f"{file_size_mb:.2f} MB")
    if je_input.file_type:
        meta_parts.append(je_input.file_type)

    # Build action buttons
    action_buttons: list[Any] = []

    # Download button for completed entries (download endpoint handles JeOutput lookup)
    is_completed = status == EntityStatus.COMPLETED
    if is_completed:
        action_buttons.append(
            ButtonLink(
                "Download",
                href=f"/journals/{je_input.uid}/download",
                variant=ButtonT.primary,
                size=Size.sm,
            )
        )

    from ui.feedback import StatusBadge

    return CardGenerator.from_dataclass(
        {"title": je_input.title or "Untitled"},
        display_fields=[],
        header_badges=[
            StatusBadge(status_str) if status_str else None,
        ],
        show_labels=False,
        metadata=[" \u2022 ".join(meta_parts)] if meta_parts else None,
        actions=Div(*action_buttons, cls="flex gap-2") if action_buttons else None,
        card_attrs={"cls": "mb-2"},
    )


def _render_journals_grid(je_inputs: list[JeInput]) -> Any:
    """Render journal entries grid as HTML fragment for HTMX swap."""
    if not je_inputs:
        return Div(
            EmptyState(title="No journals found"),
            id="journals-grid-container",
        )

    return Div(
        *[_render_journal_card(ji) for ji in je_inputs],
        id="journals-grid-container",
    )


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

JOURNALS_SIDEBAR_ITEMS = [
    SidebarItem("New Entry", "/journals/submit", "submit", icon="📤"),
    SidebarItem("My Journals", "/journals/browse", "browse", icon="📄"),
    SidebarItem("Batch Ops", "/journals/batch", "batch", icon="📦"),
]


# ============================================================================
# CONTENT FRAGMENTS
# ============================================================================


def _render_instruction_card(ex: Exercise, is_first: bool = False) -> Any:
    """Render one saved instruction file as a selectable card."""
    uid = ex.uid
    title = ex.title or "Unnamed"
    created_at = ex.created_at

    if isinstance(created_at, datetime):
        date_str = created_at.strftime("%b %d, %Y")
    elif isinstance(created_at, str) and created_at:
        date_str = created_at[:10]
    else:
        date_str = ""

    selected_cls = "ring-2 ring-primary bg-muted" if is_first else ""
    return Div(
        Div(
            Span(title, cls="text-sm font-semibold truncate"),
            Span(date_str, cls="text-xs text-muted-foreground shrink-0 ml-2"),
            cls="flex items-center justify-between",
        ),
        cls=f"instruction-card border border-border rounded-lg p-3 cursor-pointer hover:bg-muted transition-colors {selected_cls}",
        **{
            "data-uid": uid,
            "onclick": f"selectInstruction('{uid}', this)",
        },
    )


def _exercise_created_at(exercise: Exercise) -> str:
    """Sort key — ISO string for consistent ordering."""
    return exercise.created_at.isoformat() if exercise.created_at else ""


def _render_instruction_list(exercises: list[Exercise], error: str | None = None) -> Any:
    """Return the #instruction-file-list fragment (initial render or HTMX swap)."""
    exercises_sorted = sorted(
        exercises,
        key=_exercise_created_at,
        reverse=True,
    )[:5]

    parts: list[Any] = []
    if error:
        parts.append(P(f"Error: {error}", cls="text-sm text-error mb-2"))

    if exercises_sorted:
        parts.extend(
            _render_instruction_card(ex, is_first=(i == 0)) for i, ex in enumerate(exercises_sorted)
        )
    else:
        parts.append(EmptyState(title="No saved instruction files yet"))

    return Div(*parts, id="instruction-file-list", cls="space-y-2")


def _render_upload_form(exercises: list[Exercise] | None = None) -> Any:
    """Render the file upload form — title + instruction selector + file."""
    exercises = exercises or []
    return Div(
        Card(
            # x-data on card-body so both Form and instruction file picker share scope
            CardBody(
                Form(
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
                                    **{
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
                                    **{
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
                                    **{
                                        "@click": "document.getElementById('instruction-file-picker').click()"
                                    },
                                ),
                                # Saved instruction list (HTMX target)
                                _render_instruction_list(exercises),
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
                        **{"x-on:change": "handleFileSelect($event)"},
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
                ),
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


def _upload_form_script() -> Any:
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


def _render_filters_section() -> Any:
    """Render the status filter controls card."""
    return Card(
        CardBody(
            Form(
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
            ),
        ),
        cls="bg-background shadow-sm mb-6",
    )


def _render_journals_grid_container() -> Any:
    """Render the HTMX-loading journals grid container."""
    return Div(
        P("Loading journals...", cls="text-center text-muted-foreground"),
        id="journals-grid-container",
        cls="mt-4",
        hx_get="/journals/grid",
        hx_trigger="load",
        hx_swap="outerHTML",
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_journals_ui_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    orchestrator: Any,
) -> list[Any]:
    """
    Create journal UI routes — available to all authenticated users.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: JournalOrchestrator — unified facade for all journal services
    """
    if orchestrator is None:
        raise RuntimeError("JournalOrchestrator is required — check bootstrap wiring")

    logger.info("Creating Journals UI routes")

    def get_user_service() -> Any:
        return orchestrator.user_service

    # ========================================================================
    # SIDEBAR PAGES
    # ========================================================================

    @rt("/journals")
    async def journals_landing(request: Request) -> Any:
        """Journals landing — defaults to Submit page."""
        return await _render_submit_page(request)

    @rt("/journals/submit")
    async def journals_submit_page(request: Request) -> Any:
        """Submit page: simplified upload form."""
        return await _render_submit_page(request)

    async def _render_submit_page(request: Request) -> Any:
        user_uid = require_authenticated_user(request)

        exercises: list[Exercise] = []
        ex_result = await orchestrator.list_user_exercises(user_uid)
        if ex_result.is_ok:
            exercises = ex_result.value or []
        else:
            logger.warning(
                "Failed to list exercises for submit page",
                extra={"error": str(ex_result.error)},
            )

        content = Div(
            PageHeader(
                "New Journal Entry",
                subtitle="Upload a file to be processed by AI",
            ),
            _render_upload_form(exercises),
            _upload_form_script(),
        )
        return await SidebarPage(
            content=content,
            items=JOURNALS_SIDEBAR_ITEMS,
            active="submit",
            title="Journals",
            subtitle="Your personal journal",
            storage_key="journals-sidebar",
            page_title="Submit to AI",
            request=request,
            active_page="journals",
            title_href="/journals",
        )

    @rt("/journals/browse")
    async def journals_browse_page(request: Request) -> Any:
        """Browse page: journal entries with filters."""
        require_authenticated_user(request)

        content = Div(
            PageHeader("My Journals", subtitle="Browse your AI-processed journal entries"),
            _render_filters_section(),
            _render_journals_grid_container(),
        )
        return await SidebarPage(
            content=content,
            items=JOURNALS_SIDEBAR_ITEMS,
            active="browse",
            title="Journals",
            subtitle="Your personal journal",
            storage_key="journals-sidebar",
            page_title="My Journals",
            request=request,
            active_page="journals",
            title_href="/journals",
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/journals/upload")
    async def upload_journal(request: Request) -> Any:
        """HTMX endpoint for file upload with AI processing using default instructions."""
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            raw_title = form.get("title")
            custom_title = str(raw_title).strip() if raw_title else ""

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return _render_upload_status("error", "No file provided", is_error=True)

            user_uid = require_authenticated_user(request)
            file_content = await uploaded_file.read()
            filename = uploaded_file.filename or "unknown"
            metadata = {"custom_title": custom_title} if custom_title else None

            result = await orchestrator.submit_journal_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                metadata=metadata,
            )

            if result.is_error:
                return _render_upload_status("error", str(result.error), is_error=True)

            je_input = result.value
            return _render_upload_status(
                str(je_input.status.value)
                if isinstance(je_input.status, EntityStatus)
                else str(je_input.status),
                f"Journal entry created: {je_input.title}",
                je_input_uid=je_input.uid,
            )

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error uploading journal: {e}", exc_info=True)
            return _render_upload_status("error", f"Upload failed: {e}", is_error=True)

    @rt("/journals/instructions/upload")
    async def upload_instruction_file(request: Request) -> Any:
        """HTMX endpoint: save an instruction text file, return updated card list."""
        try:
            user_uid = require_authenticated_user(request)
            form = await request.form()
            uploaded_file = form.get("instruction_file")

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return _render_instruction_list([], error="No file provided")

            file_bytes = await uploaded_file.read()
            try:
                instructions_text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return _render_instruction_list([], error="File must be plain text (UTF-8)")

            if not instructions_text.strip():
                return _render_instruction_list([], error="File is empty")

            filename = uploaded_file.filename or "instructions.txt"

            create_result = await orchestrator.create_exercise(
                user_uid=user_uid,
                name=filename,
                instructions=instructions_text,
            )
            if create_result.is_error:
                logger.warning(f"Failed to save instruction file: {create_result.error}")

            # Fetch updated list and return refreshed fragment
            exercises: list[Exercise] = []
            ex_result = await orchestrator.list_user_exercises(user_uid)
            if ex_result.is_ok:
                exercises = ex_result.value or []
            else:
                logger.warning(
                    "Failed to refresh exercise list after upload",
                    extra={"error": str(ex_result.error)},
                )

            logger.info(f"Instruction file saved for {user_uid}: {filename}")
            return _render_instruction_list(exercises)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error saving instruction file: {e}", exc_info=True)
            return _render_instruction_list([], error=str(e))

    @rt("/journals/grid")
    async def get_journals_grid(request: Request) -> Any:
        """HTMX endpoint for loading journal entries grid."""
        try:
            user_uid = require_authenticated_user(request)
            status_str = request.query_params.get("status", "")
            status: EntityStatus | None = None
            if status_str:
                try:
                    status = EntityStatus(status_str)
                except ValueError:
                    return Div(
                        render_inline_error(f"Invalid status: {status_str}"),
                        id="journals-grid-container",
                    )

            result = await orchestrator.list_je_inputs(
                user_uid=user_uid,
                status=status,
                limit=50,
            )

            if result.is_error:
                return Div(
                    render_inline_error("Failed to load journals"),
                    id="journals-grid-container",
                )

            je_inputs = result.value or []
            return _render_journals_grid(je_inputs)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error loading journals: {e}", exc_info=True)
            return Div(
                render_inline_error(f"Error: {e}"),
                id="journals-grid-container",
            )

    @rt("/journals/{uid}/download")
    async def download_je_output(request: Request, uid: str) -> Any:
        """Download formatted je_output file for a journal entry.

        The uid is a JeInput UID. Looks up the associated JeOutput via TRANSFORMS.

        Returns:
            FileResponse with markdown file or error response
        """
        try:
            user_uid = require_authenticated_user(request)

            # Ownership check + TRANSFORMS lookup in one call
            download_result = await orchestrator.get_journal_for_download(uid, user_uid)
            if download_result.is_error:
                err = download_result.expect_error()
                if err.category == ErrorCategory.NOT_FOUND:
                    logger.warning(f"Journal entry {uid} not found or not owned by {user_uid}")
                    return render_inline_error("Journal entry not found")
                logger.warning(f"No je_output available for journal entry {uid}: {err}")
                return render_inline_error("No output file available for this journal entry")

            je_input, je_output = download_result.value
            if not je_output.output_file_path or not Path(je_output.output_file_path).exists():
                logger.error(f"je_output file not found on disk for journal entry {uid}")
                return render_inline_error("Output file not found on disk")

            download_name = f"{je_input.original_filename or je_input.title}_output.md"
            logger.info(
                f"Serving je_output download for journal {uid}: {je_output.output_file_path}"
            )
            return FileResponse(
                path=je_output.output_file_path,
                filename=download_name,
                media_type="text/markdown",
            )

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error downloading je_output for {uid}: {e}", exc_info=True)
            return Div(
                P(f"Download failed: {e}", cls="text-center text-error"),
            )

    # ========================================================================
    # BATCH OPERATIONS PAGE (admin-only)
    # ========================================================================

    @rt("/journals/batch")
    @require_admin(get_user_service)
    async def journals_batch_page(request: Request, current_user: Any = None) -> Any:
        """Batch operations page: transcribe + process multiple files."""
        content = Div(
            PageHeader(
                "Batch Operations",
                subtitle="Transcribe and process multiple audio files",
            ),
            # Directories card
            Card(
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
            ),
            # Processing options card
            Card(
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
                            Option(
                                "Idea Articulation", value=EnrichmentMode.IDEA_ARTICULATION.value
                            ),
                            Option(
                                "Critical Thinking", value=EnrichmentMode.CRITICAL_THINKING.value
                            ),
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
            ),
            # Results area
            Div(id="batch-results", cls="mt-4"),
            # Batch operations script
            Script(
                NotStr("""
                function getInputDir() { return document.getElementById('input-dir').value; }
                function getOutputDir() { return document.getElementById('output-dir').value; }
                function getProcessingOpts() {
                    return {
                        enrichment_mode: document.getElementById('enrichment-mode').value,
                        model: document.getElementById('llm-model').value,
                        custom_instructions: document.getElementById('custom-instructions').value || null,
                    };
                }
                function showResult(html) {
                    document.getElementById('batch-results').innerHTML = html;
                }
                function showLoading(msg) {
                    showResult('<div class="text-center text-muted-foreground p-4">' + msg + '</div>');
                }
                function formatResult(data) {
                    if (data.preview) {
                        var html = '<div class="p-4 bg-muted rounded-lg">';
                        html += '<h5 class="font-semibold mb-2">Preview: ' + data.total_files + ' files (' + data.total_size_mb + ' MB)</h5>';
                        if (data.already_transcribed && data.already_transcribed.length > 0) {
                            html += '<p class="text-sm text-muted-foreground mb-2">Already transcribed: ' + data.already_transcribed.length + '</p>';
                        }
                        html += '<ul class="text-sm space-y-1">';
                        (data.files || []).forEach(function(f) {
                            var done = (data.already_transcribed || []).includes(f.name) ? ' <span class="text-success">[done]</span>' : '';
                            html += '<li>' + f.name + ' (' + f.size_mb + ' MB)' + done + '</li>';
                        });
                        html += '</ul></div>';
                        return html;
                    }
                    // Batch result
                    var html = '<div class="p-4 bg-muted rounded-lg">';
                    if (data.transcription) {
                        html += '<h5 class="font-semibold mb-1">Tier 1: Transcription</h5>';
                        html += '<p class="text-sm mb-2">Succeeded: ' + data.transcription.succeeded + ', Failed: ' + data.transcription.failed + ', Skipped: ' + data.transcription.skipped + '</p>';
                        html += '<h5 class="font-semibold mb-1">Tier 2: Processing</h5>';
                        html += '<p class="text-sm mb-2">Succeeded: ' + data.processing.succeeded + ', Failed: ' + data.processing.failed + ', Skipped: ' + data.processing.skipped + '</p>';
                    } else {
                        html += '<h5 class="font-semibold mb-1">Results</h5>';
                        html += '<p class="text-sm mb-2">Total: ' + (data.total_files || 0) + ', Succeeded: ' + (data.succeeded || 0) + ', Failed: ' + (data.failed || 0) + ', Skipped: ' + (data.skipped || 0) + '</p>';
                    }
                    var errors = data.errors || [];
                    if (errors.length > 0) {
                        html += '<h5 class="font-semibold text-error mb-1">Errors</h5>';
                        html += '<ul class="text-sm text-error">';
                        errors.forEach(function(e) { html += '<li>' + e.name + ': ' + e.error + '</li>'; });
                        html += '</ul>';
                    }
                    html += '</div>';
                    return html;
                }
                async function apiCall(url, body) {
                    try {
                        var resp = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
                        var data = await resp.json();
                        if (!resp.ok) { showResult('<div class="alert alert-error">' + JSON.stringify(data) + '</div>'); return; }
                        showResult(formatResult(data));
                    } catch(e) { showResult('<div class="alert alert-error">Request failed: ' + e + '</div>'); }
                }

                document.getElementById('preview-btn').addEventListener('click', function() {
                    showLoading('Loading preview...');
                    apiCall('/api/journals/batch-transcribe', {input_dir: getInputDir(), output_dir: getOutputDir(), preview_only: true});
                });
                document.getElementById('transcribe-btn').addEventListener('click', function() {
                    showLoading('Transcribing... this may take a few minutes.');
                    apiCall('/api/journals/batch-transcribe', {input_dir: getInputDir(), output_dir: getOutputDir(), skip_existing: true});
                });
                document.getElementById('process-btn').addEventListener('click', function() {
                    var opts = getProcessingOpts();
                    showLoading('Processing transcripts via LLM...');
                    apiCall('/api/journals/batch-process', {input_dir: getOutputDir(), ...opts, skip_existing: true});
                });
                document.getElementById('combined-btn').addEventListener('click', function() {
                    var opts = getProcessingOpts();
                    showLoading('Running combined pipeline (transcribe + process)...');
                    apiCall('/api/journals/batch-process', {combined: true, audio_dir: getInputDir(), output_dir: getOutputDir(), ...opts, skip_existing: true});
                });
            """)
            ),
        )
        return await SidebarPage(
            content=content,
            items=JOURNALS_SIDEBAR_ITEMS,
            active="batch",
            title="Journals",
            subtitle="Your personal journal",
            storage_key="journals-sidebar",
            page_title="Batch Operations",
            request=request,
            active_page="journals",
            title_href="/journals",
        )

    # ========================================================================
    # ADMIN API ENDPOINTS
    # ========================================================================

    @rt("/api/admin/journals/cleanup")
    @require_admin(get_user_service)
    @boundary_handler()
    async def cleanup_je_outputs(
        request: Request,
        current_user: Any,
        start_date: str,
        end_date: str,
    ) -> Result[dict[str, int]]:
        """
        Clean up je_output files from date range (ADMIN only).

        Used after human has decomposed je_outputs and ingested pieces into Neo4j.

        Query Parameters:
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)

        Returns:
            JSON with cleanup stats: {files_deleted: int, bytes_freed: int}
        """
        # Parse dates
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            return Result.fail(
                Errors.validation(
                    message=f"Invalid date format. Use YYYY-MM-DD: {e}",
                    field="start_date/end_date",
                )
            )

        if start_dt > end_dt:
            return Result.fail(
                Errors.validation(
                    message="start_date must be before or equal to end_date",
                    field="start_date",
                )
            )

        logger.info(
            f"Admin {current_user.uid} cleaning up je_outputs from {start_date} to {end_date}"
        )

        result = orchestrator.cleanup_date_range(start_dt, end_dt)

        if result.is_error:
            return Result.fail(result)

        stats = result.value
        logger.info(
            f"Cleanup complete: {stats['files_deleted']} files deleted, "
            f"{stats['bytes_freed']} bytes freed"
        )

        return Result.ok(stats)

    logger.info("Journals UI routes created successfully")

    return [
        journals_landing,
        journals_submit_page,
        journals_browse_page,
        journals_batch_page,
        upload_journal,
        upload_instruction_file,
        get_journals_grid,
        download_je_output,
        cleanup_je_outputs,
    ]
