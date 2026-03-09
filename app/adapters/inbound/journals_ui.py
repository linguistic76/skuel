"""
Journals UI Routes — Personal AI-Processed Journal Entries
===========================================================

Journal is a Submission subtype (EntityType.JOURNAL extends Submission).
Users upload files here to be processed by AI using default or custom instructions.
Registered from submissions_routes.py — journals share /api/submissions/* endpoints.

Layout: Unified sidebar (Tailwind + Alpine) with 2 nav items.
Desktop: collapsible sidebar. Mobile: horizontal tabs.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from fasthtml.common import (
    H4,
    A,
    Div,
    Form,
    Input,
    Label,
    NotStr,
    Option,
    P,
    Script,
    Select,
    Span,
)
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse

from adapters.inbound.auth import require_admin, require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.buttons import Button, ButtonT
from ui.feedback import get_submission_status_badge_class
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

logger = get_logger("skuel.routes.journals.ui")


# ============================================================================
# DEFAULT INSTRUCTIONS
# ============================================================================

DEFAULT_INSTRUCTIONS = """# General Processing Instructions

## Purpose
Transform raw content into a well-formatted, readable document.

## Formatting Rules
1. **Structure**: Organize into coherent paragraphs
2. **Flow**: Remove verbal fillers ("um", "uh", "like")
3. **Clarity**: Improve sentence structure while preserving meaning
4. **Themes**: Identify main themes and group related content
5. **Action Items**: Extract concrete action items mentioned
6. **Title**: Generate concise, descriptive title

## Context Integration
- Reference active goals, tasks, habits when relevant
- Link to recent journal themes for continuity
- Identify learning opportunities from current paths

## Output Format
- Title (concise, descriptive)
- Summary (2-3 sentences)
- Main content (well-formatted paragraphs)
- Key themes (bullet list)
- Action items (if any)

