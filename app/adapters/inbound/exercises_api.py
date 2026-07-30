"""
Exercises API - Domain-Specific Routes
========================================

CRUD routes are config-driven via CRUDRouteConfig in exercises_routes.py.
Exercise creation (POST /api/exercises/create) is handled by the CRUD factory
using ConversionServiceV2.exercise_create_to_pure.

This file contains domain-specific manual routes: report generation and
curriculum linking.
"""

from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import make_service_getter, require_authenticated_user, require_teacher
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.form_helpers import parse_form_body, parse_json_body
from adapters.inbound.rate_limit import llm_quota_allowed, llm_quota_exceeded_error
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums.user_enums import UserRole
from core.models.exercises.exercise_request import (
    ExerciseKnowledgeRequest,
    ReportGenerateRequest,
)
from core.models.user_entry.user_entry import UserEntry
from core.ports.query_types import CurriculumExerciseResult, RequiredKnowledgeResult
from core.services.content_enrichment_service import ContentEnrichmentService
from core.services.exercises.exercise_service import ExerciseService
from core.services.intelligence_tier_service import get_user_intelligence_tier
from core.services.report.entry_report_service import EntryReportService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_exercises_api_routes(
    app: Any,
    rt: Any,
    exercises_service: ExerciseService,
    transcript_service: ContentEnrichmentService | None,
    entry_report_service: EntryReportService | None,
    user_service: Any = None,
    intelligence_tier: IntelligenceTier | None = None,
) -> list[Any]:
    """
    Create exercises API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        exercises_service: ExerciseService instance
        transcript_service: ContentEnrichmentService for entry lookup
        entry_report_service: EntryReportService for AI reports
        user_service: UserService for role checks
        intelligence_tier: System tier for the ADR-043 per-user AI gate
    """

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    @rt("/api/exercises/report", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def generate_report(request: Request) -> Result[dict[str, Any]]:
        """
        Generate AI report for an entry using an exercise.

        Creates a EntryReport entity (processor_type=LLM) linked to the
        submission via REPORT_FOR — symmetric with human teacher reports.

        Access (ruled 2026-07-03, systems review R1): the submission OWNER may
        summon the LLM reviewer for their own entry — the self-serve half of
        the learning loop. Teachers may generate reports for entries they
        review. Gated per-user by the ADR-043 intelligence tier (LLM = FULL).

        Body (JSON):
        - submission_uid: Submission UID (required)
        - exercise_uid: Exercise UID (required)
        - temperature: Sampling temperature 0-1 (optional, default 0.7)
        - max_tokens: Max tokens to generate (optional, default 4000)

        Returns:
        - 200: EntryReport entity created {report_uid, submission_uid, exercise_uid, content}
        - 400: Invalid input
        - 404: Entry or exercise not found (or not the caller's entry, non-teacher)
        - 503: Service not available
        """
        if not entry_report_service:
            return Result.fail(
                Errors.system("Report service not available", service="EntryReportService")
            )

        if not transcript_service:
            return Result.fail(
                Errors.system(
                    "Transcript service not available",
                    service="ContentEnrichmentService",
                )
            )

        user_uid = require_authenticated_user(request)

        # Per-user tier gate (ADR-043): fail-secure — the LLM reviewer is a
        # FULL-tier capability; missing gate dependencies mean deny.
        if intelligence_tier is None or user_service is None:
            return Result.fail(
                Errors.business(
                    rule="ai_tier_gate_unavailable",
                    message="AI report generation is not available on this deployment",
                )
            )
        caller_result = await user_service.get_user(user_uid)
        if caller_result.is_error or caller_result.value is None:
            return Result.fail(Errors.database("get_user", "Could not verify user access tier"))
        caller = caller_result.value
        effective_tier = get_user_intelligence_tier(intelligence_tier, caller.role)
        if not effective_tier.ai_enabled:
            return Result.fail(
                Errors.business(
                    rule="ai_tier_required",
                    message="AI report generation requires a paid subscription (FULL tier)",
                )
            )

        # Parse request body — JSON for API callers, form-encoded for the
        # HTMX "Request AI feedback" button (htmx posts urlencoded hx-vals).
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            parsed = await parse_json_body(request, ReportGenerateRequest)
        else:
            parsed = await parse_form_body(request, ReportGenerateRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        report_request = parsed.value

        # Get submission and exercise
        entry_result = await transcript_service.get(report_request.submission_uid)
        if entry_result.is_error:
            return Result.fail(Errors.not_found("Submission", report_request.submission_uid))

        exercise_result = await exercises_service.get_exercise(report_request.exercise_uid)
        if exercise_result.is_error:
            return Result.fail(Errors.not_found("Exercise", report_request.exercise_uid))

        entry = entry_result.value
        exercise = exercise_result.value
        # transcript_service.get() returns Result[Entity]; narrow to UserEntry
        # which is what generate_report requires. Wrong-type entries hit a 404.
        if not isinstance(entry, UserEntry):
            return Result.fail(Errors.not_found("UserEntry", report_request.submission_uid))

        # Owner-or-teacher: a non-teacher may only summon the reviewer for
        # their OWN entry. Not-found (not 403) so entry UIDs don't leak
        # (OWNERSHIP_VERIFICATION pattern).
        is_teacher = caller.role.has_permission(UserRole.TEACHER)
        if entry.user_uid != user_uid and not is_teacher:
            return Result.fail(Errors.not_found("UserEntry", report_request.submission_uid))

        # Non-teachers are further pinned to the exercise their entry FULFILLS —
        # the claim that was already access-validated at submission time
        # (AudienceResolver.validate_references). Without this, any student
        # could run an arbitrary (e.g. another user's PERSONAL) exercise's
        # instructions against their own entry and read them back out of the
        # generated report (Kody security finding, PR #497).
        if not is_teacher:
            fulfilled = await exercises_service.get_exercise_for_submission(
                report_request.submission_uid
            )
            if fulfilled.is_error:
                return Result.fail(fulfilled)
            fulfilled_uid = (fulfilled.value or {}).get("exercise_uid")
            if fulfilled_uid != report_request.exercise_uid:
                return Result.fail(Errors.not_found("Exercise", report_request.exercise_uid))

        # Daily LLM quota — after every access check, immediately before the
        # paid reviewer call, so a rejected request never burns a unit.
        if not llm_quota_allowed(user_uid):
            return Result.fail(llm_quota_exceeded_error())

        # Generate report — creates EntryReport entity + REPORT_FOR relationship
        report_result = await entry_report_service.generate_report(
            entry=entry,
            exercise=exercise,
            user_uid=user_uid,
            temperature=report_request.temperature,
            max_tokens=report_request.max_tokens,
        )

        if report_result.is_error:
            logger.error(f"Failed to generate report: {report_result.error}")
            return Result.fail(report_result)

        report_entity = report_result.value

        return Result.ok(
            {
                "report_uid": report_entity.uid,
                "submission_uid": report_request.submission_uid,
                "exercise_uid": report_request.exercise_uid,
                "content": report_entity.content,
            }
        )

    # ========================================================================
    # CURRICULUM LINKING ROUTES
    # ========================================================================

    @rt("/api/exercises/require-knowledge", methods=["POST"])
    @csrf_protected
    @require_teacher(get_user_service)
    @boundary_handler()
    async def require_knowledge(request: Request, current_user: Any = None) -> Result[bool]:
        """
        Link an exercise to a curriculum KU via REQUIRES_KNOWLEDGE.

        Body (JSON):
        - exercise_uid: Exercise UID (required)
        - curriculum_uid: Curriculum KU UID (required)

        Returns:
        - 200: Relationship created
        - 404: Exercise or curriculum KU not found
        """
        result = await parse_json_body(request, ExerciseKnowledgeRequest)
        if result.is_error:
            return Result.fail(result)
        req = result.value

        return await exercises_service.link_to_curriculum(req.exercise_uid, req.curriculum_uid)

    @rt("/api/exercises/unrequire-knowledge", methods=["POST"])
    @csrf_protected
    @require_teacher(get_user_service)
    @boundary_handler()
    async def unrequire_knowledge(request: Request, current_user: Any = None) -> Result[bool]:
        """
        Remove REQUIRES_KNOWLEDGE relationship between exercise and curriculum KU.

        Body (JSON):
        - exercise_uid: Exercise UID (required)
        - curriculum_uid: Curriculum KU UID (required)

        Returns:
        - 200: Relationship removed
        - 404: Relationship not found
        """
        result = await parse_json_body(request, ExerciseKnowledgeRequest)
        if result.is_error:
            return Result.fail(result)
        req = result.value

        return await exercises_service.unlink_from_curriculum(req.exercise_uid, req.curriculum_uid)

    @rt("/api/exercises/required-knowledge", methods=["GET"])
    @require_teacher(get_user_service)
    @boundary_handler()
    async def get_required_knowledge(
        request: Request, current_user: Any = None
    ) -> Result[list[RequiredKnowledgeResult]]:
        """
        Get all curriculum KUs required by an exercise.

        Query params:
        - uid: Exercise UID (required)

        Returns:
        - 200: List of required curriculum KUs
        """
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))

        return await exercises_service.get_required_knowledge(uid)

    @rt("/api/exercises/for-curriculum", methods=["GET"])
    @require_teacher(get_user_service)
    @boundary_handler()
    async def get_exercises_for_curriculum(
        request: Request, current_user: Any = None
    ) -> Result[list[CurriculumExerciseResult]]:
        """
        Get all exercises that require a specific curriculum KU.

        Query params:
        - curriculum_uid: Curriculum KU UID (required)

        Returns:
        - 200: List of exercises requiring this curriculum KU
        """
        curriculum_uid = request.query_params.get("curriculum_uid")
        if not curriculum_uid:
            return Result.fail(
                Errors.validation("curriculum_uid is required", field="curriculum_uid")
            )

        return await exercises_service.get_exercises_for_curriculum(curriculum_uid)

    @rt("/api/exercises/md")
    async def download_exercise_md(request, uid: str) -> Any:
        """Download an exercise as a Markdown worksheet (.md)."""
        from starlette.responses import Response

        from adapters.outbound.exercise_renderer import render_exercise_md

        user_uid = require_authenticated_user(request)

        # Same audience check as the detail fragment — this route hands back the
        # exercise body as a file, so an unscoped read here would leak exactly
        # what the scoped read next door refuses.
        result = await exercises_service.get_exercise_for_user(uid, user_uid)
        if result.is_error or not result.value:
            return Response(
                content="Exercise not found",
                status_code=404,
                media_type="text/plain",
            )

        md_content = render_exercise_md(result.value, user_uid=user_uid)

        safe_title = "".join(
            c if c.isalnum() or c in "-_" else "-"
            for c in (result.value.title or uid).lower().replace(" ", "-")
        ).strip("-")
        filename = f"exercise-{safe_title}.md"

        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    logger.info("Exercises API routes registered (Factory pattern + curriculum linking)")

    return []
