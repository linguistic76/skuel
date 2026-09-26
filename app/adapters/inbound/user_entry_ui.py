"""
UserEntry UI Routes (ADR-054)
=============================

The single UI route file for the unified UserEntry hub. Replaced the legacy
``submissions_ui``, ``submissions_hub_routes``, and ``journals_ui`` surfaces.

Routes:
- GET  /submissions                      — MOC root: links to all 5 sub-pages (no sidebar)
- GET  /submissions/submit               — The Submit page (the upload form)
- GET  /submissions/journal              — Journal file-upload UX (alternative to /journals)
- GET  /submit/journals/{uid}/download   — Ownership-verified download
- GET  /gradebook                        — GradeBook: per-exercise exchange lines + conditional report groups
- GET  /gradebook/lines                  — HTMX fragment: filtered exchange lines (status/source)
- GET  /gradebook/{uid}/download         — The entry as a .md file, behind the same audience read
- GET  /gradebook/{uid}                  — Submission detail: the owner's page, or the recipient card
- GET  /submissions/history              — Submission history (4th sidebar slot)
- GET  /submissions/history/list         — HTMX fragment refresh
- POST /submissions/history/delete       — HTMX row delete
- GET  /submissions/knowledge            — Knowledge notes + grounded-Ku chips (5th slot)

Journal upload routes (POST /journals/upload, POST /journals/folder-process) live
in journals_routes.py. Those paths are zero-persistence (ADR-073) — they process
to je_out/ and write nothing. Reads go through ``UserEntryOrchestrator``. There is
no journal-history surface: ``GET /journals/browse`` was deleted with the browse
route in #420 — journals flow through SKUEL, they do not live in it.
"""

from __future__ import annotations

import json
import mimetypes
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fasthtml.common import FT, H4, A, Div, FtResponse, P, Span
from starlette.responses import FileResponse, Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import status_for_error, ui_boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from adapters.inbound.result_helpers import require_found
from adapters.inbound.route_factories import is_not_found, refuse
from adapters.outbound.user_entry_renderer import entry_download_filename, render_user_entry_md
from core.models.enums.entity_enums import EntityStatus
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import EXERCISE_REMOVED_TITLE, UserEntry
from core.services.intelligence_tier_service import get_user_intelligence_tier
from core.utils.logging import get_logger
from ui.activities.nav import render_activity_sidebar_error, render_activity_sidebar_page
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle, Icon
from ui.feedback import Badge, BadgeT
from ui.gradebook.recipient_card import RecipientEntryCard
from ui.gradebook.share_panel import ShareButton, SharePanelForm
from ui.gradebook.summary import (
    EXCHANGE_SECTION_ID,
    EXERCISE_REMOVED_LABEL,
    GRADEBOOK_TITLE,
    normalize_exchange_filters,
    render_activity_reports_group,
    render_exchange_section,
    render_other_feedback_group,
)
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.learning_loop.report import render_activity_report_list, render_yours_list
from ui.learning_loop.turn_in_label import turn_in_label
from ui.patterns.empty_state import EmptyState
from ui.patterns.entity_links import entity_detail_href
from ui.patterns.error_banner import render_error_banner, render_inline_error
from ui.patterns.hub import HubSection, MocCard, hub_cards_from_organizers
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink
from ui.user_entry.forms import render_upload_form
from ui.user_entry.knowledge_notes import render_knowledge_notes_list
from ui.workbench.nav import render_submissions_sidebar_page

if TYPE_CHECKING:
    from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator
    from core.ports.query_types import OrganizerResult
    from core.services.groups.group_service import GroupService
    from core.services.report.entry_report_service import EntryReportService
    from core.services.user_entry.entry_sharing_service import EntrySharingService
    from core.services.user_entry.user_entry_service import UserEntryService

logger = get_logger("skuel.routes.user_entry.ui")


def _moc_child_href(child: OrganizerResult) -> str:
    """Detail href for a MOC child of any entity type; ``#`` when none exists."""
    return entity_detail_href(child.get("entity_type"), child["uid"]) or "#"


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


