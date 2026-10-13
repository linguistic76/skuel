"""
PathStep Engagement Routes — 3-Transition API (Phase 5)
========================================================

Wires the public surface of :class:`PsEngagementService` (Phase 4):

    POST /api/ps/{ps_uid}/engage       → T1 engage_pathstep (authenticated user is student)
    POST /api/ps/{ps_uid}/complete     → T2 complete_pathstep (body: review dict)
    POST /api/ps/{ps_uid}/abandon      → T3 abandon_pathstep

There is no publish route: a PathStep is published by its content-vault file's
``publication_state`` (ADR-091 S7).

Authorization
-------------
Any authenticated user. Each transition is scoped to the calling user's own
(student, PS) edge.

Validation errors
-----------------
``engage`` validates the PS's templates and may return a 422 BUSINESS error
with the typed ``list[Violation]`` under ``details.violations`` (per the
Phase 0 ``Errors.ps_validation_report``).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any, cast

from adapters.inbound.auth.session import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.form_helpers import read_json_body
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from services_bootstrap import Services

logger = get_logger(__name__)


def _engagement_to_dict(engagement: Any) -> dict[str, Any]:
    """Convert an :class:`Engagement` frozen dataclass to a JSON-safe dict.

    Datetimes become ISO 8601 strings; ``spawned_instance_uids`` becomes a list.
    """
    raw = asdict(engagement)
    if raw.get("since") is not None:
        raw["since"] = raw["since"].isoformat()
    if raw.get("completed_at") is not None:
        raw["completed_at"] = raw["completed_at"].isoformat()
    if raw.get("abandoned_at") is not None:
        raw["abandoned_at"] = raw["abandoned_at"].isoformat()
    if raw.get("spawned_instance_uids") is not None:
        raw["spawned_instance_uids"] = list(raw["spawned_instance_uids"])
    return raw


def create_ps_engagement_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services | None,
    _sync_service: Any = None,
) -> None:
    """Register the 3-transition engagement endpoints.

    No-op if the engagement service didn't initialize (e.g., during a partial
    bootstrap that omitted the template layer); a warning is logged.
    """
    ps_engagement_service = getattr(services, "ps_engagement", None) if services else None
    if not ps_engagement_service:
        logger.warning("PS engagement routes registered without ps_engagement service")
        return

    # ========================================================================
    # T1 — engage (any authenticated user)
    # ========================================================================

    @rt("/api/ps/{ps_uid}/engage", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def engage_pathstep(request: Request, ps_uid: str) -> Result[dict[str, Any]]:
        """Open a (student, PS) engagement and spawn instances from templates."""
        student_uid = require_authenticated_user(request)
        result = await ps_engagement_service.engage_pathstep(student_uid, ps_uid)
        if result.is_error:
            return cast("Result[dict[str, Any]]", result)
        return Result.ok(_engagement_to_dict(result.value))

    # ========================================================================
    # T2 — complete (any authenticated user; body is review dict)
    # ========================================================================

    @rt("/api/ps/{ps_uid}/complete", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def complete_pathstep(request: Request, ps_uid: str) -> Result[dict[str, Any]]:
        """Apply the student's keep/discard review and close the engagement.

        Request body shape::

            {"review": {"<template_uid>": "keep" | "discard", ...}}

        Templates omitted from the review default to ``"keep"`` (forgiving).
        """
        student_uid = require_authenticated_user(request)
        try:
            body = await read_json_body(request)
        except ValueError:
            return Result.fail(Errors.validation(message="Invalid JSON body", field="body"))
        if not isinstance(body, dict):
            return Result.fail(
                Errors.validation(message="Request body must be a JSON object", field="body")
            )
        review_raw = body.get("review") or {}
        if not isinstance(review_raw, dict):
            return Result.fail(
                Errors.validation(
                    message="'review' must be an object mapping template UIDs to keep/discard",
                    field="review",
                )
            )
        review: dict[str, Any] = {}
        for template_uid, decision in review_raw.items():
            if decision not in ("keep", "discard"):
                return Result.fail(
                    Errors.validation(
                        message=(
                            f"Invalid review decision for {template_uid!r}: "
                            f"{decision!r}. Must be 'keep' or 'discard'."
                        ),
                        field="review",
                    )
                )
            review[str(template_uid)] = decision

        result = await ps_engagement_service.complete_pathstep(student_uid, ps_uid, review)
        if result.is_error:
            return cast("Result[dict[str, Any]]", result)
        return Result.ok(_engagement_to_dict(result.value))

    # ========================================================================
    # T3 — abandon (any authenticated user)
    # ========================================================================

    @rt("/api/ps/{ps_uid}/abandon", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def abandon_pathstep(request: Request, ps_uid: str) -> Result[dict[str, Any]]:
        """Delete all spawned instances and mark the engagement abandoned."""
        student_uid = require_authenticated_user(request)
        result = await ps_engagement_service.abandon_pathstep(student_uid, ps_uid)
        if result.is_error:
            return cast("Result[dict[str, Any]]", result)
        return Result.ok(_engagement_to_dict(result.value))

    logger.info("PS engagement routes registered (3 transitions: engage/complete/abandon)")


__all__ = ["create_ps_engagement_routes"]