Preserve the author's voice and authenticity while improving readability.
"""


# ============================================================================
# HTMX FRAGMENT RENDERING
# ============================================================================


def _render_upload_status(
    status: str,
    message: str,
    report_uid: str | None = None,
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
            H4("Submitted to AI", cls="mb-0"),
            P(f"Report ID: {report_uid}", cls="mb-0") if report_uid else None,
            P(f"Status: {status}", cls="mb-0"),
            A(
                "View Report",
                href=f"/submissions/{report_uid}",
                cls="btn btn-sm btn-ghost mt-2",
            )
            if report_uid
            else None,
            cls="alert alert-success",
        ),
        id="upload-status",
    )


_get_status_badge_class = get_submission_status_badge_class


def _get_report_identifier(report: Any) -> str:
    """Extract the identifier from report metadata."""
    metadata = getattr(report, "metadata", None)
    if isinstance(metadata, dict):
        identifier = metadata.get("identifier")
        if identifier:
            return str(identifier)
    return getattr(report, "report_type", "unknown")


def _render_report_card(report: Any) -> Any:
    """Render a single report card for the AI reports grid."""
    file_size_mb = (report.file_size / 1024 / 1024) if getattr(report, "file_size", 0) else 0
    identifier = _get_report_identifier(report)

    # Check if je_output file exists in metadata
    metadata = getattr(report, "metadata", None)
    has_je_output = False
    if isinstance(metadata, dict):
        je_output_path = metadata.get("je_output_path")
        has_je_output = bool(je_output_path)

    # Build action buttons
    action_buttons = [
        A(
            "View",
            href=f"/submissions/{report.uid}",
            cls="btn btn-sm btn-ghost",
        ),
    ]

    # Add download button for completed reports with je_output
    if has_je_output and report.status == "completed":
        action_buttons.append(
            A(
                "Download",
                href=f"/journals/{report.uid}/download",
                cls="btn btn-sm btn-primary",
            )
        )

    return Div(
        Div(
            Div(
                Div(
                    H4(report.original_filename, cls="mb-0 font-semibold"),
                    P(
                        f"{identifier} \u2022 {file_size_mb:.2f} MB",
                        cls="text-sm text-base-content/60 mb-0",
                    ),
                    cls="flex-1",
                ),
                Div(
                    Span(
                        report.status,
                        cls=f"badge {_get_status_badge_class(report.status)}",
                    ),
                ),
                Div(
                    *action_buttons,
                    cls="flex gap-2",
                ),
                cls="flex items-center gap-4",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_reports_grid(reports: list[Any]) -> Any:
    """Render reports grid as HTML fragment for HTMX swap."""
    if not reports:
        return Div(
            P("No journals found.", cls="text-center text-base-content/60"),
            id="submissions-grid-container",
        )

    return Div(
        *[_render_report_card(r) for r in reports],
        id="submissions-grid-container",
    )


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

JOURNALS_SIDEBAR_ITEMS = [
    SidebarItem("New Entry", "/journals/submit", "submit", icon="📤"),
    SidebarItem("My Journals", "/journals/browse", "browse", icon="📄"),
]


# ============================================================================
# CONTENT FRAGMENTS
# ============================================================================


def _render_instruction_card(ex: Any, is_first: bool = False) -> Any:
    """Render one saved instruction file as a selectable card."""
    uid = getattr(ex, "uid", "")
    title = getattr(ex, "title", "Unnamed")
    created_at = getattr(ex, "created_at", None)

    if isinstance(created_at, datetime):
        date_str = created_at.strftime("%b %d, %Y")
    elif isinstance(created_at, str) and created_at:
        date_str = created_at[:10]
    else:
        date_str = ""

    selected_cls = "ring-2 ring-primary bg-base-200" if is_first else ""
    return Div(
        Div(
            Span(title, cls="text-sm font-semibold truncate"),
            Span(date_str, cls="text-xs text-base-content/60 shrink-0 ml-2"),
            cls="flex items-center justify-between",
        ),
        cls=f"instruction-card border border-base-300 rounded-lg p-3 cursor-pointer hover:bg-base-200 transition-colors {selected_cls}",
        **{
            "data-uid": uid,
            "onclick": f"selectInstruction('{uid}', this)",
        },
    )


def _exercise_created_at(exercise: Any) -> str:
    return getattr(exercise, "created_at", "") or ""


def _render_instruction_list(exercises: list[Any], error: str | None = None) -> Any:
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
        parts.append(P("No saved instruction files yet.", cls="text-sm text-base-content/60"))

    return Div(*parts, id="instruction-file-list", cls="space-y-2")


def _render_upload_form(exercises: list[Any] | None = None) -> Any:
    """Render the file upload form — title + instruction selector + file."""
    exercises = exercises or []
    return Div(
        Div(
            # x-data on card-body so both Form and instruction file picker share scope
            Div(
                Form(
                    # Title input (optional — auto-generated if left blank)
                    Div(
                        Label("Title (optional)", cls="label"),
                        Input(
                            type="text",
                            name="title",
                            placeholder="Leave blank to auto-generate (e.g. Journal — mike — Mar 02, 2026 — #1)",
                            cls="input input-bordered w-full",
                        ),
                        P(
                            "Leave blank to use the auto-generated title",
                            cls="text-xs text-base-content/60 mt-1",
                        ),
                        cls="mb-4",
                    ),
                    # Hidden exercise_uid — set by selectInstruction() JS, cleared on default mode
                    Input(type="hidden", name="exercise_uid", id="exercise-uid-input", value=""),
                    # Processing instructions section
                    Div(
                        Label("Processing Instructions", cls="label"),
                        Div(
                            # Default radio
                            Label(
                                Input(
                                    type="radio",
                                    name="instruction_mode",
                                    value="default",
                                    cls="radio radio-sm",
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
                                Input(
                                    type="radio",
                                    name="instruction_mode",
                                    value="custom",
                                    cls="radio radio-sm",
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
                                    cls="btn btn-sm btn-outline mb-3",
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
                                cls="text-sm text-base-content/60 text-center mt-0",
                                id="file-label-hint",
                            ),
                            cls="p-4 text-center bg-base-200 rounded-lg cursor-pointer border-2 border-dashed border-base-300",
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
                    **{
                        "hx-post": "/journals/upload",
                        "hx-target": "#upload-status",
                        "hx-swap": "outerHTML",
                        "hx-encoding": "multipart/form-data",
                    },
                    id="upload-form",
                ),
                # Instruction file picker — sibling of Form, shares Alpine scope from card-body
                Input(
                    type="file",
                    id="instruction-file-picker",
                    name="instruction_file",
                    cls="hidden",
                    accept=".txt,.md,.rst,text/plain,text/markdown",
                    **{
                        "hx-post": "/journals/instructions/upload",
                        "hx-target": "#instruction-file-list",
                        "hx-swap": "outerHTML",
                        "hx-encoding": "multipart/form-data",
                        "hx-trigger": "change",
                    },
                ),
                cls="card-body",
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
            cls="card bg-base-100 shadow-sm hover:shadow-md transition-shadow",
        ),
    )


def _upload_form_script() -> Any:
    """HTMX event handlers and helpers for the journal upload form."""
    return Script(
        NotStr("""
        // Global: highlight selected instruction card and store its uid
        function selectInstruction(uid, el) {
            document.querySelectorAll('.instruction-card').forEach(function(c) {
                c.classList.remove('ring-2', 'ring-primary', 'bg-base-200');
            });
            if (el) el.classList.add('ring-2', 'ring-primary', 'bg-base-200');
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
    return Div(
        Div(
            Form(
                Div(
                    Label("Status", cls="label"),
                    Select(
                        Option("All Status", value="", selected=True),
                        Option("Submitted", value="submitted"),
                        Option("Queued", value="queued"),
                        Option("Processing", value="processing"),
                        Option("Completed", value="completed"),
                        Option("Failed", value="failed"),
                        name="status",
                        cls="select select-bordered w-full",
                    ),
                    cls="mb-2",
                ),
                **{
                    "hx-get": "/journals/grid",
                    "hx-target": "#submissions-grid-container",
                    "hx-swap": "outerHTML",
                    "hx-trigger": "change from:select",
                },
                id="filter-form",
            ),
            cls="card-body",
        ),
        cls="card bg-base-100 shadow-sm mb-6",
    )


def _render_reports_grid_container() -> Any:
    """Render the HTMX-loading reports grid container."""
    return Div(
        P("Loading AI reports...", cls="text-center text-base-content/60"),
        id="submissions-grid-container",
        cls="mt-4",
        **{
            "hx-get": "/journals/grid",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_journals_ui_routes(
    _app,
    rt,
    report_service,
    processing_service,
    report_projects_service,
    user_service=None,
    journal_generator=None,
    submissions_core_service=None,
):
    """
    Create journal UI routes — available to all authenticated users.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        report_service: SubmissionsService
        processing_service: SubmissionsProcessingService
        report_projects_service: ExerciseService (optional — enables custom instructions)
        user_service: UserService for admin role checks
        journal_generator: JournalOutputGenerator for cleanup operations
        submissions_core_service: SubmissionsCoreService (optional — enables auto-title generation)
    """

    logger.info("Creating Journals UI routes")

    def get_user_service():
        """Get user service for role checks."""
        return user_service

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

        exercises: list[Any] = []
        if report_projects_service:
            ex_result = await report_projects_service.list_user_exercises(user_uid)
            if ex_result.is_ok:
                exercises = ex_result.value or []

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
        """Browse page: AI-processed reports with filters."""
        require_authenticated_user(request)

        content = Div(
            PageHeader("My Journals", subtitle="Browse your AI-processed journal entries"),
            _render_filters_section(),
            _render_reports_grid_container(),
        )
        return await SidebarPage(
            content=content,
            items=JOURNALS_SIDEBAR_ITEMS,
            active="browse",
            title="Journals",
            subtitle="Your personal journal",
            storage_key="journals-sidebar",
            page_title="AI Reports",
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

            # Resolve title: custom > auto-generated
            if custom_title:
                title = custom_title
            elif submissions_core_service:
                title_result = await submissions_core_service.generate_journal_title(user_uid)
                title = title_result.value if title_result.is_ok else filename
            else:
                title = filename

            # Resolve processing instructions: exercise overrides default
            exercise_uid = str(form.get("exercise_uid", "")).strip()
            instructions_text = DEFAULT_INSTRUCTIONS
            if exercise_uid and report_projects_service:
                ex_result = await report_projects_service.get_exercise(exercise_uid)
                if ex_result.is_ok and ex_result.value and ex_result.value.instructions:
                    instructions_text = ex_result.value.instructions
                    logger.info(f"Using exercise instructions: {exercise_uid}")

            logger.info(f"Journal upload: {filename} ({len(file_content)} bytes, title={title})")

            # Submit file with LLM processor type
            metadata: dict[str, Any] = {"project_uid": "__default__"}
            if exercise_uid:
                metadata["exercise_uid"] = exercise_uid

            result = await report_service.submit_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                entity_type=EntityType.JOURNAL_SUBMISSION,
                processor_type=ProcessorType.LLM,
                title=title,
                metadata=metadata,
            )

            if result.is_error:
                return _render_upload_status("error", str(result.error), is_error=True)

            report = result.value

            # Auto-trigger AI processing with resolved instructions
            # extract_activities=True enables DSL parsing: @context() tags → entities
            process_result = await processing_service.process_submission(
                report.uid,
                instructions={
                    "custom_instructions": instructions_text,
                    "extract_activities": True,  # Enable DSL entity extraction
                },
            )

            if process_result.is_error:
                error_msg = "File uploaded but AI processing failed"
                if process_result.error:
                    error_msg = f"{error_msg}: {process_result.error.user_message or process_result.error.message}"
                logger.warning(f"AI processing failed for {report.uid}: {error_msg}")
                return _render_upload_status(
                    status="submitted",
                    message=f"File uploaded. AI processing pending — {error_msg}",
                    report_uid=report.uid,
                )

            processed_report = process_result.value
            return _render_upload_status(
                status=processed_report.status if processed_report else "completed",
                message="File uploaded and processed by AI",
                report_uid=report.uid,
            )

        except Exception as e:
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

            if report_projects_service:
                create_result = await report_projects_service.create_exercise(
                    user_uid=user_uid,
                    name=filename,
                    instructions=instructions_text,
                )
                if create_result.is_error:
                    logger.warning(f"Failed to save instruction file: {create_result.error}")

            # Fetch updated list and return refreshed fragment
            exercises: list[Any] = []
            if report_projects_service:
                ex_result = await report_projects_service.list_user_exercises(user_uid)
                if ex_result.is_ok:
                    exercises = ex_result.value or []

            logger.info(f"Instruction file saved for {user_uid}: {filename}")
            return _render_instruction_list(exercises)

        except Exception as e:
            logger.error(f"Error saving instruction file: {e}", exc_info=True)
            return _render_instruction_list([], error=str(e))

    @rt("/journals/grid")
    async def get_journals_grid(request: Request) -> Any:
        """HTMX endpoint for loading AI-processed reports grid."""
        try:
            user_uid = require_authenticated_user(request)
            status = request.query_params.get("status", "")

            kwargs: dict[str, Any] = {"user_uid": user_uid, "limit": 50}
            if status:
                kwargs["status"] = status

            result = await report_service.list_submissions(**kwargs)

            if result.is_error:
                return Div(
                    P("Failed to load reports", cls="text-center text-error"),
                    id="submissions-grid-container",
                )

            reports = result.value or []
            # Filter to LLM-processed reports
            ai_reports = [
                r
                for r in reports
                if getattr(r, "processor_type", None) in ("llm", "LLM", ProcessorType.LLM)
            ]
            return _render_reports_grid(ai_reports)

        except Exception as e:
            logger.error(f"Error loading AI reports: {e}", exc_info=True)
            return Div(
                P(f"Error: {e}", cls="text-center text-error"),
                id="submissions-grid-container",
            )

    @rt("/journals/{uid}/download")
    async def download_je_output(request: Request, uid: str) -> Any:
        """Download formatted je_output file for a journal report.

        Returns:
            FileResponse with markdown file or error response
        """
        try:
            user_uid = require_authenticated_user(request)

            # Fetch the report
            result = await report_service.get_submission(uid)

            if result.is_error:
                logger.warning(f"Report {uid} not found for download")
                return Div(
                    P("Report not found", cls="text-center text-error"),
                )

            report = result.value

            # Verify ownership
            if report.user_uid != user_uid:
                logger.warning(
                    f"User {user_uid} attempted to download report {uid} owned by {report.user_uid}"
                )
                return Div(
                    P("Not authorized to download this report", cls="text-center text-error"),
                )

            # Check for je_output_path in metadata
            metadata = getattr(report, "metadata", None)
            if not isinstance(metadata, dict):
                logger.warning(f"Report {uid} has no metadata")
                return Div(
                    P("No je_output file available for this report", cls="text-center text-error"),
                )

            je_output_path = metadata.get("je_output_path")
            if not je_output_path:
                logger.warning(f"Report {uid} has no je_output_path in metadata")
                return Div(
                    P("No je_output file available for this report", cls="text-center text-error"),
                )

            # Verify file exists
            je_output_file = Path(je_output_path)
            if not je_output_file.exists():
                logger.error(f"je_output file not found at {je_output_path} for report {uid}")
                return Div(
                    P("je_output file not found on disk", cls="text-center text-error"),
                )

            # Return file for download
            logger.info(f"Serving je_output download for report {uid}: {je_output_path}")
            return FileResponse(
                path=str(je_output_file),
                filename=f"{report.original_filename}_output.md",
                media_type="text/markdown",
            )

        except Exception as e:
            logger.error(f"Error downloading je_output for {uid}: {e}", exc_info=True)
            return Div(
                P(f"Download failed: {e}", cls="text-center text-error"),
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
        if not journal_generator:
            return Result.fail(
                Errors.system(
                    message="Journal generator service not available",
                    service="journal_generator",
                )
            )

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

        result = journal_generator.cleanup_date_range(start_dt, end_dt)

        if result.is_error:
            return Result.fail(result.expect_error())

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
        upload_journal,
        upload_instruction_file,
        get_journals_grid,
        download_je_output,
        cleanup_je_outputs,
    ]
