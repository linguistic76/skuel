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
    Div,
    NotStr,
    P,
    Script,
)
from starlette.datastructures import UploadFile
from starlette.responses import FileResponse

from adapters.inbound.auth import require_admin, require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.models.enums.entity_enums import EntityStatus
from core.models.exercises.exercise import Exercise
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory, Errors, Result
from ui.journals.cards import render_instruction_list, render_journals_grid
from ui.journals.components import (
    render_batch_directories_card,
    render_batch_processing_card,
    render_filters_section,
    render_journals_grid_container,
    render_upload_status,
)
from ui.journals.forms import render_upload_form, upload_form_script
from ui.patterns.error_banner import render_inline_error
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

logger = get_logger("skuel.routes.journals.ui")


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

JOURNALS_SIDEBAR_ITEMS = [
    SidebarItem("New Entry", "/journals/submit", "submit", icon="📤"),
    SidebarItem("My Journals", "/journals/browse", "browse", icon="📄"),
    SidebarItem("Batch Ops", "/journals/batch", "batch", icon="📦"),
]


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
            render_upload_form(exercises),
            upload_form_script(),
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
            render_filters_section(),
            render_journals_grid_container(),
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
                return render_upload_status("error", "No file provided", is_error=True)

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
                return render_upload_status("error", str(result.error), is_error=True)

            je_input = result.value
            return render_upload_status(
                str(je_input.status.value)
                if isinstance(je_input.status, EntityStatus)
                else str(je_input.status),
                f"Journal entry created: {je_input.title}",
                je_input_uid=je_input.uid,
            )

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error uploading journal: {e}", exc_info=True)
            return render_upload_status("error", f"Upload failed: {e}", is_error=True)

    @rt("/journals/instructions/upload")
    async def upload_instruction_file(request: Request) -> Any:
        """HTMX endpoint: save an instruction text file, return updated card list."""
        try:
            user_uid = require_authenticated_user(request)
            form = await request.form()
            uploaded_file = form.get("instruction_file")

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return render_instruction_list([], error="No file provided")

            file_bytes = await uploaded_file.read()
            try:
                instructions_text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return render_instruction_list([], error="File must be plain text (UTF-8)")

            if not instructions_text.strip():
                return render_instruction_list([], error="File is empty")

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
            return render_instruction_list(exercises)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error saving instruction file: {e}", exc_info=True)
            return render_instruction_list([], error=str(e))

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
            return render_journals_grid(je_inputs)

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
            render_batch_directories_card(),
            render_batch_processing_card(),
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
