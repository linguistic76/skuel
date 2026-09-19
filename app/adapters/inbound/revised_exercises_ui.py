"""
Phase 4: RevisedExercise — Student-Facing Revision Pages
=========================================================

Student view of teacher-created revision instructions. Phase 4 closes the feedback
loop: after a teacher returns NEEDS_REVISION (Phase 3: EntryReport), they create
a RevisedExercise targeting the student's gaps. The student then submits against it,
re-entering Phase 2 (new UserEntry) for another round:

    EntryReport (NEEDS_REVISION) → RevisedExercise → UserEntry v2 → ...

Revisions surface on the GradeBook exchange lines and inside /exchange threads
(arc 2 C1) — this file keeps the detail page.

Routes:
- GET /revised-exercises/detail?uid=            — Revision detail with feedback points + submit link

Renderers: ui/learning_loop/revised_exercise.py
Teacher creation: TeacherReviewService.request_revision_with_exercise()
See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import (
    Div,
)

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from core.utils.logging import get_logger
from ui.activities.nav import render_activity_sidebar_error, render_activity_sidebar_page
from ui.gradebook.summary import GRADEBOOK_TITLE
from ui.learning_loop.revised_exercise import render_revised_exercise_detail

logger = get_logger("skuel.routes.revised_exercises_ui")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_revised_exercises_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    orchestrator: Any = None,
) -> None:
    """Create the revised-exercise detail route.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: SubmissionsOrchestrator for unified states
    """

    # ========================================================================
    # REVISION DETAIL PAGE
    # ========================================================================

    @rt("/revised-exercises/detail")
    async def revised_exercise_detail(request: Request) -> Any:
        """Revision detail view — full instructions, feedback points, rationale."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()

        if not uid:
            return render_activity_sidebar_error(
                "Revision UID is required",
                active="gradebook",
                request=request,
                title=GRADEBOOK_TITLE,
            )

        if not orchestrator:
            return render_activity_sidebar_error(
                "Revision orchestrator unavailable",
                active="gradebook",
                request=request,
                title=GRADEBOOK_TITLE,
            )

        result = await orchestrator.get_revised_exercise(uid)
        if result.is_error:
            logger.warning(f"Revised exercise not found: {uid}")
            return render_activity_sidebar_error(
                "Revision not found",
                active="gradebook",
                request=request,
                title=GRADEBOOK_TITLE,
            )

        entity = result.value
        # Ownership check: student or owning teacher
        entity_student = getattr(entity, "student_uid", None) or ""
        entity_owner = getattr(entity, "user_uid", None) or ""
        if user_uid not in (entity_student, entity_owner):
            return render_activity_sidebar_error(
                "Revision not found",
                active="gradebook",
                request=request,
                title=GRADEBOOK_TITLE,
            )

        content = Div(render_revised_exercise_detail(entity))
        return render_activity_sidebar_page(
            content=content,
            active="gradebook",
            request=request,
            title=GRADEBOOK_TITLE,
        )

    logger.info("Revised Exercises UI routes created (/revised-exercises/detail)")
