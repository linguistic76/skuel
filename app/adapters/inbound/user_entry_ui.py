"""
UserEntry UI Routes (ADR-054)
=============================

The single UI route file for the unified UserEntry hub. Replaced the legacy
``submissions_ui``, ``submissions_hub_routes``, and ``journals_ui`` surfaces.

Routes:
- GET  /submissions                      — MOC root: links to all 4 sub-pages (no sidebar)
- GET  /submissions/exercise             — Exercise worksheet upload form (canonical)
- GET  /submit                           — 302 redirect → /submissions/exercise (legacy)
- GET  /submissions/journal              — Journal file-upload UX (alternative to /journals)
- GET  /submit/journals/{uid}/download   — Ownership-verified download
- GET  /gradebook                        — MOC root: links to Entry Reports, Activity Reports, Revised Exercises
- GET  /gradebook/{uid}                  — Submission detail page
- GET  /submissions/history              — Submission history (4th sidebar slot)
- GET  /submissions/history/list         — HTMX fragment refresh
- POST /submissions/history/delete       — HTMX row delete
- GET  /api/submissions/submit/preview   — HTMX hub preview (submit)
- GET  /api/submissions/journal/preview  — HTMX hub preview (journal CTA)
- GET  /api/submissions/history/preview  — HTMX hub preview (history)

Journal upload routes (POST /journals/upload, POST /journals/folder-process,
GET /journals/browse) live in journals_routes.py. Those paths are
zero-persistence (ADR-073) — they process to je_out/ and write nothing. Reads
go through ``UserEntryOrchestrator``.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fasthtml.common import H2, H4, A, Div, P, Span
from starlette.responses import FileResponse, RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from adapters.inbound.result_helpers import require_found
from core.models.enums.entity_enums import EntityStatus
from core.models.user_entry.user_entry import UserEntry
from core.utils.logging import get_logger
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle, Icon
from ui.feedback import Badge, BadgeT
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.learning_loop.report import render_yours_list
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner, render_inline_error
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink
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
                        cls=ButtonT.ghost,
                        size="sm",
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
        cls=(ButtonT.secondary, "mt-4"),
        size="sm",
        hx_post="/api/entry-reports/respond",
        hx_vals=json.dumps({"entry_uid": entry_uid}),
        hx_target="#entry-responses",
        hx_swap="outerHTML",
        hx_disabled_elt="this",
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


def create_user_entry_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    user_entry_service: UserEntryService,
    *,
    orchestrator: UserEntryOrchestrator | None = None,
    entry_report_service: EntryReportService | None = None,
    groups_service: GroupService | None = None,
    batch_transcription_service: Any | None = None,
    processing_service: Any | None = None,
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
        batch_transcription_service: Retained for API compatibility (journal upload
            routes now live in journals_routes.py).
        processing_service: Retained for API compatibility (journal upload
            routes now live in journals_routes.py).
    """
    if user_entry_service is None:
        raise RuntimeError("UserEntryService is required — check bootstrap wiring")
    if orchestrator is None:
        raise RuntimeError("UserEntryOrchestrator is required — check bootstrap wiring")

    logger.info("Creating UserEntry UI routes")

    # =========================================================================
    # SUBMISSIONS MOC ROOT
    # =========================================================================

    @rt("/submissions")
    async def submissions_moc(request: Request) -> Any:
        """Submissions MOC — links to all 4 sub-pages, no sidebar."""
        require_authenticated_user(request)

        def _moc_card(
            title: str,
            description: str,
            href: str,
            icon: str,
            icon_bg: str = "bg-muted",
        ) -> Any:
            return A(
                Div(
                    Div(
                        Icon(icon, size=28),
                        cls=f"w-14 h-14 rounded-2xl {icon_bg} flex items-center justify-center mb-4",
                    ),
                    H2(title, cls="text-lg font-semibold mb-1"),
                    P(description, cls="text-sm text-muted-foreground"),
                    cls="p-6",
                ),
                href=href,
                cls=(
                    "block border border-border rounded-2xl bg-card "
                    "hover:border-primary/40 hover:shadow-md transition-all duration-150"
                ),
            )

        content = Div(
            PageHeader("Submissions", subtitle="Choose how you want to submit or sync your work"),
            Div(
                _moc_card(
                    "Exercise",
                    "Upload a completed exercise worksheet for teacher or AI feedback.",
                    "/submissions/exercise",
                    "send",
                    "bg-blue-50",
                ),
                _moc_card(
                    "Journal",
                    "Upload audio, text, or files to be transcribed and processed by AI.",
                    "/submissions/journal",
                    "book-open",
                    "bg-violet-50",
                ),
                _moc_card(
                    "Sync",
                    "Pull your Obsidian Daily Notes into SKUEL and write completions back.",
                    "/submissions/sync",
                    "refresh-cw",
                    "bg-emerald-50",
                ),
                _moc_card(
                    "History",
                    "Browse your past exercise submissions and feedback status.",
                    "/submissions/history",
                    "clock",
                    "bg-amber-50",
                ),
                cls="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6",
            ),
        )

        return await BasePage(
            content=content,
            title="Submissions",
            request=request,
            active_page="submissions",
        )

    # =========================================================================
    # SUBMIT — EXERCISE (canonical: /submissions/exercise; legacy: /submit)
    # =========================================================================

    async def _exercise_page(request: Request) -> Any:
        """Inner handler for the exercise upload form (shared by two routes)."""
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
            PageHeader("Submit Exercise", subtitle="Upload your completed exercise worksheet"),
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
            active="exercise",
            request=request,
        )

    @rt("/submissions/exercise")
    async def submissions_exercise_page(request: Request) -> Any:
        """Exercise worksheet upload form (canonical URL)."""
        return await _exercise_page(request)

    @rt("/submit")
    async def submit_redirect(request: Request) -> Any:
        """Legacy URL — redirect to canonical /submissions/exercise."""
        return RedirectResponse(url="/submissions/exercise", status_code=302)

    # =========================================================================
    # SUBMIT — JOURNAL UPLOAD UX (/submissions/journal)
    # =========================================================================

    @rt("/submissions/journal")
    async def submissions_journal_page(request: Request) -> Any:
        """Journal file-upload UX — alternative entry point to /journals."""
        require_authenticated_user(request)

        from ui.journals.forms import render_upload_form as render_journal_form
        from ui.journals.forms import upload_form_script as journal_script

        content = Div(
            PageHeader(
                "New Journal Entry",
                subtitle="Upload a file to be processed by AI",
            ),
            render_journal_form(),
            journal_script(),
        )
        return await render_submissions_sidebar_page(
            content=content,
            active="journal",
            request=request,
        )

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

        entry_result = require_found(await orchestrator.get_entry(uid, user_uid), "UserEntry", uid)
        if entry_result.is_error:
            return render_error_banner("Submission not found")

        # Fail closed: an entry that has received feedback must not be silently
        # lost, so block the delete whenever the feedback state can't be confirmed.
        if entry_report_service is None:
            return render_error_banner("Cannot verify feedback state — delete blocked")
        history_result = await entry_report_service.list_for_submission(uid)
        if history_result.is_error:
            return render_error_banner("Could not check for feedback — delete blocked")
        if history_result.value:
            return render_error_banner("Cannot delete a submission that has received feedback")

        delete_result = await orchestrator.delete_entry(uid, user_uid)
        if delete_result.is_error:
            return render_error_banner("Failed to delete submission", str(delete_result.error))

        return Div()

    # =========================================================================
    # JOURNALS  (download only — upload/browse live in journals_routes.py)
    # =========================================================================

    @rt("/submit/journals/{uid}/download")
    async def download_journal(request: Request, uid: str) -> Any:
        """Ownership-verified download of a journal entry's source file."""
        try:
            user_uid = require_authenticated_user(request)
            entry_result = require_found(
                await orchestrator.get_entry(uid, user_uid), "UserEntry", uid
            )
            if entry_result.is_error:
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

        except Exception as e:  # safety-net: download error boundary
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
            # Owner-scope the response fetch: `get_entry_responses` is NOT
            # ownership-aware, so on a failed attempt (e.g. not-found for an
            # entry the caller does not own) we must NOT render that entry's
            # reports — re-verify ownership before surfacing any responses.
            owned = await orchestrator.get_entry(entry_uid, user_uid)
            existing = (
                await orchestrator.get_entry_responses(entry_uid)
                if owned.is_ok and owned.value is not None
                else None
            )
            return Div(
                render_inline_error(result.expect_error().message),
                _render_entry_responses(
                    existing.value if existing is not None and existing.is_ok else []
                ),
                id="entry-responses",
            )

        responses_result = await orchestrator.get_entry_responses(entry_uid)
        responses = responses_result.value if responses_result.is_ok else []
        return _render_entry_responses(responses)

    # =========================================================================
    # GRADEBOOK MOC ROOT
    # =========================================================================

    @rt("/gradebook")
    async def gradebook_moc(request: Request) -> Any:
        """GradeBook MOC — links to all 3 sub-pages, no sidebar."""
        require_authenticated_user(request)

        def _moc_card(
            title: str,
            description: str,
            href: str,
            icon: str,
            icon_bg: str = "bg-muted",
        ) -> Any:
            return A(
                Div(
                    Div(
                        Icon(icon, size=28),
                        cls=f"w-14 h-14 rounded-2xl {icon_bg} flex items-center justify-center mb-4",
                    ),
                    H2(title, cls="text-lg font-semibold mb-1"),
                    P(description, cls="text-sm text-muted-foreground"),
                    cls="p-6",
                ),
                href=href,
                cls=(
                    "block border border-border rounded-2xl bg-card "
                    "hover:border-primary/40 hover:shadow-md transition-all duration-150"
                ),
            )

        content = Div(
            PageHeader("GradeBook", subtitle="Review your feedback, reports, and revised work"),
            Div(
                _moc_card(
                    "Entry Reports",
                    "AI and teacher feedback on your submitted exercises and journals.",
                    "/entry-reports",
                    "clipboard-check",
                    "bg-blue-50",
                ),
                _moc_card(
                    "Activity Reports",
                    "Holistic reports aggregating your activity patterns and progress.",
                    "/activity-reports",
                    "bar-chart-2",
                    "bg-amber-50",
                ),
                _moc_card(
                    "Revised Exercises",
                    "Exercises returned for revision with teacher comments and scoring.",
                    "/revised-exercises",
                    "refresh-cw",
                    "bg-emerald-50",
                ),
                cls="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6",
            ),
        )

        return await BasePage(
            content=content,
            title="GradeBook",
            request=request,
            active_page="gradebook",
        )

    # =========================================================================
    # GRADEBOOK DETAIL — MUST BE LAST (catch-all pattern)
    # =========================================================================

    @rt("/gradebook/{uid}")
    async def submission_detail(request: Request, uid: str) -> Any:
        """Submission detail page rendered from a ``UserEntry``."""
        user_uid = require_authenticated_user(request)

        entry_result = require_found(await orchestrator.get_entry(uid, user_uid), "UserEntry", uid)
        if entry_result.is_error:
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
                        "← Back to Submission History",
                        href="/submissions/history",
                        cls=ButtonT.ghost,
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
        # Button visibility uses the SAME eligibility check the respond POST
        # enforces — so it shows for NONE-pipeline TRANSFORMS children too.
        eligible = await orchestrator.is_entry_response_eligible(entry)
        respond_button: Any = (
            _render_respond_button(uid) if (eligible.is_ok and eligible.value) else None
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
        submissions_moc,
        submissions_exercise_page,
        submit_redirect,
        submissions_journal_page,
        submit_preview,
        journal_preview,
        history_preview,
        submissions_history,
        history_list,
        delete_submission,
        download_journal,
        respond_to_entry,
        gradebook_moc,
        submission_detail,  # MUST BE LAST — catch-all /gradebook/{uid}
    ]


__all__ = ["create_user_entry_ui_routes"]
