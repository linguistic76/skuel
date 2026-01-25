"""
Journals API Routes
===================

Dedicated API endpoints for the Journal domain.

Domain Separation (January 2026):
---------------------------------
- Journals: Personal reflections, metacognition, automatic LLM feedback
- Assignments: File submission, teacher review, gradebook

This module provides:
- Voice journal upload (POST /api/journals/voice)
- Curated journal creation (POST /api/journals/curated)
- Journal listing and filtering
- Journal search
- FIFO cleanup status

Graph Node: :Journal
Routes prefix: /api/journals
"""

from datetime import date, datetime
from typing import Any

from fasthtml.common import JSONResponse

from core.auth import UserUID, require_authenticated_user
from core.models.enums.journal_enums import JournalType
from core.models.journal.journal_converters import journal_dto_to_response, journal_pure_to_dto
from core.models.journal.journal_pure import create_journal
from core.services.journals import JournalsCoreService
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.journals_api")


def _get_journal_entry_date(journal):
    """Get entry_date from journal for sorting, with fallback to date.min."""
    return journal.entry_date if journal.entry_date else date.min


def create_journals_api_routes(app, rt, services):
    """
    Create journal API routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Services container

    Returns:
        List of registered routes
    """
    # Get journals core service
    journals_core: JournalsCoreService = getattr(services, "journals_core", None)

    if not journals_core:
        logger.warning("JournalsCoreService not available - journal API routes disabled")
        return []

    routes = []

    # ========================================================================
    # CREATE ENDPOINTS
    # ========================================================================

    @rt("/api/journals/voice", methods=["POST"])
    async def create_voice_journal(request) -> JSONResponse:
        """
        Create a voice journal entry (PJ1 - ephemeral).

        Voice journals have FIFO cleanup - only 3 most recent are kept.

        Request body:
            title: str
            content: str
            category: str (optional)
            tags: list[str] (optional)

        Returns:
            201: Created journal
            400: Validation error
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        try:
            data = await request.json()
        except Exception:
            return JSONResponse(
                {"error": "Invalid JSON body"},
                status_code=400,
            )

        title = data.get("title", "Voice Journal")
        content = data.get("content", "")

        if not content:
            return JSONResponse(
                {"error": "Content is required"},
                status_code=400,
            )

        # Create voice journal
        journal = create_journal(
            uid=f"journal:{user_uid}:{datetime.now().strftime('%Y%m%d%H%M%S')}",
            user_uid=user_uid,
            title=title,
            content=content,
            journal_type=JournalType.VOICE,
            category=data.get("category"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )

        result = await journals_core.create_journal(journal, enforce_fifo=True)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        dto = journal_pure_to_dto(result.value)
        return JSONResponse(journal_dto_to_response(dto), status_code=201)

    routes.append(create_voice_journal)

    @rt("/api/journals/curated", methods=["POST"])
    async def create_curated_journal(request) -> JSONResponse:
        """
        Create a curated journal entry (PJ2 - permanent).

        Curated journals are permanently stored.

        Request body:
            title: str
            content: str
            category: str (optional)
            tags: list[str] (optional)

        Returns:
            201: Created journal
            400: Validation error
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        try:
            data = await request.json()
        except Exception:
            return JSONResponse(
                {"error": "Invalid JSON body"},
                status_code=400,
            )

        title = data.get("title", "Curated Journal")
        content = data.get("content", "")

        if not content:
            return JSONResponse(
                {"error": "Content is required"},
                status_code=400,
            )

        # Create curated journal
        journal = create_journal(
            uid=f"journal:{user_uid}:{datetime.now().strftime('%Y%m%d%H%M%S')}",
            user_uid=user_uid,
            title=title,
            content=content,
            journal_type=JournalType.CURATED,
            category=data.get("category"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )

        result = await journals_core.create_journal(journal, enforce_fifo=False)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        dto = journal_pure_to_dto(result.value)
        return JSONResponse(journal_dto_to_response(dto), status_code=201)

    routes.append(create_curated_journal)

    # ========================================================================
    # READ ENDPOINTS
    # ========================================================================

    @rt("/api/journals", methods=["GET"])
    async def list_journals(
        request,
        journal_type: str | None = None,
        limit: int = 50,
    ) -> JSONResponse:
        """
        List journals for the authenticated user.

        Query params:
            journal_type: "voice" or "curated" (optional)
            limit: max results (default: 50)

        Returns:
            200: List of journals
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        # Filter by type if specified
        if journal_type:
            try:
                jt = JournalType(journal_type)
                result = await journals_core.get_journals_by_type(user_uid, jt, limit)
            except ValueError:
                return JSONResponse(
                    {"error": f"Invalid journal_type: {journal_type}. Use 'voice' or 'curated'"},
                    status_code=400,
                )
        else:
            # Get all journals
            voice_result = await journals_core.get_voice_journals(user_uid, 3)
            curated_result = await journals_core.get_curated_journals(user_uid, limit)

            journals = []
            if voice_result.is_ok:
                journals.extend(voice_result.value)
            if curated_result.is_ok:
                journals.extend(curated_result.value)

            # Sort by entry_date descending
            journals.sort(key=_get_journal_entry_date, reverse=True)
            sorted_journals = journals[:limit]

            return JSONResponse(
                {
                    "journals": [
                        journal_dto_to_response(journal_pure_to_dto(j)) for j in sorted_journals
                    ],
                    "total": len(sorted_journals),
                }
            )

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        return JSONResponse(
            {
                "journals": [journal_dto_to_response(journal_pure_to_dto(j)) for j in result.value],
                "total": len(result.value),
            }
        )

    routes.append(list_journals)

    @rt("/api/journals/{uid}", methods=["GET"])
    async def get_journal(request, uid: str) -> JSONResponse:
        """
        Get a specific journal by UID.

        Returns:
            200: Journal details
            404: Not found
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await journals_core.get_journal(uid)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        journal = result.value
        if not journal:
            return JSONResponse(
                {"error": f"Journal not found: {uid}"},
                status_code=404,
            )

        # Verify ownership
        if journal.user_uid != user_uid:
            return JSONResponse(
                {"error": f"Journal not found: {uid}"},
                status_code=404,
            )

        dto = journal_pure_to_dto(journal)
        return JSONResponse(journal_dto_to_response(dto))

    routes.append(get_journal)

    @rt("/api/journals/voice", methods=["GET"])
    async def list_voice_journals(request) -> JSONResponse:
        """
        List voice journals (PJ1) for the authenticated user.

        Returns the 3 most recent voice journals (FIFO limit).

        Returns:
            200: List of voice journals
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await journals_core.get_voice_journals(user_uid, 3)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        return JSONResponse(
            {
                "journals": [journal_dto_to_response(journal_pure_to_dto(j)) for j in result.value],
                "total": len(result.value),
                "max_retention": 3,
            }
        )

    routes.append(list_voice_journals)

    @rt("/api/journals/curated", methods=["GET"])
    async def list_curated_journals(request, limit: int = 50) -> JSONResponse:
        """
        List curated journals (PJ2) for the authenticated user.

        Query params:
            limit: max results (default: 50)

        Returns:
            200: List of curated journals
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await journals_core.get_curated_journals(user_uid, limit)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        return JSONResponse(
            {
                "journals": [journal_dto_to_response(journal_pure_to_dto(j)) for j in result.value],
                "total": len(result.value),
            }
        )

    routes.append(list_curated_journals)

    # ========================================================================
    # UPDATE ENDPOINTS
    # ========================================================================

    @rt("/api/journals/{uid}", methods=["PUT"])
    async def update_journal(request, uid: str) -> JSONResponse:
        """
        Update a journal entry.

        Request body:
            title: str (optional)
            content: str (optional)
            tags: list[str] (optional)

        Returns:
            200: Updated journal
            404: Not found
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        # Verify ownership first
        get_result = await journals_core.get_journal(uid)
        if get_result.is_error or not get_result.value:
            return JSONResponse(
                {"error": f"Journal not found: {uid}"},
                status_code=404,
            )

        if get_result.value.user_uid != user_uid:
            return JSONResponse(
                {"error": f"Journal not found: {uid}"},
                status_code=404,
            )

        try:
            data = await request.json()
        except Exception:
            return JSONResponse(
                {"error": "Invalid JSON body"},
                status_code=400,
            )

        # Build updates
        updates: dict[str, Any] = {}
        if "title" in data:
            updates["title"] = data["title"]
        if "content" in data:
            updates["content"] = data["content"]
        if "tags" in data:
            updates["tags"] = data["tags"]

        if not updates:
            return JSONResponse(
                {"error": "No updates provided"},
                status_code=400,
            )

        result = await journals_core.update_journal(uid, updates)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        dto = journal_pure_to_dto(result.value)
        return JSONResponse(journal_dto_to_response(dto))

    routes.append(update_journal)

    # ========================================================================
    # DELETE ENDPOINTS
    # ========================================================================

    @rt("/api/journals/{uid}", methods=["DELETE"])
    async def delete_journal(request, uid: str) -> JSONResponse:
        """
        Delete a journal entry.

        Returns:
            200: Deletion confirmed
            404: Not found
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        # Verify ownership first
        get_result = await journals_core.get_journal(uid)
        if get_result.is_error or not get_result.value:
            return JSONResponse(
                {"error": f"Journal not found: {uid}"},
                status_code=404,
            )

        if get_result.value.user_uid != user_uid:
            return JSONResponse(
                {"error": f"Journal not found: {uid}"},
                status_code=404,
            )

        result = await journals_core.delete_journal(uid)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        return JSONResponse({"deleted": True, "uid": uid})

    routes.append(delete_journal)

    # ========================================================================
    # SEARCH ENDPOINTS
    # ========================================================================

    @rt("/api/journals/search", methods=["POST"])
    async def search_journals(request) -> JSONResponse:
        """
        Search journals by text query.

        Request body:
            query: str
            journal_type: str (optional)
            limit: int (optional, default: 50)

        Returns:
            200: Matching journals
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        try:
            data = await request.json()
        except Exception:
            return JSONResponse(
                {"error": "Invalid JSON body"},
                status_code=400,
            )

        query = data.get("query", "")
        if not query:
            return JSONResponse(
                {"error": "Query is required"},
                status_code=400,
            )

        journal_type = None
        if data.get("journal_type"):
            try:
                journal_type = JournalType(data["journal_type"])
            except ValueError:
                return JSONResponse(
                    {"error": f"Invalid journal_type: {data['journal_type']}"},
                    status_code=400,
                )

        limit = data.get("limit", 50)

        result = await journals_core.search_journals(query, user_uid, journal_type, limit)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        return JSONResponse(
            {
                "journals": [journal_dto_to_response(journal_pure_to_dto(j)) for j in result.value],
                "total": len(result.value),
                "query": query,
            }
        )

    routes.append(search_journals)

    # ========================================================================
    # DATE RANGE ENDPOINTS
    # ========================================================================

    @rt("/api/journals/date-range", methods=["GET"])
    async def get_journals_by_date_range(
        request,
        start_date: str,
        end_date: str,
        journal_type: str | None = None,
        limit: int = 100,
    ) -> JSONResponse:
        """
        Get journals within a date range.

        Query params:
            start_date: ISO date (YYYY-MM-DD)
            end_date: ISO date (YYYY-MM-DD)
            journal_type: "voice" or "curated" (optional)
            limit: max results (default: 100)

        Returns:
            200: Journals in date range
            400: Invalid date format
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            return JSONResponse(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status_code=400,
            )

        jt = None
        if journal_type:
            try:
                jt = JournalType(journal_type)
            except ValueError:
                return JSONResponse(
                    {"error": f"Invalid journal_type: {journal_type}"},
                    status_code=400,
                )

        result = await journals_core.get_journals_by_date_range(user_uid, start, end, jt, limit)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        return JSONResponse(
            {
                "journals": [journal_dto_to_response(journal_pure_to_dto(j)) for j in result.value],
                "total": len(result.value),
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    routes.append(get_journals_by_date_range)

    # ========================================================================
    # PROMOTE VOICE TO CURATED
    # ========================================================================

    @rt("/api/journals/{uid}/promote", methods=["POST"])
    async def promote_to_curated(request, uid: str) -> JSONResponse:
        """
        Promote a voice journal to curated (permanent).

        This removes the journal from FIFO cleanup.

        Returns:
            200: Promoted journal
            404: Not found
            401: Not authenticated
        """
        user_uid: UserUID = require_authenticated_user(request)

        # Verify ownership first
        get_result = await journals_core.get_journal(uid)
        if get_result.is_error or not get_result.value:
            return JSONResponse(
                {"error": f"Journal not found: {uid}"},
                status_code=404,
            )

        journal = get_result.value
        if journal.user_uid != user_uid:
            return JSONResponse(
                {"error": f"Journal not found: {uid}"},
                status_code=404,
            )

        if journal.journal_type == JournalType.CURATED:
            return JSONResponse(
                {"error": "Journal is already curated"},
                status_code=400,
            )

        result = await journals_core.promote_to_curated(uid)

        if result.is_error:
            return JSONResponse(
                {"error": str(result.error)},
                status_code=400,
            )

        dto = journal_pure_to_dto(result.value)
        return JSONResponse(journal_dto_to_response(dto))

    routes.append(promote_to_curated)

    logger.info(f"Registered {len(routes)} journal API routes")
    return routes
