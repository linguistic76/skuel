"""
UserEntry UI Routes (ADR-054)
=============================

The single UI route file for the unified UserEntry hub. Replaced the legacy
``submissions_ui``, ``submissions_hub_routes``, and ``journals_ui`` surfaces.

Routes:
- GET  /submit                           — Exercise worksheet upload form
- GET  /gradebook/{uid}                  — Submission detail page
- GET  /submissions/history              — Submission history
- GET  /submissions/history/list         — HTMX fragment refresh
- POST /submissions/history/delete       — HTMX row delete
- GET  /api/submissions/upload/preview   — HTMX hub preview (upload)
- GET  /api/submissions/submit/preview   — HTMX hub preview (submit)
- GET  /api/submissions/journal/preview  — HTMX hub preview (journal CTA)
- GET  /api/submissions/history/preview  — HTMX hub preview (history)
- GET  /journals/submit                  — Journal upload form
- GET  /journals/browse                  — Journal entry grid
- POST /journals/upload                  — HTMX journal multipart upload
- GET  /journals/{uid}/download          — Ownership-verified download

All writes go through ``UserEntryService.submit_file``. All reads go through
``UserEntryOrchestrator``.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fasthtml.common import H4, Div, P, Span
from starlette.datastructures import UploadFile
from starlette.responses import FileResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody, CardHeader, CardTitle
from ui.feedback import Badge, BadgeT, StatusBadge
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.journals.components import render_upload_status as render_journal_upload_status
from ui.journals.forms import render_upload_form as render_journal_upload_form
from ui.layout import Size
from ui.learning_loop.report import render_yours_list
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner, render_inline_error
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.page_header import PageHeader
from ui.user_entry.forms import render_upload_form, upload_form_script
from ui.workbench.nav import render_submissions_sidebar_page

if TYPE_CHECKING:
    from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator
    from core.services.groups.group_service import GroupService
    from core.services.report.entry_report_service import EntryReportService
    from core.services.user_entry.user_entry_service import UserEntryService

logger = get_logger("skuel.routes.user_entry.ui")


def _status_value(entry: UserEntry) -> str:
    status = entry.status
    if isinstance(status, EntityStatus):
        return status.value
    return str(status) if status else "submitted"


# Pipelines whose entries are journal-chain reflections eligible for an LLM
# reflective response (ADR-069). NONE-pipeline TRANSFORMS children are also
# eligible but require a graph check; the service validates that case on POST.
_RESPONSE_BUTTON_PIPELINES = frozenset(
    {Pipeline.EXTRACT_ACTIVITIES, Pipeline.TRANSCRIBE_AND_STRUCTURE}
)


def _render_entry_responses(responses: list[dict[str, Any]]) -> Any:
    """Render the "Responses" section for an entry detail page (ADR-069).

    HTMX swap target ``#entry-responses`` — re-rendered after a new response is
    generated. Each item links to the full report at ``/entry-reports/detail``.
    """
    if responses:
        body: Any = Div(
            *[
                Div(
                    Span(str(r.get("title") or "Response"), cls="font-medium text-sm"),
                    Span(
                        f" · {str(r.get('processor_type') or '').upper()}",
                        cls="text-xs text-muted-foreground ml-1",
                    ),
                    ButtonLink(
                        "View",
                        href=f"/entry-reports/detail?uid={r.get('uid')}",
                        variant=ButtonT.ghost,
                        size=Size.sm,
                    ),
                    cls="flex items-center justify-between p-2 border-b border-border",
                )
                for r in responses
                if r.get("uid")
            ]
        )
    else:
        body = P("No responses yet.", cls="text-sm text-muted-foreground")

    return Div(
        H4("Responses", cls="mb-3"),
        body,
        id="entry-responses",
        cls="mt-6",
    )


def _render_respond_button(entry_uid: str) -> Any:
    """Button that requests a reflective LLM response for a journal entry."""
    return Button(
        "Get a reflective response",
        variant=ButtonT.secondary,
        size=Size.sm,
        hx_post="/api/entry-reports/respond",
        hx_vals=json.dumps({"entry_uid": entry_uid}),
        hx_target="#entry-responses",
        hx_swap="outerHTML",
        hx_disabled_elt="this",
        cls="mt-4",
    )


def _render_awaiting_response_section(entries: list[UserEntry]) -> Any:
    """Render the "Awaiting a response" list on the journals browse page.

    Empty (renders nothing) when every journal entry already has a response.
    Each item links to the entry detail page where the response can be requested.
    """
    if not entries:
        return Div()
    return Card(
        CardHeader(CardTitle("Awaiting a response")),
        CardBody(
            *[
                Div(
                    Span(e.title or "Untitled entry", cls="font-medium text-sm"),
                    ButtonLink(
                        "Open",
                        href=f"/gradebook/{e.uid}",
                        variant=ButtonT.ghost,
                        size=Size.sm,
                    ),
                    cls="flex items-center justify-between p-2 border-b border-border",
                )
                for e in entries
            ]
        ),
        cls="mb-6 bg-background shadow-sm",
    )


def _to_history_dict(entry: UserEntry) -> dict[str, Any]:
    """Adapt a ``UserEntry`` to the dict shape ``render_yours_list`` expects."""
    return {
        "uid": entry.uid,
        "title": entry.title,
        "original_filename": entry.original_filename,
        "status": _status_value(entry),
        "feedback_count": 0,
        "created_at": entry.created_at,
    }


def _render_user_entry_journal_card(entry: UserEntry) -> Any:
    """Render a journal ``UserEntry`` card for the browse grid."""
    file_size = entry.file_size or 0
    file_size_mb = file_size / 1024 / 1024 if file_size else 0

    meta_parts: list[str] = []
    if entry.original_filename:
        meta_parts.append(entry.original_filename)
    if file_size_mb > 0:
        meta_parts.append(f"{file_size_mb:.2f} MB")
    if entry.file_type:
        meta_parts.append(entry.file_type)

    status_str = _status_value(entry)

    action_buttons: list[Any] = []
    if entry.status == EntityStatus.COMPLETED:
        action_buttons.append(
            ButtonLink(
                "Download",
                href=f"/journals/{entry.uid}/download",
                variant=ButtonT.primary,
                size=Size.sm,
            )
        )

    return CardGenerator.from_dataclass(
        {"title": entry.title or "Untitled"},
        display_fields=[],
        header_badges=[StatusBadge(status_str) if status_str else None],
        show_labels=False,
        metadata=[" \u2022 ".join(meta_parts)] if meta_parts else None,
        actions=Div(*action_buttons, cls="flex gap-2") if action_buttons else None,
        card_attrs={"cls": "mb-2"},
    )


def _render_user_entry_journal_grid(entries: list[UserEntry]) -> Any:
    if not entries:
        return Div(EmptyState(title="No journals found"), id="journals-grid-container")
    return Div(
        *[_render_user_entry_journal_card(e) for e in entries],
        id="journals-grid-container",
    )


def create_user_entry_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    user_entry_service: UserEntryService,
    *,
    orchestrator: UserEntryOrchestrator | None = None,
    entry_report_service: EntryReportService | None = None,
    groups_service: GroupService | None = None,
) -> list[Any]:
    """Register the UserEntry UI routes.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        user_entry_service: Primary ``UserEntryService`` (writes)
        orchestrator: ``UserEntryOrchestrator`` (reads across related services)
        entry_report_service: Used to guard delete when feedback exists
        groups_service: ``GroupService`` used by ``/submit`` to enumerate the
            student's own groups for the audience radio selector.
    """
    if user_entry_service is None:
        raise RuntimeError("UserEntryService is required — check bootstrap wiring")
    if orchestrator is None:
        raise RuntimeError("UserEntryOrchestrator is required — check bootstrap wiring")

    logger.info("Creating UserEntry UI routes")

    # =========================================================================
    # SUBMIT
    # =========================================================================

    @rt("/submit")
    async def submit_page(request: Request) -> Any:
        """Exercise worksheet upload form."""
        user_uid = require_authenticated_user(request)

        assigned_exercises: list[Any] = []
        exercises_result = await orchestrator.get_student_exercises(user_uid)
        if not exercises_result.is_error and exercises_result.value:
            assigned_exercises = exercises_result.value

        user_groups: list[Any] = []
        if groups_service is not None:
            groups_result = await groups_service.get_user_groups(user_uid)
            if not groups_result.is_error and groups_result.value:
                user_groups = groups_result.value

        selected_exercise_uid = request.query_params.get("exercise_uid")
        from_ps = request.query_params.get("from_ps") or None

        content = Div(
            PageHeader("Submit", subtitle="Upload your completed exercise worksheet"),
            render_upload_form(
                assigned_exercises,
                selected_exercise_uid=selected_exercise_uid,
                from_ps=from_ps,
                user_groups=user_groups,
            ),
            upload_form_script(),
        )
        return await render_submissions_sidebar_page(
            content=content,
            active="submit",
            request=request,
        )

    # =========================================================================
    # /submissions (hub root) is now a tab on /profile?tab=submissions.
    # Detail routes and the /api/submissions/* preview endpoints below
    # remain — the Submissions tab and the upload/submit flows reuse them.
    # =========================================================================

    @rt("/api/submissions/upload/preview")
    async def upload_preview(request: Request) -> Any:
        """HTMX preview: upload form embedded directly in the hub block."""
        require_authenticated_user(request)
        from adapters.inbound.upload_ui import _results_area, _upload_form

        return Div(_upload_form(), _results_area())

    @rt("/api/submissions/submit/preview")
    async def submit_preview(request: Request) -> Any:
        """HTMX preview: pending exercises to submit."""
        require_authenticated_user(request)
        return HubPreviewEmpty("submissions")

    @rt("/api/submissions/journal/preview")
    async def journal_preview(request: Request) -> Any:
        """HTMX preview: short CTA describing the journal pipeline."""
        require_authenticated_user(request)
        return Div(
            P(
                "Upload audio, video, or text — AI transcribes and structures it into a journal entry.",
                cls="text-sm text-muted-foreground",
            ),
        )

    @rt("/api/submissions/history/preview")
    async def history_preview(request: Request) -> Any:
        """HTMX preview: 3 most recent teacher-review entries."""
        user_uid = require_authenticated_user(request)
        result = await orchestrator.list_exercise_entries(user_uid, limit=3)
        if result.is_error:
            return HubPreviewEmpty("submissions")
        entries = result.value or []
        if not entries:
            return HubPreviewEmpty("submissions")
        cards = []
        for entry in entries[:3]:
            status = _status_value(entry).replace("_", " ").title()
            badge = (
                Span(status, cls="text-[10px] font-medium text-muted-foreground")
                if status
                else None
            )
            cards.append(
                HubPreviewCard(
                    title=entry.title or "Untitled",
                    href=f"/gradebook/{entry.uid}",
                    badge=badge,
                )
            )
        return HubPreviewGrid(cards)

    # =========================================================================
    # SUBMISSION HISTORY
    # =========================================================================

    @rt("/submissions/history")
    async def submissions_history(request: Request) -> Any:
        """Submission history page."""
        user_uid = require_authenticated_user(request)

        submissions_content: Any
        result = await orchestrator.list_exercise_entries(user_uid)
        if result.is_error:
            logger.error(f"Error loading submissions history: {result.error}")
            submissions_content = render_error_banner(
                "Failed to load submissions", str(result.error)
            )
        else:
            items = [_to_history_dict(e) for e in (result.value or [])]
            if items:
                submissions_content = render_yours_list(items)
            else:
                submissions_content = EmptyState(
                    title="No submissions yet",
                    description="Submit your first exercise to see it here.",
                )

        content = Div(
            PageHeader(
                "Submission History",
                subtitle="Your submitted exercises and feedback status",
            ),
            submissions_content,
        )
        return await render_submissions_sidebar_page(
            content=content,
            active="history",
            request=request,
        )

    @rt("/submissions/history/list")
    async def history_list(request: Request) -> Any:
        """HTMX fragment: refreshed submissions list."""
        try:
            user_uid = require_authenticated_user(request)
            result = await orchestrator.list_exercise_entries(user_uid)
            if result.is_error:
                logger.error(f"Error loading submissions history: {result.error}")
                return Div(
                    render_error_banner("Failed to load submissions", str(result.error)),
                    id="submissions-yours-list",
                )
            items = [_to_history_dict(e) for e in (result.value or [])]
            return render_yours_list(items)
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading submissions history: {e}", exc_info=True)
            return Div(
                render_error_banner("Error loading submissions", str(e)),
                id="submissions-yours-list",
            )

    @rt("/submissions/history/delete", methods=["POST"])
    @csrf_protected
    async def delete_submission(request: Request, uid: str) -> Any:
        """Delete a user-owned UserEntry (blocked when feedback exists)."""
        user_uid = require_authenticated_user(request)

        entry_result = await orchestrator.get_entry(uid, user_uid)
        if entry_result.is_error or entry_result.value is None:
            return render_error_banner("Submission not found")

        if entry_report_service is not None:
            history_result = await entry_report_service.list_for_submission(uid)
            if not history_result.is_error and history_result.value:
                return render_error_banner("Cannot delete a submission that has received feedback")

        delete_result = await orchestrator.delete_entry(uid, user_uid)
        if delete_result.is_error:
            return render_error_banner("Failed to delete submission", str(delete_result.error))

        return Div()

    # =========================================================================
    # JOURNALS
    # =========================================================================

    @rt("/journals/submit")
    async def journals_submit_page(request: Request) -> Any:
        """Journal upload form."""
        user_uid = require_authenticated_user(request)

        exercises: list[Any] = []
        ex_result = await orchestrator.list_user_exercises(user_uid)
        if ex_result.is_ok:
            exercises = ex_result.value or []

        from ui.layouts.base_page import BasePage

        content = Div(
            PageHeader(
                "New Journal Entry",
                subtitle="Upload a file to be processed by AI",
                actions=ButtonLink(
                    "Browse my journals",
                    href="/journals/browse",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                ),
            ),
            render_journal_upload_form(exercises),
        )
        return await BasePage(
            content=content,
            title="Journals",
            request=request,
            active_page="journals",
        )

    @rt("/journals/browse")
    async def journals_browse_page(request: Request) -> Any:
        """Browse the user's journal entries."""
        user_uid = require_authenticated_user(request)

        entries: list[UserEntry] = []
        result = await orchestrator.list_journal_entries(user_uid)
        if not result.is_error and result.value:
            entries = list(result.value)

        # Journal-chain entries with no response yet — wires
        # get_pending_submissions(pipelines=[...]) (ADR-069).
        awaiting_result = await orchestrator.get_entries_awaiting_response(user_uid)
        awaiting_uids = set(awaiting_result.value or []) if awaiting_result.is_ok else set()
        awaiting_entries = [e for e in entries if e.uid in awaiting_uids]

        from ui.layouts.base_page import BasePage

        content = Div(
            PageHeader(
                "My Journals",
                subtitle="Browse your AI-processed journal entries",
                actions=ButtonLink(
                    "New Journal",
                    href="/journals/submit",
                    variant=ButtonT.primary,
                    size=Size.sm,
                ),
            ),
            _render_awaiting_response_section(awaiting_entries),
            _render_user_entry_journal_grid(entries),
        )
        return await BasePage(
            content=content,
            title="Journals",
            request=request,
            active_page="journals",
        )

    @rt("/journals/upload")
    @csrf_protected
    async def upload_journal(request: Request) -> Any:
        """HTMX endpoint for journal file upload (TRANSCRIBE_AND_STRUCTURE)."""
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            raw_title = form.get("title")
            custom_title = str(raw_title).strip() if raw_title else ""

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return render_journal_upload_status("error", "No file provided", is_error=True)

            user_uid = require_authenticated_user(request)
            file_content = await uploaded_file.read()
            filename = uploaded_file.filename or "unknown"
            title = custom_title or filename

            result = await user_entry_service.submit_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
                title=title,
                metadata={"custom_title": custom_title} if custom_title else None,
            )

            if result.is_error:
                return render_journal_upload_status("error", str(result.error), is_error=True)

            entry, _outcome = result.value
            return render_journal_upload_status(
                _status_value(entry),
                f"Journal entry created: {entry.title}",
                je_input_uid=entry.uid,
            )

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error uploading journal: {e}", exc_info=True)
            return render_journal_upload_status("error", f"Upload failed: {e}", is_error=True)

    @rt("/journals/{uid}/download")
    async def download_journal(request: Request, uid: str) -> Any:
        """Ownership-verified download of a journal entry's source file."""
        try:
            user_uid = require_authenticated_user(request)
            entry_result = await orchestrator.get_entry(uid, user_uid)
            if entry_result.is_error or entry_result.value is None:
                return render_inline_error("Journal entry not found")

            entry = entry_result.value
            if not entry.file_path or not Path(entry.file_path).exists():
                logger.warning(f"Journal file not found on disk for entry {uid}")
                return render_inline_error("File not available")

            media_type = (
                entry.file_type
                or mimetypes.guess_type(entry.original_filename or entry.file_path)[0]
                or "application/octet-stream"
            )
            download_name = entry.original_filename or Path(entry.file_path).name
            return FileResponse(
                path=entry.file_path,
                filename=download_name,
                media_type=media_type,
            )

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error downloading journal {uid}: {e}", exc_info=True)
            return Div(P(f"Download failed: {e}", cls="text-center text-error"))

    @rt("/api/entry-reports/respond", methods=["POST"])
    @csrf_protected
    async def respond_to_entry(request: Request, entry_uid: str = "") -> Any:
        """Generate an LLM reflective response to the user's own journal entry.

        Owner-only (the orchestrator/service does the ownership-verified fetch
        and returns not-found for entries the user does not own). Returns the
        re-rendered ``#entry-responses`` section so the new response appears
        in place (HTMX outerHTML swap).
        """
        user_uid = require_authenticated_user(request)
        entry_uid = (entry_uid or "").strip()
        if not entry_uid:
            return render_inline_error("Missing entry_uid")

        result = await orchestrator.generate_entry_response(entry_uid, user_uid)
        if result.is_error:
            existing = await orchestrator.get_entry_responses(entry_uid)
            return Div(
                render_inline_error(result.expect_error().message),
                _render_entry_responses(existing.value if existing.is_ok else []),
                id="entry-responses",
            )

        responses_result = await orchestrator.get_entry_responses(entry_uid)
        responses = responses_result.value if responses_result.is_ok else []
        return _render_entry_responses(responses)

    # =========================================================================
    # GRADEBOOK DETAIL — MUST BE LAST (catch-all pattern)
    # =========================================================================

    @rt("/gradebook/{uid}")
    async def submission_detail(request: Request, uid: str) -> Any:
        """Submission detail page rendered from a ``UserEntry``."""
        user_uid = require_authenticated_user(request)

        entry_result = await orchestrator.get_entry(uid, user_uid)
        if entry_result.is_error or entry_result.value is None:
            content = Div(
                PageHeader("Submission Not Found", subtitle=f"UID: {uid}"),
                render_inline_error("Submission not found"),
            )
            return await render_gradebook_sidebar_page(
                content=content,
                active="submissions",
                request=request,
            )

        entry = entry_result.value
        body_text = entry.processed_content or entry.content or ""

        fulfills_uid = (entry.metadata or {}).get("fulfills_exercise_uid")
        exercise_link: Any = None
        if fulfills_uid:
            exercise_link = Div(
                Span("Exercise: ", cls="font-medium text-sm text-muted-foreground"),
                Badge(str(fulfills_uid), variant=BadgeT.outline, size=Size.sm),
                cls="mb-4",
            )

        detail_card = Card(
            CardHeader(CardTitle("Submission Details")),
            CardBody(
                P(
                    f"Status: {_status_value(entry).replace('_', ' ').title()}",
                    cls="text-sm text-muted-foreground mb-2",
                ),
                P(
                    f"Filename: {entry.original_filename or '—'}",
                    cls="text-sm text-muted-foreground mb-2",
                ),
                exercise_link,
                H4("Processed Content", cls="mt-6 mb-4"),
                Div(
                    P(body_text, cls="whitespace-pre-wrap text-sm")
                    if body_text
                    else P(
                        "No processed content yet.",
                        cls="text-sm text-muted-foreground",
                    ),
                    cls="p-4 bg-muted rounded-lg",
                    style="max-height: 600px; overflow-y: auto;",
                ),
                Div(
                    ButtonLink(
                        "\u2190 Back to Submission History",
                        href="/submissions/history",
                        variant=ButtonT.ghost,
                    ),
                    cls="mt-4",
                ),
            ),
            cls="bg-background shadow-sm",
        )

        # Responses section (ADR-069) — EntryReports pointing at this entry,
        # via ReportRelationshipService.get_submission_chain.
        responses_result = await orchestrator.get_entry_responses(uid)
        responses = responses_result.value if responses_result.is_ok else []
        respond_button: Any = (
            _render_respond_button(uid) if entry.pipeline in _RESPONSE_BUTTON_PIPELINES else None
        )

        content = Div(
            PageHeader(entry.title or "Submission Details", subtitle=f"UID: {uid}"),
            detail_card,
            respond_button,
            _render_entry_responses(responses),
        )

        return await render_gradebook_sidebar_page(
            content=content,
            active="submissions",
            request=request,
        )

    logger.info("UserEntry UI routes created successfully")

    return [
        submit_page,
        upload_preview,
        submit_preview,
        journal_preview,
        history_preview,
        submissions_history,
        history_list,
        delete_submission,
        journals_submit_page,
        journals_browse_page,
        upload_journal,
        download_journal,
        respond_to_entry,
        submission_detail,  # MUST BE LAST — catch-all /gradebook/{uid}
    ]


__all__ = ["create_user_entry_ui_routes"]
