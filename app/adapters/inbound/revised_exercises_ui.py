"""
Phase 4: RevisedExercise — Student-Facing Revision Pages
=========================================================

Student view of teacher-created revision instructions. Phase 4 closes the feedback
loop: after a teacher returns NEEDS_REVISION (Phase 3: EntryReport), they create
a RevisedExercise targeting the student's gaps. The student then submits against it,
re-entering Phase 2 (new UserEntry) for another round:

    EntryReport (NEEDS_REVISION) → RevisedExercise → UserEntry v2 → ...

These pages live in the GradeBook sidebar (ui/gradebook/nav.py).

Routes:
- GET /revised-exercises                        — Revisions list page
- GET /revised-exercises/detail?uid=            — Revision detail with feedback points + submit link
- GET /revised-exercises/list                   — HTMX fragment: filtered revisions list
- GET /api/gradebook/revised-exercises/preview  — HTMX hub preview block

Renderers: ui/submissions/revised_exercise.py
Teacher creation: TeacherReviewService.request_revision_with_exercise()
See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import (
    Div,
    Span,
)

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from core.utils.logging import get_logger
from core.utils.text_truncation import truncate_to_budget
from ui.components import Card
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.learning_loop.revised_exercise import (
    render_revised_exercise_detail,
    render_revised_exercise_list,
)
from ui.patterns.error_banner import render_error_banner
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.revised_exercises_ui")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_revised_exercises_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    orchestrator: Any = None,
) -> list[Any]:
    """Create /revised-exercises UI routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: SubmissionsOrchestrator for unified states
    """

    # ========================================================================
    # REVISIONS LIST PAGE
    # ========================================================================

    @rt("/revised-exercises")
    def revised_exercises_page(request: Request) -> Any:
        """Student-facing list of revision requests."""
        require_authenticated_user(request)

        revisions_section = Card(
            content_loading_placeholder(
                "/revised-exercises/list",
                "revisions-list",
                loading_text="Loading revisions...",
            ),
            cls="bg-background shadow-sm p-4",
        )

        content = Div(
            PageHeader(
                "Revisions",
                subtitle="Teacher revision requests for your submissions",
            ),
            revisions_section,
        )
        return render_gradebook_sidebar_page(
            content=content,
            active="revised-exercises",
            request=request,
        )

    # ========================================================================
    # REVISION DETAIL PAGE
    # ========================================================================

    @rt("/revised-exercises/detail")
    async def revised_exercise_detail(request: Request) -> Any:
        """Revision detail view — full instructions, feedback points, rationale."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()

        if not uid:
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Revision UID is required")),
                active="revised-exercises",
                request=request,
            )

        if not orchestrator:
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Revision orchestrator unavailable")),
                active="revised-exercises",
                request=request,
            )

        result = await orchestrator.get_revised_exercise(uid)
        if result.is_error:
            logger.warning(f"Revised exercise not found: {uid}")
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Revision not found")),
                active="revised-exercises",
                request=request,
            )

        entity = result.value
        # Ownership check: student or owning teacher
        entity_student = getattr(entity, "student_uid", None) or ""
        entity_owner = getattr(entity, "user_uid", None) or ""
        if user_uid not in (entity_student, entity_owner):
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Revision not found")),
                active="revised-exercises",
                request=request,
            )

        content = Div(render_revised_exercise_detail(entity))
        return render_gradebook_sidebar_page(
            content=content,
            active="revised-exercises",
            request=request,
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/revised-exercises/list")
    async def revised_exercises_list(request: Request) -> Any:
        """HTMX fragment: revised exercises for current student."""
        try:
            user_uid = require_authenticated_user(request)
            if not orchestrator:
                return Div(
                    render_error_banner("Revision orchestrator unavailable"),
                    id="revisions-list",
                )
            result = await orchestrator.list_revised_exercises(user_uid)
            if result.is_error:
                logger.error(f"Error loading revisions list: {result.error}")
                return Div(
                    render_error_banner("Failed to load revisions", str(result.error)),
                    id="revisions-list",
                )
            return render_revised_exercise_list(result.value or [])
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading revisions list: {e}", exc_info=True)
            return Div(
                render_error_banner("Error loading revisions", str(e)),
                id="revisions-list",
            )

    # ========================================================================
    # HUB PREVIEW ENDPOINT (HTMX lazy-loaded from /gradebook hub)
    # ========================================================================

    @rt("/api/gradebook/revised-exercises/preview")
    async def revised_exercises_preview(request: Request) -> Any:
        """HTMX fragment: 3 most recent revisions for hub preview."""
        user_uid = require_authenticated_user(request)
        if not orchestrator:
            return HubPreviewEmpty("revisions")
        result = await orchestrator.list_revised_exercises(user_uid)
        if result.is_error:
            return HubPreviewEmpty("revisions")
        revisions = result.value or []
        if not revisions:
            return HubPreviewEmpty("revisions")
        cards = []
        for rev in revisions[:3]:
            uid = getattr(rev, "uid", "") or ""
            title = getattr(rev, "title", None) or uid or "Revision"
            revision_number = getattr(rev, "revision_number", 1) or 1
            badge = Span(
                f"#{revision_number}",
                cls="text-[10px] font-medium text-destructive",
            )
            instructions = getattr(rev, "instructions", None) or ""
            href = f"/revised-exercises/detail?uid={uid}" if uid else "/revised-exercises"
            cards.append(
                HubPreviewCard(
                    title=title,
                    href=href,
                    badge=badge,
                    description=truncate_to_budget(instructions, 160) if instructions else None,
                )
            )
        return HubPreviewGrid(cards)

    logger.info(
        "Revised Exercises UI routes created "
        "(/revised-exercises, /revised-exercises/detail, /revised-exercises/list)"
    )

    return [
        revised_exercises_page,
        revised_exercise_detail,
        revised_exercises_list,
    ]
