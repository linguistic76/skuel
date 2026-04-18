"""
UserEntry API Routes (ADR-054 Step 7)
======================================

REST API for the unified ``UserEntry`` domain — the single entry point for
every user-authored creation path (exercise turn-ins, journal audio, plain
text, LLM-summary jobs, file uploads). Replaces the legacy submissions and
journal REST surfaces post-migration; lives alongside them through Step 13
per the additive-through-Step-13 discipline.

Routes
------
- ``POST  /api/user-entries``         — create (JSON body: ``UserEntryCreateRequest``)
- ``POST  /api/user-entries/upload``  — create from multipart file upload
- ``POST  /api/user-entries/process`` — trigger the pipeline on an existing entry
- ``GET   /api/user-entries/get``     — ownership-verified fetch
- ``GET   /api/user-entries``         — list for the authenticated user
- ``POST  /api/user-entries/delete``  — ownership-verified delete

All routes require session authentication. User-owned reads return 404 for
entries the requester does not own — never 403 — so other students' work is
invisible.

See: /home/mike/.claude/plans/woolly-weaving-hejlsberg.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.datastructures import UploadFile

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from core.models.entity_converters import entity_to_response
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.forms.form_submission_request import FormSubmitRequest
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import (
    UserEntryCreateRequest,
    UserEntryProcessRequest,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.user_entry.user_entry_processing_service import (
        UserEntryProcessingService,
    )
    from core.services.user_entry.user_entry_service import UserEntryService

logger = get_logger("skuel.routes.user_entry.api")


def create_user_entry_api_routes(
    _app: Any,
    rt: Any,
    user_entry_service: UserEntryService,
    processing_service: UserEntryProcessingService | None = None,
) -> list[Any]:
    """Register UserEntry REST API routes.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        user_entry_service: UserEntryService facade (required)
        processing_service: UserEntryProcessingService dispatcher (optional —
            POST /process returns a clear error when missing)
    """
    if not user_entry_service:
        raise ValueError("user_entry_service is required for user_entry API routes")

    logger.info("Creating UserEntry API routes")

    async def _load_owned(uid: str, user_uid: UserUID) -> Result[Any]:
        """Load an entry and 404 when the requester does not own it."""
        result = await user_entry_service.get_entry(uid, user_uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="UserEntry", identifier=uid))
        return Result.ok(result.value)

    # =========================================================================
    # CREATE — JSON body
    # =========================================================================

    @rt("/api/user-entries", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_user_entry_route(request: Request) -> Result[dict[str, Any]]:
        """Create a UserEntry from a JSON ``UserEntryCreateRequest`` body."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_json_body(request, UserEntryCreateRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await user_entry_service.create_entry(request=req, user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "user_entry": entity_to_response(result.value),
                "message": "UserEntry created successfully",
            }
        )

    # =========================================================================
    # CREATE — multipart file upload
    # =========================================================================

    @rt("/api/user-entries/upload", methods=["POST"])
    @boundary_handler(success_status=201)
    async def upload_user_entry_route(request: Request) -> Result[dict[str, Any]]:
        """Create a UserEntry from a multipart file upload.

        Form fields:
            file                           — upload (required)
            title                          — entry title (defaults to filename)
            pipeline                       — Pipeline enum value (default: NONE)
            fulfills_exercise_uid          — optional exercise link
            about_path_step_uid            — optional PathStep link
            instructions                   — pipeline-specific instructions
            share_with_groups              — CSV of group UIDs
            share_with_users               — CSV of user UIDs
            auto_share_to_exercise_groups  — ``"true"`` to server-resolve the
                                             exercise's assigned groups
        """
        user_uid = require_authenticated_user(request)

        form = await request.form()
        uploaded_file = form.get("file")
        if not isinstance(uploaded_file, UploadFile):
            return Result.fail(Errors.validation("No file provided", field="file"))

        file_content = await uploaded_file.read()
        if len(file_content) > 100_000_000:
            return Result.fail(Errors.validation("File too large (max 100MB)", field="file"))

        # Best-effort server-side file storage delegated to UserEntryService in a
        # later step. For now carry metadata only; pipelines that need the raw
        # bytes (Deepgram/LLM) run against ``processed_content`` after wiring.
        pipeline_str = str(form.get("pipeline") or Pipeline.NONE.value)
        try:
            pipeline = Pipeline(pipeline_str)
        except ValueError:
            return Result.fail(
                Errors.validation(f"Invalid pipeline: {pipeline_str}", field="pipeline")
            )

        share_groups_raw = form.get("share_with_groups", "") or ""
        share_users_raw = form.get("share_with_users", "") or ""
        share_with_groups = [g.strip() for g in str(share_groups_raw).split(",") if g.strip()]
        share_with_users = [u.strip() for u in str(share_users_raw).split(",") if u.strip()]
        auto_share_raw = str(form.get("auto_share_to_exercise_groups") or "").strip().lower()
        auto_share_to_exercise_groups = auto_share_raw in {"true", "1", "on", "yes"}

        title_val = form.get("title") or uploaded_file.filename or "Untitled"

        req = UserEntryCreateRequest(
            title=str(title_val),
            pipeline=pipeline,
            instructions=(str(form.get("instructions")) if form.get("instructions") else None),
            original_filename=uploaded_file.filename,
            file_size=len(file_content),
            file_type=uploaded_file.content_type,
            fulfills_exercise_uid=(
                str(form.get("fulfills_exercise_uid"))
                if form.get("fulfills_exercise_uid")
                else None
            ),
            about_path_step_uid=(
                str(form.get("about_path_step_uid")) if form.get("about_path_step_uid") else None
            ),
            share_with_groups=share_with_groups,
            share_with_users=share_with_users,
            auto_share_to_exercise_groups=auto_share_to_exercise_groups,
        )

        result = await user_entry_service.create_entry(request=req, user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "user_entry": entity_to_response(result.value),
                "message": "UserEntry uploaded successfully",
            }
        )

    # =========================================================================
    # CREATE — structured form (inline Ku/PS exercise forms)
    # =========================================================================

    @rt("/api/user-entries/form", methods=["POST"])
    @boundary_handler(success_status=201)
    async def submit_form_route(request: Request) -> Result[dict[str, Any]]:
        """Submit structured form data against an exercise as a ``UserEntry``.

        JSON body (``FormSubmitRequest``):
            exercise_uid: str
            form_data:    dict[str, Any]
            title:        str | None
            from_ps:      str | None
        """
        import json as _json

        user_uid = require_authenticated_user(request)

        parsed = await parse_json_body(request, FormSubmitRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        if not req.form_data:
            return Result.fail(
                Errors.validation("form_data must be a non-empty object", field="form_data")
            )

        metadata: dict[str, Any] = {
            "submission_mode": "form",
            "form_data": req.form_data,
        }
        if req.from_ps:
            metadata["from_ps"] = req.from_ps

        create_req = UserEntryCreateRequest(
            title=req.title or "Form Submission",
            pipeline=Pipeline.TEACHER_REVIEW,
            fulfills_exercise_uid=req.exercise_uid,
            content=_json.dumps(req.form_data),
            metadata=metadata,
        )

        result = await user_entry_service.create_entry(request=create_req, user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "user_entry": entity_to_response(result.value),
                "message": "Form submitted successfully",
            }
        )

    # =========================================================================
    # PROCESS
    # =========================================================================

    @rt("/api/user-entries/process", methods=["POST"])
    @boundary_handler()
    async def process_user_entry_route(request: Request) -> Result[dict[str, Any]]:
        """Trigger the pipeline on an existing entry.

        JSON body: ``UserEntryProcessRequest`` (``uid`` required, optional
        per-run ``pipeline`` and ``instructions`` overrides).
        """
        user_uid = require_authenticated_user(request)

        if processing_service is None:
            return Result.fail(
                Errors.business(
                    rule="processing_service_unavailable",
                    message="UserEntryProcessingService is not wired",
                )
            )

        parsed = await parse_json_body(request, UserEntryProcessRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        loaded = await _load_owned(req.uid, user_uid)
        if loaded.is_error:
            return Result.fail(loaded)
        entry = loaded.value

        result = await processing_service.process(entry, instructions=req.instructions)
        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "user_entry": entity_to_response(result.value),
                "message": "UserEntry processed successfully",
            }
        )

    # =========================================================================
    # GET — ownership verified
    # =========================================================================

    @rt("/api/user-entries/get", methods=["GET"])
    @boundary_handler()
    async def get_user_entry_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Ownership-verified fetch. 404 for entries the requester does not own."""
        user_uid = require_authenticated_user(request)
        loaded = await _load_owned(uid, user_uid)
        if loaded.is_error:
            return Result.fail(loaded)
        return Result.ok(entity_to_response(loaded.value))

    # =========================================================================
    # LIST — ownership scoped
    # =========================================================================

    @rt("/api/user-entries", methods=["GET"])
    @boundary_handler()
    async def list_user_entries_route(
        request: Request,
        pipeline: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[dict[str, Any]]:
        """List the authenticated user's UserEntries with optional filters."""
        user_uid = require_authenticated_user(request)

        parsed_pipeline: Pipeline | None = None
        if pipeline:
            try:
                parsed_pipeline = Pipeline(pipeline)
            except ValueError:
                return Result.fail(
                    Errors.validation(f"Invalid pipeline: {pipeline}", field="pipeline")
                )

        parsed_status: EntityStatus | None = None
        if status:
            try:
                parsed_status = EntityStatus(status)
            except ValueError:
                return Result.fail(Errors.validation(f"Invalid status: {status}", field="status"))

        result = await user_entry_service.list_for_user(
            user_uid=user_uid,
            pipeline=parsed_pipeline,
            status=parsed_status,
            limit=limit,
            offset=offset,
        )
        if result.is_error:
            return Result.fail(result)

        entries = result.value or []
        return Result.ok(
            {
                "user_entries": [entity_to_response(e) for e in entries],
                "count": len(entries),
                "limit": limit,
                "offset": offset,
            }
        )

    # =========================================================================
    # DELETE — ownership verified
    # =========================================================================

    @rt("/api/user-entries/delete", methods=["POST"])
    @boundary_handler()
    async def delete_user_entry_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Ownership-verified cascade delete."""
        user_uid = require_authenticated_user(request)
        result = await user_entry_service.delete_entry(uid, user_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"uid": uid, "deleted": bool(result.value)})

    logger.info("UserEntry API routes created successfully")

    return [
        create_user_entry_route,
        upload_user_entry_route,
        submit_form_route,
        process_user_entry_route,
        get_user_entry_route,
        list_user_entries_route,
        delete_user_entry_route,
    ]