def _render_ai_feedback_button(entry_uid: str, exercise_uid: str) -> Any:
    """Button that summons the LLM exercise reviewer for the owner's entry (R1).

    Posts to the single gated door (``POST /api/exercises/report``). Success
    reloads the page so the new report appears under Responses; failures
    surface through the global toast listener reading the X-Toast headers
    (``boundary_handler`` sets them on every error).
    """
    return Button(
        "Request AI feedback",
        cls=(ButtonT.primary, "mt-4"),
        size="sm",
        hx_post="/api/exercises/report",
        hx_vals=json.dumps({"submission_uid": entry_uid, "exercise_uid": exercise_uid}),
        hx_swap="none",
        hx_disabled_elt="this",
        hx_on__after_request="if(event.detail.successful) location.reload()",
    )


def _to_history_dict(entry: UserEntry) -> dict[str, Any]:
    """Adapt a ``UserEntry`` to the dict shape ``render_yours_list`` expects."""
    return {
        "uid": entry.uid,
        "title": entry.title,
        "original_filename": entry.original_filename,
        "exercise_title": entry.turn_in_exercise_title,
        "revision": entry.turn_in_revision,
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
    entry_sharing: EntrySharingService | None = None,
    batch_transcription_service: Any | None = None,
    processing_service: Any | None = None,
    user_service: Any | None = None,
    intelligence_tier: Any | None = None,
) -> None:
    """Register the UserEntry UI routes.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        user_entry_service: Primary ``UserEntryService`` (writes)
        orchestrator: ``UserEntryOrchestrator`` (reads across related services)
        entry_report_service: Used to guard delete when feedback exists
        groups_service: ``GroupService`` used by ``/submissions/submit`` to
            enumerate the student's own groups for the form.
        entry_sharing: ``EntrySharingService`` — the Share panel's candidates
            (``/gradebook/{uid}/share-panel``); without it the owner's page
            renders no Share button.
        batch_transcription_service: Retained for API compatibility (journal upload
            routes now live in journals_routes.py).
        processing_service: Retained for API compatibility (journal upload
            routes now live in journals_routes.py).
        user_service: Resolves the caller's role for the per-user AI tier
            gate (ADR-043) behind the "Request AI feedback" button.
        intelligence_tier: System ``IntelligenceTier``; with ``user_service``
            decides whether the AI-feedback affordance renders at all.
    """
    if user_entry_service is None:
        raise RuntimeError("UserEntryService is required — check bootstrap wiring")
    if orchestrator is None:
        raise RuntimeError("UserEntryOrchestrator is required — check bootstrap wiring")

    logger.info("Creating UserEntry UI routes")

    async def _caller_ai_enabled(user_uid: str) -> bool:
        """Per-user AI tier gate (ADR-043) for the AI-feedback affordance.

        Fail-secure: missing deps or an unresolvable caller mean the button
        does not render. The POST route re-enforces the same gate.
        """
        if user_service is None or intelligence_tier is None:
            return False
        caller_result = await user_service.get_user(user_uid)
        if caller_result.is_error or caller_result.value is None:
            return False
        effective = get_user_intelligence_tier(intelligence_tier, caller_result.value.role)
        return bool(effective.ai_enabled)

    # =========================================================================
    # SUBMISSIONS MOC ROOT
    # =========================================================================

    @rt("/submissions")
    def submissions_moc(request: Request) -> Any:
        """Submissions MOC — links to all 5 sub-pages, no sidebar."""
        require_authenticated_user(request)

        content = Div(
            PageHeader("Submissions", subtitle="Choose how you want to submit or sync your work"),
            Div(
                MocCard(
                    "Sync",
                    "Pull your Obsidian Daily Notes into SKUEL and write completions back.",
                    "/submissions/sync",
                    "refresh-cw",
                    "bg-emerald-50",
                ),
                MocCard(
                    "Submit",
                    "Send your work to a teacher or AI for feedback.",
                    "/submissions/submit",
                    "send",
                    "bg-blue-50",
                ),
                MocCard(
                    "Journal",
                    "Upload audio, text, or files to be transcribed and processed by AI.",
                    "/submissions/journal",
                    "book-open",
                    "bg-violet-50",
                ),
                MocCard(
                    "History",
                    "Browse your past exercise submissions and feedback status.",
                    "/submissions/history",
                    "clock",
                    "bg-amber-50",
                ),
                MocCard(
                    "Knowledge",
                    "Review your knowledge notes and the concepts SKUEL grounded them to.",
                    "/submissions/knowledge",
                    "brain",
                    "bg-rose-50",
                ),
                cls="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6",
            ),
        )

        return BasePage(
            content=content,
            title="Submissions",
            request=request,
            active_page="submissions",
        )

    # =========================================================================
    # SUBMIT — the one Submit page (/submissions/submit)
    # =========================================================================

    @rt("/submissions/submit")
    async def submissions_submit_page(request: Request) -> Any:
        """The Submit page: the upload form, preselecting ``?exercise_uid=`` when carried.

        The PS learning-loop and exercise "Submit →" links arrive here with
        ``exercise_uid`` (+ ``from_ps``); without one the form is the
        exercise-less turn-in.
        """
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
            PageHeader("Submit", subtitle="Send your work for feedback"),
            render_upload_form(
                assigned_exercises,
                selected_exercise_uid=selected_exercise_uid,
                from_ps=from_ps,
                user_groups=user_groups,
            ),
        )
        return render_submissions_sidebar_page(
            content=content,
            active="submit",
            request=request,
        )

    # =========================================================================
    # SUBMIT — JOURNAL UPLOAD UX (/submissions/journal)
    # =========================================================================

    @rt("/submissions/journal")
    async def submissions_journal_page(request: Request) -> Any:
        """Journal file-upload UX — alternative entry point to /journals."""
        user_uid = require_authenticated_user(request)

        from ui.journals.forms import render_upload_form as render_journal_form
        from ui.journals.forms import upload_form_script as journal_script

        # FOUNDER gates the canon "summon" checkbox on the compile path. A lookup
        # failure degrades to hidden (canon-free) — never a visible no-op control.
        is_founder = False
        if user_service is not None:
            user_result = await user_service.get_user(user_uid)
            is_founder = (
                user_result.is_ok
                and user_result.value is not None
                and user_result.value.journal_tier.is_founder()
            )

        content = Div(
            PageHeader(
                "New Journal Entry",
                subtitle="Upload a file to be processed by AI",
            ),
            render_journal_form(is_founder=is_founder),
            journal_script(),
        )
        return render_submissions_sidebar_page(
            content=content,
            active="journal",
            request=request,
        )

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
        return render_submissions_sidebar_page(
            content=content,
            active="history",
            request=request,
        )

    @rt("/submissions/history/list")
    @ui_boundary_handler("Error loading submissions", fragment_id="submissions-yours-list")
    async def history_list(request: Request) -> Any:
        """HTMX fragment: refreshed submissions list."""
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

    @rt("/submissions/history/delete", methods=["POST"])
    @csrf_protected
    async def delete_submission(request: Request, uid: str) -> Any:
        """Delete a user-owned UserEntry (blocked when feedback exists)."""
        user_uid = require_authenticated_user(request)

        entry_result = require_found(await orchestrator.get_entry(uid, user_uid), "UserEntry", uid)
        if entry_result.is_error:
            return refuse(entry_result.expect_error(), render_error_banner, "Submission")

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
    # KNOWLEDGE NOTES — grounded-Ku chips, visible + removable (PR 4)
    # =========================================================================

    @rt("/submissions/knowledge")
    async def submissions_knowledge(request: Request) -> Any:
        """Knowledge notes with their grounded-Ku chips.

        The review surface for eager grounding writes (ruling 2026-07-11):
        every ``pipeline: knowledge`` entry, each chip removable in place via
        ``POST /api/user-entries/grounding/remove``.
        """
        user_uid = require_authenticated_user(request)

        notes_content: Any
        result = await orchestrator.list_knowledge_entries_with_grounding(user_uid)
        if result.is_error:
            logger.error(f"Error loading knowledge notes: {result.error}")
            notes_content = render_error_banner("Failed to load knowledge notes", str(result.error))
        else:
            notes_content = render_knowledge_notes_list(result.value or [])

        content = Div(
            PageHeader(
                "Knowledge Notes",
                subtitle=(
                    "Your knowledge-pipeline notes and the concepts SKUEL "
                    "grounded them to — remove any chip that misses the mark"
                ),
            ),
            notes_content,
        )
        return render_submissions_sidebar_page(
            content=content,
            active="knowledge",
            request=request,
        )

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
    # GRADEBOOK — one page: per-exercise exchange lines (arc 2 C1+C2)
    # =========================================================================

    @rt("/gradebook")
    async def gradebook_page(request: Request, status: str = "all", source: str = "all") -> Any:
        """GradeBook — feedback received, one exchange line per exercise."""
        user_uid = require_authenticated_user(request)
        status, source = normalize_exchange_filters(status, source)
        header = PageHeader(
            GRADEBOOK_TITLE,
            subtitle="Feedback you've received on your work",
            # The on-demand activity report's door lives on the page itself:
            # the GradeBook renders under the Tasks+ sidebar and adds no row to it.
            actions=ButtonLink(
                Icon("bar-chart-2", cls="size-4 mr-2", aria_hidden="true"),
                "Request activity report",
                href="/submit-activity-report",
                cls=ButtonT.default,
                size="sm",
            ),
        )

        summaries_result = await orchestrator.get_student_exchange_summaries(user_uid)
        if summaries_result.is_error:
            # Outage ≠ empty: a failed read must never render as a blank GradeBook.
            logger.error(f"Failed to load exchange summaries: {summaries_result.error}")
            return render_activity_sidebar_page(
                content=Div(
                    header,
                    render_error_banner("Could not load your feedback. Please try again."),
                ),
                active="gradebook",
                request=request,
                title=GRADEBOOK_TITLE,
            )
        summaries = summaries_result.value

        # Conditional group: activity reports (flat, hidden when empty). A
        # failed read surfaces as its own banner — not a silently absent group.
        activity_result = await orchestrator.get_activity_report_history(user_uid, limit=50)
        if activity_result.is_error:
            logger.error(f"Failed to load activity reports: {activity_result.error}")
            activity_group: Any = Div(
                render_error_banner("Could not load activity reports.", severity="warning"),
                cls="mt-8",
            )
        else:
            reports = activity_result.value or []
            activity_group = render_activity_reports_group(
                render_activity_report_list(reports) if reports else None
            )

        content = Div(
            header,
            render_exchange_section(summaries["exercises"], status, source),
            activity_group,
            render_other_feedback_group(summaries["other_feedback"]),
        )
        return render_activity_sidebar_page(
            content=content,
            active="gradebook",
            request=request,
            title=GRADEBOOK_TITLE,
        )

    # Registered BEFORE /gradebook/{uid}: registration order keeps the
    # fragment path from being swallowed by the catch-all detail route.
    @rt("/gradebook/lines")
    @ui_boundary_handler("Error loading exchanges", fragment_id=EXCHANGE_SECTION_ID)
    async def gradebook_lines(request: Request, status: str = "all", source: str = "all") -> Any:
        """HTMX fragment: exchange lines re-rendered for a chip/source change."""
        user_uid = require_authenticated_user(request)
        status, source = normalize_exchange_filters(status, source)
        result = await orchestrator.get_student_exchange_summaries(user_uid)
        if result.is_error:
            logger.error(f"Failed to load exchange summaries: {result.error}")
            return Div(
                render_error_banner("Failed to load exchanges", str(result.error)),
                id=EXCHANGE_SECTION_ID,
            )
        return render_exchange_section(result.value["exercises"], status, source)

    async def _owner_display_name(entry: UserEntry) -> str | None:
        """The owner's display name for a recipient's "From" line, or ``None``
        when it cannot be resolved (the card then carries no line, never a uid)."""
        owner = await orchestrator.user_service.get_user(UserUID(entry.user_uid))
        if owner.is_error or owner.value is None:
            return None
        return owner.value.display_name or owner.value.title

    @rt("/gradebook/{uid}/download")
    async def submission_download(request: Request, uid: str) -> Response:
        """The entry as a Markdown file — the owner's or a recipient's read.

        Behind the same audience read as the page (ADR-088 §3): whoever can
        open the entry can save it. The file carries the title, description
        and body only — never status, the processed body or feedback — so a
        recipient's download withholds exactly what the recipient card does.
        """
        user_uid = require_authenticated_user(request)
        entry_result = require_found(
            await orchestrator.get_entry_for_viewer(uid, user_uid), "Submission", uid
        )
        if entry_result.is_error:
            error = entry_result.expect_error()
            if is_not_found(error):
                return Response("Submission not found", status_code=404, media_type="text/plain")
            return Response(
                "Submission unavailable",
                status_code=status_for_error(error),
                media_type="text/plain",
            )
        entry = entry_result.value
        return Response(
            content=render_user_entry_md(entry),
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{entry_download_filename(entry)}"'
            },
        )

    @rt("/gradebook/{uid}/share-panel")
    async def share_panel_fragment(
        request: Request, uid: str, preselect: str = ""
    ) -> FT | FtResponse:
        """HTMX fragment: the Share panel's body for the entry's owner.

        Candidates are the owner's active student and owned groups and their
        R8 co-members, with the entry's current audience marked; ``preselect=
        reviewers`` (the GradeBook nudge) checks the offered groups the entry
        was submitted to for feedback. Any other entity, and anyone but the
        owner, gets the rendered not-found at 404.
        """
        user_uid = require_authenticated_user(request)
        if entry_sharing is None:
            return render_inline_error("Sharing is not available.")
        candidates = await entry_sharing.candidates(uid, user_uid)
        if candidates.is_error:
            return refuse(candidates.expect_error(), render_inline_error, "UserEntry")
        return SharePanelForm(uid, candidates.value, preselect=preselect or None)

    # =========================================================================
    # GRADEBOOK DETAIL — MUST BE LAST (catch-all pattern)
    # =========================================================================

    @rt("/gradebook/{uid}")
    async def submission_detail(
        request: Request, uid: str, share: str = "", preselect: str = ""
    ) -> FT | FtResponse:
        """Submission detail — the owner's page, or the recipient card.

        One audience read (``read_visibility`` OWNER_OR_AUDIENCE, ADR-088 §5)
        admits the owner and anyone the share links name; everyone else gets
        the rendered not-found at a real 404. The owner-versus-recipient
        branch then decides what is shown: a recipient sees the R6 card —
        with the entry's derived "reviewed" badges — and never the status,
        the processed body, feedback or the exchange. The owner's page
        carries the Share button (``?share=1`` opens its panel — the exchange
        thread's per-version Share link and the GradeBook nudge, R2; the
        nudge adds ``preselect=reviewers``, forwarded to the panel load).
        """
        user_uid = require_authenticated_user(request)

        entry_result = require_found(
            await orchestrator.get_entry_for_viewer(uid, user_uid), "Submission", uid
        )
        if entry_result.is_error:
            return refuse(
                entry_result.expect_error(),
                partial(
                    render_activity_sidebar_error,
                    active="gradebook",
                    request=request,
                    title=GRADEBOOK_TITLE,
                ),
                "Submission",
            )

        entry = entry_result.value
        if entry.user_uid != user_uid:
            standing = await orchestrator.get_entry_review_standing(uid)
            if standing.is_error:
                # The badges are decoration on a page the audience read already
                # admitted; a failed derivation renders the card without them.
                logger.error(f"Failed to derive review standing for {uid}: {standing.error}")
            return BasePage(
                content=RecipientEntryCard(
                    entry,
                    await _owner_display_name(entry),
                    None if standing.is_error else standing.value,
                ),
                title=entry.title or "Shared entry",
                request=request,
                active_page="shared",
            )

        body_text = entry.processed_content or entry.content or ""

        # Submission chain: exercise (the turn-in snapshot — the live node
        # while it exists, the snapshot with ``removed`` once it is deleted,
        # Submit & Share arc R12), feedback reports, revisions. A failed
        # chain query must not masquerade as "no feedback" (Kody #505) —
        # surface it instead of rendering {}.
        chain_result = await orchestrator.get_entry_chain(uid)
        chain_error: str | None = None
        chain: dict[str, Any] = {}
        if chain_result.is_error:
            chain_error = chain_result.expect_error().message
        else:
            chain = dict(chain_result.value or {})
        fulfilled_exercise = chain.get("exercise") or None
        exercise_removed = bool(fulfilled_exercise and fulfilled_exercise.get("removed"))

        exercise_link: Any = None
        if fulfilled_exercise:
            exercise_link = Div(
                Span("Fulfills exercise: ", cls="font-medium text-sm text-muted-foreground"),
                Badge(
                    turn_in_label(
                        str(
                            fulfilled_exercise.get("title")
                            or EXERCISE_REMOVED_TITLE
                            or fulfilled_exercise.get("uid")
                        ),
                        entry.turn_in_revision,
                    )
                    or "",
                    variant=BadgeT.outline,
                    size=Size.sm,
                ),
                Badge(EXERCISE_REMOVED_LABEL, variant=BadgeT.outline, size=Size.sm, cls="ml-2")
                if exercise_removed
                else None,
                A(
                    "View exchange thread →",
                    href=f"/exchange?exercise={fulfilled_exercise.get('uid')}",
                    cls="text-xs text-primary hover:underline ml-2",
                ),
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
                H4(
                    "Processed Content" if entry.processed_content else "Submitted Content",
                    cls="mt-6 mb-4",
                ),
                Div(
                    P(body_text, cls="whitespace-pre-wrap text-sm")
                    if body_text
                    else P(
                        "No content yet.",
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
            cls="bg-background shadow-xs",
        )

        # Responses section (ADR-069) — EntryReports pointing at this entry,
        # from the same chain fetch as the badge.
        responses = list(chain.get("feedback") or [])
        # Button visibility uses the SAME eligibility check the respond POST
        # enforces — so it shows for NONE-pipeline TRANSFORMS children too.
        eligible = await orchestrator.is_entry_response_eligible(entry)
        respond_button: Any = (
            _render_respond_button(uid) if (eligible.is_ok and eligible.value) else None
        )

        # "Request AI feedback" (R1): the owner may summon the LLM reviewer
        # for an exercise-fulfilling entry. Render only when the entry
        # fulfills an exercise that still exists (the reviewer reads its
        # instructions) AND the caller's effective tier allows AI
        # (ADR-043) — the POST re-enforces both server-side.
        ai_feedback_button: Any = None
        if fulfilled_exercise and not exercise_removed and await _caller_ai_enabled(user_uid):
            ai_feedback_button = _render_ai_feedback_button(uid, str(fulfilled_exercise.get("uid")))

        responses_section: Any = (
            Div(
                render_inline_error(f"Could not load feedback for this submission: {chain_error}"),
                id="entry-responses",
                cls="mt-6",
            )
            if chain_error is not None
            else _render_entry_responses(responses)
        )

        # Map of Content — ORGANIZES children drawn by the vault MOC ingestion
        # (moc: true body links). Renders for ANY owned entry with edges; most
        # entries have none and get no section. A failed fetch must not
        # masquerade as "not a MOC" (Kody #505 precedent) — surface it.
        map_section: Any = None
        children_result = await orchestrator.get_entry_organized_children(uid)
        if children_result.is_error:
            map_section = Div(
                render_inline_error(
                    "Could not load this entry's organized contents: "
                    f"{children_result.expect_error().message}"
                ),
                cls="mt-6",
            )
        elif children_result.value:
            map_section = Div(
                HubSection(
                    "Map of Content",
                    hub_cards_from_organizers(
                        children_result.value,
                        href_for=_moc_child_href,
                    ),
                ),
                cls="mt-6",
            )

        share_button: Div | None = (
            ShareButton(uid, open=bool(share), preselect=preselect or None)
            if entry_sharing is not None
            else None
        )

        content = Div(
            PageHeader(entry.title or "Submission Details", subtitle=f"UID: {uid}"),
            share_button,
            detail_card,
            map_section,
            respond_button,
            ai_feedback_button,
            responses_section,
        )

        return render_activity_sidebar_page(
            content=content,
            active="gradebook",
            request=request,
            title=GRADEBOOK_TITLE,
        )

    logger.info("UserEntry UI routes created successfully")


__all__ = ["create_user_entry_ui_routes"]
