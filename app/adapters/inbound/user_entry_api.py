"""
UserEntry API Routes (ADR-054)
==============================

REST API for the unified ``UserEntry`` domain — the single entry point for
every user-authored creation path (exercise turn-ins, journal audio, plain
text, LLM-summary jobs, file uploads). Replaced the legacy submissions and
journal REST surfaces.

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
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from starlette.datastructures import UploadFile

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.result_helpers import require_found
from core.models.entity_converters import entity_to_response
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.forms.form_submission_request import FormSubmitRequest
from core.models.type_hints import EntityUID, UserUID
from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_request import (
    UserEntryCreateRequest,
    UserEntryProcessRequest,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.entry_grounding_service import EntryGroundingService
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
    grounding_service: EntryGroundingService | None = None,
) -> list[Any]:
    """Register UserEntry REST API routes.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        user_entry_service: UserEntryService facade (required)
        processing_service: UserEntryProcessingService dispatcher (optional —
            POST /process returns a clear error when missing)
        grounding_service: EntryGroundingService (optional — the grounding
            remove route returns a clear error when missing)
    """
    if not user_entry_service:
        raise ValueError("user_entry_service is required for user_entry API routes")

    logger.info("Creating UserEntry API routes")

    async def _load_owned(uid: str, user_uid: UserUID) -> Result[UserEntry]:
        """Load an entry and 404 when the requester does not own it."""
        return require_found(
            await user_entry_service.get_entry(uid, user_uid),
            "UserEntry",
            uid,
        )

    # =========================================================================
    # CREATE — JSON body
    # =========================================================================

    @rt("/api/user-entries", methods=["POST"])
    @csrf_protected
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

        entry, outcome = result.value
        response: dict[str, Any] = {
            "user_entry": entity_to_response(entry),
            "message": "UserEntry created successfully",
        }
        if outcome.any_success or outcome.any_failure:
            response["share_outcome"] = outcome.to_payload()
        return Result.ok(response)

    # =========================================================================
    # CREATE — multipart file upload
    # =========================================================================

    @rt("/api/user-entries/upload", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=201)
    async def upload_user_entry_route(request: Request) -> Result[dict[str, Any]]:
        """Create a UserEntry from a multipart file upload.

        Form fields:
            file                   — upload (required)
            title                  — entry title (defaults to filename)
            pipeline               — Pipeline enum value (default: NONE)
            fulfills_exercise_uid  — optional exercise link
            about_path_step_uid    — optional PathStep link
            instructions           — pipeline-specific instructions
            audience               — single-choice audience selector emitted
                                     by the ``/submit`` form. One of:
                                     ``teachers``       (auto-share to exercise groups)
                                     ``group:<uid>``    (share with a specific group)
                                     ``public``         (visibility=PUBLIC)
                                     ``private`` / ``"" (default — owner only)
        """
        user_uid = require_authenticated_user(request)

        form = await request.form()
        uploaded_file = form.get("file")
        if not isinstance(uploaded_file, UploadFile):
            return Result.fail(Errors.validation("No file provided", field="file"))

        file_content = await uploaded_file.read()
        if len(file_content) > 100_000_000:
            return Result.fail(Errors.validation("File too large (max 100MB)", field="file"))

        # Text uploads carry their content onto the entry — the LLM pipelines
        # (LLM_SUMMARY, exercise reports) read ``entry.content``, and a worksheet
        # turn-in whose text is dropped can never receive feedback. Binary
        # uploads (audio/video) stay metadata-only; their bytes flow through the
        # transcription pipelines instead.
        content_text: str | None = None
        filename_lower = (uploaded_file.filename or "").lower()
        content_type = uploaded_file.content_type or ""
        is_texty = content_type.startswith("text/") or filename_lower.endswith(
            (".md", ".markdown", ".txt")
        )
        if file_content and is_texty:
            try:
                content_text = file_content.decode("utf-8")
            except UnicodeDecodeError:
                content_text = None  # mislabeled binary — keep metadata-only

        pipeline_str = str(form.get("pipeline") or Pipeline.NONE.value)
        try:
            pipeline = Pipeline(pipeline_str)
        except ValueError:
            return Result.fail(
                Errors.validation(f"Invalid pipeline: {pipeline_str}", field="pipeline")
            )

        audience_raw = str(form.get("audience") or "private").strip().lower()
        share_with_groups: list[str] = []
        auto_share_to_exercise_groups = False
        visibility: Visibility | None = None
        if audience_raw == "teachers":
            auto_share_to_exercise_groups = True
        elif audience_raw.startswith("group:"):
            group_uid = audience_raw.split(":", 1)[1].strip()
            if group_uid:
                share_with_groups = [group_uid]
        elif audience_raw == "public":
            visibility = Visibility.PUBLIC
        elif audience_raw not in {"private", ""}:
            return Result.fail(
                Errors.validation(f"Unknown audience: {audience_raw}", field="audience")
            )

        title_val = form.get("title") or uploaded_file.filename or "Untitled"

        req = UserEntryCreateRequest(
            title=str(title_val),
            content=content_text,
            pipeline=pipeline,
            instructions=(str(form.get("instructions")) if form.get("instructions") else None),
            original_filename=uploaded_file.filename,
            file_size=len(file_content),
            file_type=uploaded_file.content_type,
            fulfills_exercise_uid=(
                EntityUID(str(form.get("fulfills_exercise_uid")))
                if form.get("fulfills_exercise_uid")
                else None
            ),
            about_path_step_uid=(
                EntityUID(str(form.get("about_path_step_uid")))
                if form.get("about_path_step_uid")
                else None
            ),
            share_with_groups=share_with_groups,
            auto_share_to_exercise_groups=auto_share_to_exercise_groups,
            visibility=visibility,
        )

        result = await user_entry_service.create_entry(request=req, user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        entry, outcome = result.value
        response: dict[str, Any] = {
            "user_entry": entity_to_response(entry),
            "message": "UserEntry uploaded successfully",
        }
        if outcome.any_success or outcome.any_failure:
            response["share_outcome"] = outcome.to_payload()
        return Result.ok(response)

    # =========================================================================
    # CREATE — structured form (inline Ku/PS exercise forms)
    # =========================================================================

    @rt("/api/user-entries/form", methods=["POST"])
    @csrf_protected
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
            fulfills_exercise_uid=EntityUID(req.exercise_uid),
            # PathStep context rides onto the Interaction record
            # (INTERACTION_DURING) — same contract as the upload path.
            about_path_step_uid=(EntityUID(req.from_ps) if req.from_ps else None),
            content=_json.dumps(req.form_data),
            metadata=metadata,
        )

        result = await user_entry_service.create_entry(request=create_req, user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        entry, outcome = result.value
        response: dict[str, Any] = {
            "user_entry": entity_to_response(entry),
            "message": "Form submitted successfully",
        }
        if outcome.any_success or outcome.any_failure:
            response["share_outcome"] = outcome.to_payload()
        return Result.ok(response)

    # =========================================================================
    # PROCESS
    # =========================================================================

    @rt("/api/user-entries/process", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def process_user_entry_route(request: Request) -> Result[dict[str, Any]]:
        """Trigger the pipeline on an existing entry.

        JSON body: ``UserEntryProcessRequest`` (``uid`` required, optional
        per-run ``pipeline``/``instructions`` overrides and ``force`` re-run
        flag for the EXTRACT_ACTIVITIES completed-run guard).
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

        if req.pipeline is not None and req.pipeline != entry.pipeline:
            entry = replace(entry, pipeline=req.pipeline)

        result = await processing_service.process(
            entry, instructions=req.instructions, force=req.force
        )
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
    @csrf_protected
    @boundary_handler()
    async def delete_user_entry_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Ownership-verified cascade delete."""
        user_uid = require_authenticated_user(request)
        result = await user_entry_service.delete_entry(uid, user_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"uid": uid, "deleted": bool(result.value)})

    # =========================================================================
    # GROUNDING — remove one APPLIES_KNOWLEDGE edge (Entry-Enrichment PR 3)
    # =========================================================================

    @rt("/api/user-entries/grounding/remove", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def remove_grounded_knowledge_route(
        request: Request, uid: str, ku_uid: str
    ) -> Result[dict[str, Any]]:
        """Remove one ``(entry)-[:APPLIES_KNOWLEDGE]->(ku)`` edge from an owned entry.

        The user is editor, not approver: inferred grounding edges write
        eagerly and are removed here — each removal is recorded on the entry
        so no future pass re-infers the pair, and logged as
        threshold-calibration data. POST (not DELETE) matches this file's
        mutation convention. Not owned / edge absent → 404, never 403.
        """
        user_uid = require_authenticated_user(request)
        if grounding_service is None:
            return Result.fail(
                Errors.unavailable(
                    feature="entry_grounding",
                    reason="Entry grounding service is not wired.",
                    operation="remove_grounded_knowledge",
                )
            )
        result = await grounding_service.remove(uid, ku_uid, user_uid)
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(
                Errors.not_found(resource="UserEntry knowledge link", identifier=f"{uid}→{ku_uid}")
            )
        return Result.ok({"uid": uid, "ku_uid": ku_uid, "removed": True})

    logger.info("UserEntry API routes created successfully")

    return [
        create_user_entry_route,
        upload_user_entry_route,
        submit_form_route,
        process_user_entry_route,
        get_user_entry_route,
        list_user_entries_route,
        delete_user_entry_route,
        remove_grounded_knowledge_route,
    ]
