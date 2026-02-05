"""
Journals API Routes
===================

API routes for Journal entities (voice submissions, text journals, transcriptions).
Handles search, categorization, tagging, insights, analytics, and transcription processing.

This file operates on Journal entities (JournalPure) and uses JournalRelationshipService.
"""

__version__ = "1.0"

from datetime import date
from pathlib import Path
from typing import Any

from core.infrastructure.routes.crud_route_factory import CRUDRouteFactory
from core.infrastructure.routes.query_route_factory import CommonQueryRouteFactory
from core.models.enums import ContentScope
from core.models.journal.journal_pure import JournalPure
from core.models.journal.journal_request import (
    JournalCreateRequest as JournalCreateSchema,
)
from core.models.journal.journal_request import (
    JournalUpdateRequest as JournalUpdateSchema,
)
from core.models.transcription import ProcessingStatus
from core.services.conversion_service import ConversionService
from core.services.journals import JournalRelationshipService
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.views.journal_view import (
    journal_pure_to_view,
    journals_pure_to_summary_list,
    journals_pure_to_view_list,
)

conversion_service = ConversionService()

logger = get_logger("skuel.routes.journals.api")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_journals_api_routes(
    app: Any,
    rt: Any,
    transcript_processor: Any,
    assignments_core: Any = None,
    user_service: Any = None,
    audio: Any = None,
) -> list[Any]:
    """
    Create journals API routes.

    Args:
        app: FastHTML application instance
        rt: Router instance
        transcript_processor: TranscriptProcessorService - AI transcript processing
        assignments_core: AssignmentsCoreService for content management
        user_service: Optional user service
        audio: Optional audio service

    SERVICE ARCHITECTURE:
    --------------------
    - TranscriptProcessorService: AI transcript processing (process_transcript, search_journals)
    - AssignmentsCoreService: Content management (categories, tags, publish/archive, bulk ops)
    - JournalRelationshipService: Graph relationship queries for journals

    Returns:
        List of created routes
    """
    routes: list[Any] = []

    # FAIL-FAST: Validate required services BEFORE any route registration
    if not transcript_processor:
        raise ValueError("transcript_processor required for journals API - fail-fast")
    if not assignments_core:
        raise ValueError("assignments_core required for content management routes - fail-fast")

    # Initialize relationship services for fetching graph relationships
    driver = None
    if transcript_processor and transcript_processor.backend:
        driver = transcript_processor.backend.driver
    elif assignments_core and assignments_core.backend:
        driver = assignments_core.backend.driver

    # Use JournalRelationshipService for journal-related queries
    journal_relationships = JournalRelationshipService(driver=driver) if driver else None

    async def to_journal_view(journal: JournalPure) -> dict[str, Any]:
        """
        Convert journal to view with relationship data.

        Fetches relationships from graph and passes to view converter.
        """
        related_uids: list[str] = []
        goal_uids: list[str] = []

        uid = getattr(journal, "uid", "")

        if journal_relationships:
            related_result = await journal_relationships.get_related_journals(uid)
            related_uids = related_result.value if related_result.is_ok else []

            goals_result = await journal_relationships.get_supported_goals(uid)
            goal_uids = goals_result.value if goals_result.is_ok else []

        return journal_pure_to_view(
            journal,
            related_journal_uids=related_uids,
            goal_uids=goal_uids,
        )

    logger.info("Creating Journals API routes")

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated)
    # ========================================================================

    crud_factory = CRUDRouteFactory(
        service=transcript_processor,
        domain_name="journals",
        create_schema=JournalCreateSchema,
        update_schema=JournalUpdateSchema,
        uid_prefix="journal",
        scope=ContentScope.USER_OWNED,
    )
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # COMMON QUERY ROUTES (Factory-Generated)
    # ========================================================================

    # Create factory for common query patterns
    query_factory = CommonQueryRouteFactory(
        service=transcript_processor,
        domain_name="journals",
        user_service=user_service,  # For admin /user route
        supports_goal_filter=False,
        supports_habit_filter=False,
        scope=ContentScope.USER_OWNED,
    )

    # Register common query routes:
    # - GET /api/journals/mine               (get authenticated user's journals)
    # - GET /api/journals/user?user_uid=...  (admin only - get any user's journals)
    # - GET /api/journals/by-status?status=...  (filter by status, auth required)
    query_factory.register_routes(app, rt)

    # ========================================================================
    # SEARCH OPERATIONS
    # ========================================================================

    @rt("/api/journals/search")
    @boundary_handler()
    async def search_journals_route(request) -> Result[Any]:
        """Search journal entries with text query"""
        params = dict(request.query_params)

        # Required parameter
        query = params.get("query", "").strip()
        if not query:
            return Result.fail(Errors.validation("Query parameter is required", field="query"))

        # Optional parameters
        limit = int(params.get("limit", 50))
        offset = int(params.get("offset", 0))

        # Use unified journals service - no fallbacks per SKUEL principles
        if not transcript_processor:
            return Result.fail(Errors.system("Journals service not available"))

        result = await transcript_processor.search_journals(query=query, limit=limit, offset=offset)

        if result.is_success():
            journal_summaries = journals_pure_to_summary_list(result.data)
            return Result.ok(
                {"journals": journal_summaries, "query": query, "count": len(journal_summaries)}
            )
        else:
            return Result.fail(Errors.system(result.error.user_message))

    # ========================================================================
    # TIME-BASED QUERIES
    # ========================================================================

    @rt("/api/journals/date-range")
    @boundary_handler()
    async def get_journals_by_date_range_route(request) -> Result[Any]:
        """Get journal entries within a date range"""
        params = dict(request.query_params)

        # Required parameters
        start_date = date.fromisoformat(params["start_date"])
        end_date = date.fromisoformat(params["end_date"])

        # Optional parameters
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))

        # Call service
        result = await transcript_processor.get_journals_by_date_range(
            start_date=start_date, end_date=end_date, limit=limit, offset=offset
        )

        if result.is_success():
            journal_views = journals_pure_to_view_list(result.data)
            return Result.ok(
                {
                    "journals": journal_views,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "count": len(journal_views),
                }
            )
        else:
            return Result.fail(Errors.system(result.error.user_message))

    @rt("/api/journals/recent")
    @boundary_handler()
    async def get_recent_journals_route(request) -> Result[Any]:
        """Get recent journal entries"""
        params = dict(request.query_params)

        # Optional parameters
        limit = int(params.get("limit", 50))

        # Call service (list already sorts by occurred_at desc)
        result = await transcript_processor.list(limit=limit)

        if result.is_ok:
            journal_summaries = journals_pure_to_summary_list(result.value)
            return Result.ok({"journals": journal_summaries, "count": len(journal_summaries)})
        else:
            return Result.fail(Errors.system(result.error.user_message))

    @rt("/api/journals/date")
    @boundary_handler()
    async def get_journal_for_date_route(request, target_date: str) -> Result[Any]:
        """Get journal entry for a specific date"""
        parsed_date = date.fromisoformat(target_date)
        params = dict(request.query_params)
        user_uid = params.get("user_uid")

        # Use AssignmentsCoreService for journal lookup
        if not assignments_core:
            return Result.fail(Errors.system("Content management service not available"))

        # Call service (filters by JOURNAL type internally)
        result = await assignments_core.get_journal_for_date(parsed_date, user_uid)

        if result.is_ok:
            if result.value:
                journal_view = await to_journal_view(result.value)
                return Result.ok(journal_view)
            else:
                return Result.ok(None)  # No journal for this date
        else:
            return Result.fail(Errors.system(result.error.user_message))

    # ========================================================================
    # STATUS OPERATIONS
    # ========================================================================

    @rt("/api/journals/publish")
    @boundary_handler()
    async def publish_journal_route(request, uid: str) -> Result[Any]:
        """Publish a journal entry"""
        if not assignments_core:
            return Result.fail(Errors.system("Content management service not available"))

        result = await assignments_core.publish_journal(uid)

        if result.is_ok:
            journal_view = await to_journal_view(result.value)
            logger.info(f"Journal published via API: {uid}")
            return Result.ok(journal_view)
        else:
            if "not found" in result.error.user_message.lower():
                return Result.fail(Errors.not_found("Journal", uid))
            return Result.fail(Errors.system(result.error.user_message))

    @rt("/api/journals/archive")
    @boundary_handler()
    async def archive_journal_route(request, uid: str) -> Result[Any]:
        """Archive a journal entry"""
        if not assignments_core:
            return Result.fail(Errors.system("Content management service not available"))

        result = await assignments_core.archive_journal(uid)

        if result.is_ok:
            journal_view = await to_journal_view(result.value)
            logger.info(f"Journal archived via API: {uid}")
            return Result.ok(journal_view)
        else:
            if "not found" in result.error.user_message.lower():
                return Result.fail(Errors.not_found("Journal", uid))
            return Result.fail(Errors.system(result.error.user_message))

    # ========================================================================
    # CATEGORY OPERATIONS
    # ========================================================================

    @rt("/api/journals/category")
    @boundary_handler()
    async def get_journals_by_category_route(request, category: str) -> Result[Any]:
        """Get journal entries by category"""
        params = dict(request.query_params)

        # Optional parameters
        limit = int(params.get("limit", 50))
        user_uid = params.get("user_uid")

        if not assignments_core:
            return Result.fail(Errors.system("Content management service not available"))

        # Call service (uses string category, stored in metadata)
        result = await assignments_core.get_journals_by_category(
            category=category, limit=limit, user_uid=user_uid
        )

        if result.is_ok:
            journal_summaries = journals_pure_to_summary_list(result.value)
            return Result.ok(
                {
                    "journals": journal_summaries,
                    "category": category,
                    "count": len(journal_summaries),
                }
            )
        else:
            return Result.fail(Errors.system(result.error.user_message))

    # ========================================================================
    # INSIGHT OPERATIONS
    # ========================================================================

    @rt("/api/journals/insights")
    @boundary_handler()
    async def update_insights_route(request, uid: str) -> Result[Any]:
        """Update journal with insights"""
        body = await request.json()

        # Validate insights - basic validation here
        insights = {}
        if body.get("mood"):
            insights["mood"] = body["mood"]
        if "energy_level" in body and body["energy_level"] is not None:
            insights["energy_level"] = int(body["energy_level"])
        if body.get("key_topics"):
            insights["key_topics"] = body["key_topics"]
        if body.get("action_items"):
            insights["action_items"] = body["action_items"]
        if body.get("mentioned_people"):
            insights["mentioned_people"] = body["mentioned_people"]
        if body.get("mentioned_places"):
            insights["mentioned_places"] = body["mentioned_places"]

        # Call service
        result = await transcript_processor.update_insights(uid, insights)

        if result.is_success():
            journal_view = await to_journal_view(result.data)
            logger.info(f"Journal insights updated via API: {uid}")
            return Result.ok(journal_view)
        else:
            if "not found" in result.error.user_message.lower():
                return Result.fail(Errors.not_found("Journal", uid))
            return Result.fail(Errors.system(result.error.user_message))

    @rt("/api/journals/extract-insights")
    @boundary_handler()
    async def extract_insights_route(request, uid: str) -> Result[Any]:
        """Extract basic insights from journal content"""
        result = await transcript_processor.extract_basic_insights(uid)

        if result.is_success():
            journal_view = await to_journal_view(result.data)
            logger.info(f"Insights extracted for journal via API: {uid}")
            return Result.ok(journal_view)
        else:
            if "not found" in result.error.user_message.lower():
                return Result.fail(Errors.not_found("Journal", uid))
            return Result.fail(Errors.system(result.error.user_message))

    # ========================================================================
    # MOOD AND ENERGY OPERATIONS
    # ========================================================================

    @rt("/api/journals/mood")
    @boundary_handler()
    async def get_journals_by_mood_route(request, mood: str) -> Result[Any]:
        """Get journal entries by mood"""
        params = dict(request.query_params)

        # Optional date range
        start_date = None
        end_date = None
        if "start_date" in params:
            start_date = date.fromisoformat(params["start_date"])
        if "end_date" in params:
            end_date = date.fromisoformat(params["end_date"])

        limit = int(params.get("limit", 50))

        # Call service
        result = await transcript_processor.get_journals_by_mood(
            mood=mood, start_date=start_date, end_date=end_date, limit=limit
        )

        if result.is_success():
            journal_summaries = journals_pure_to_summary_list(result.data)
            return Result.ok(
                {"journals": journal_summaries, "mood": mood, "count": len(journal_summaries)}
            )
        else:
            return Result.fail(Errors.system(result.error.user_message))

    @rt("/api/journals/transcribed")
    @boundary_handler()
    async def get_transcribed_journals_route(request) -> Result[Any]:
        """Get journal entries created from transcriptions"""
        params = dict(request.query_params)

        # Optional date range
        start_date = None
        end_date = None
        if "start_date" in params:
            start_date = date.fromisoformat(params["start_date"])
        if "end_date" in params:
            end_date = date.fromisoformat(params["end_date"])

        limit = int(params.get("limit", 50))

        # Call service
        result = await transcript_processor.get_transcribed_journals(
            start_date=start_date, end_date=end_date, limit=limit
        )

        if result.is_success():
            journal_views = journals_pure_to_view_list(result.data)
            return Result.ok({"journals": journal_views, "count": len(journal_views)})
        else:
            return Result.fail(Errors.system(result.error.user_message))

    # ========================================================================
    # ANALYTICS ROUTES
    # ========================================================================

    @rt("/api/journals/analytics/statistics")
    @boundary_handler()
    async def get_writing_statistics_route(request) -> Result[Any]:
        """Get comprehensive writing statistics"""
        params = dict(request.query_params)

        # Required parameters
        if "start_date" not in params or "end_date" not in params:
            return Result.fail(
                Errors.validation("start_date and end_date are required", field="start_date")
            )

        start_date = date.fromisoformat(params["start_date"])
        end_date = date.fromisoformat(params["end_date"])

        # Call service
        result = await transcript_processor.get_writing_statistics(start_date, end_date)

        if result.is_success():
            return Result.ok(
                {
                    "statistics": result.data,
                    "period": {
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                    },
                }
            )
        else:
            return Result.fail(Errors.system(result.error.user_message))

    @rt("/api/journals/analytics/mood-trends")
    @boundary_handler()
    async def get_mood_trends_route(request) -> Result[Any]:
        """Get mood trends over time"""
        params = dict(request.query_params)

        # Required parameters
        if "start_date" not in params or "end_date" not in params:
            return Result.fail(
                Errors.validation("start_date and end_date are required", field="start_date")
            )

        date.fromisoformat(params["start_date"])
        date.fromisoformat(params["end_date"])

        # Optional parameter
        params.get("granularity", "daily")

        return Result.fail(Errors.system("Mood trends feature not yet implemented"))

    @rt("/api/journals/analytics/streaks")
    @boundary_handler()
    async def get_writing_streaks_route(request) -> Result[Any]:
        """Get writing streak information"""
        params = dict(request.query_params)
        params.get("user_id")

        return Result.fail(Errors.system("Writing streaks feature not yet implemented"))

    # ========================================================================
    # TAG OPERATIONS
    # ========================================================================

    @rt("/api/journals/tags", methods=["POST"])
    @boundary_handler()
    async def add_tags_route(request, uid: str) -> Result[Any]:
        """Add tags to journal entry"""
        body = await request.json()

        tags = body.get("tags", [])
        if not tags:
            return Result.fail(Errors.validation("No tags provided", field="tags"))

        if not assignments_core:
            return Result.fail(Errors.system("Content management service not available"))

        # Call service
        result = await assignments_core.add_tags(uid, tags)

        if result.is_ok:
            journal_view = await to_journal_view(result.value)
            logger.info(f"Tags added to journal via API: {uid}")
            return Result.ok(journal_view)
        else:
            if "not found" in result.error.user_message.lower():
                return Result.fail(Errors.not_found("Journal", uid))
            return Result.fail(Errors.system(result.error.user_message))

    @rt("/api/journals/tag")
    @boundary_handler()
    async def get_journals_by_tag_route(request, tag: str) -> Result[Any]:
        """Get journal entries with specific tag"""
        params = dict(request.query_params)

        limit = int(params.get("limit", 50))
        user_uid = params.get("user_uid")

        if not assignments_core:
            return Result.fail(Errors.system("Content management service not available"))

        result = await assignments_core.get_assignments_by_tag(tag, limit, user_uid)

        if result.is_ok:
            assignments = result.value
            # Convert to summary format for response
            summaries = journals_pure_to_summary_list(assignments)
            return Result.ok({"assignments": summaries, "tag": tag, "count": len(summaries)})
        else:
            return Result.fail(Errors.system(result.error.user_message))

    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================

    @rt("/api/journals/bulk/categorize")
    @boundary_handler()
    async def bulk_categorize_journals_route(request) -> Result[Any]:
        """Bulk categorize multiple journal entries"""
        body = await request.json()

        journal_uids = body.get("journal_uids", [])
        category = body.get("category")

        if not journal_uids or not category:
            return Result.fail(
                Errors.validation("journal_uids and category are required", field="journal_uids")
            )

        if not assignments_core:
            return Result.fail(Errors.system("Content management service not available"))

        # Call service (uses string category, stored in metadata)
        result = await assignments_core.bulk_categorize(journal_uids, category)

        if result.is_ok:
            logger.info(f"Bulk categorized {result.value} journals to {category}")
            return Result.ok(
                {
                    "updated_count": result.value,
                    "category": category,
                }
            )
        else:
            return Result.fail(Errors.system(result.error.user_message))

    @rt("/api/journals/bulk/tag")
    @boundary_handler()
    async def bulk_tag_journals_route(request) -> Result[Any]:
        """Bulk add tags to multiple journal entries"""
        body = await request.json()

        journal_uids = body.get("journal_uids", [])
        tags = body.get("tags", [])

        if not journal_uids or not tags:
            return Result.fail(
                Errors.validation("journal_uids and tags are required", field="journal_uids")
            )

        if not assignments_core:
            return Result.fail(Errors.system("Content management service not available"))

        # Call service
        result = await assignments_core.bulk_tag(journal_uids, tags)

        if result.is_ok:
            logger.info(f"Bulk tagged {result.value} journals")
            return Result.ok(
                {
                    "updated_count": result.value,
                    "tags": tags,
                }
            )
        else:
            return Result.fail(Errors.system(result.error.user_message))

    # ========================================================================
    # EXPORT OPERATIONS
    # ========================================================================

    @rt("/api/journals/export/markdown")
    @boundary_handler()
    async def export_markdown_route(request, uid: str) -> Result[Any]:
        """Export journal to markdown format"""
        if not assignments_core:
            return Result.fail(Errors.system("Content management service not available"))

        result = await assignments_core.export_to_markdown(uid)

        if result.is_ok:
            return Result.ok({"markdown": result.value, "journal_uid": uid})
        else:
            if "not found" in result.error.user_message.lower():
                return Result.fail(Errors.not_found("Journal", uid))
            return Result.fail(Errors.system(result.error.user_message))

    @rt("/api/transcribe")
    @boundary_handler()
    async def transcribe_audio_route(request) -> Result[Any]:
        """Transcribe audio file and return transcription"""
        import tempfile

        temp_file_path = None
        try:
            logger.info("=== Starting audio transcription request ===")

            # Get uploaded file
            form = await request.form()
            logger.info(f"Form received: {form}")
            audio_file = form.get("audio")
            logger.info(f"Audio file from form: {audio_file}")

            if not audio_file:
                logger.error("No audio file in form data")
                return Result.fail(Errors.validation("No audio file provided", field="audio"))

            # Read file content
            file_content = await audio_file.read()
            filename = audio_file.filename
            logger.info(f"File received: {filename}, size: {len(file_content)} bytes")

            # Get audio transcription service
            audio_service = audio
            if not audio_service:
                logger.error("Audio service not available")
                return Result.fail(Errors.system("Audio transcription service not available"))

            # Save to temporary file
            suffix = Path(filename).suffix if filename else ".mp3"
            logger.info(f"Creating temp file with suffix: {suffix}")
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            logger.info(f"Temp file created: {temp_file_path}")

            # Transcribe audio (requires user_uid)
            user_uid = request.query_params.get("user_uid", "demo_user")

            logger.info(f"Starting transcription for user: {user_uid}")

            # STAGE 1: Transcribe only (no journal creation yet)
            # Use process_transcription_with_llm() separately for STAGE 2 (LLM processing)
            result = await audio_service.transcribe_file(
                file_path=temp_file_path, language="en", user_uid=user_uid
            )

            logger.info(f"Transcription result: is_ok={result.is_ok}")

            if result.is_ok:
                transcription = result.value
                logger.info(
                    f"Transcription successful: uid={transcription.uid}, text length={len(transcription.transcript_text)}"
                )

                # Get enum value safely
                status_value = (
                    transcription.processing_status.value
                    if isinstance(transcription.processing_status, ProcessingStatus)
                    else transcription.processing_status
                )

                return Result.ok(
                    {
                        "transcription_text": transcription.transcript_text,
                        "uid": transcription.uid,
                        "status": status_value,
                        "message": "Transcription complete. Use /api/assignments/process-transcription to format with LLM.",
                    }
                )
            else:
                error_msg = result.error.user_message if result.error else "Unknown error"
                logger.error(f"Transcription failed: {error_msg}")
                return Result.fail(Errors.system(error_msg))

        finally:
            # Clean up temporary file
            if temp_file_path and Path(temp_file_path).exists():
                try:
                    Path(temp_file_path).unlink()
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file: {cleanup_error}")

    @rt("/api/journals/process-transcription")
    @boundary_handler()
    async def process_transcription_with_llm_route(request) -> Result[Any]:
        """
        STAGE 2: Process an existing transcription with LLM instructions.

        Query parameters:
        - transcription_uid: UID of the transcription to process (REQUIRED)
        - project_uid: JournalProject UID containing instructions (default: jp.transcript_default)
        - user_uid: User UID (default: demo_user)
        - title: Optional custom title for journal

        Returns:
        - journal_uid: UID of the created formatted journal
        """
        # Get parameters
        transcription_uid = request.query_params.get("transcription_uid")
        if not transcription_uid:
            return Result.fail(
                Errors.validation("transcription_uid is required", field="transcription_uid")
            )

        project_uid = request.query_params.get("project_uid", "jp.transcript_default")
        user_uid = request.query_params.get("user_uid", "demo_user")
        title = request.query_params.get("title")  # Optional

        # Get audio service
        audio_service = audio
        if not audio_service:
            return Result.fail(Errors.system("Audio transcription service not available"))

        logger.info(
            f"Processing transcription {transcription_uid} with project {project_uid} for user {user_uid}"
        )

        # Process the transcription with LLM
        result = await audio_service.process_transcription_with_llm(
            transcription_uid=transcription_uid,
            project_uid=project_uid,
            user_uid=user_uid,
            title=title,
        )

        if result.is_ok:
            journal_uid = result.value
            logger.info(f"Transcription processed successfully → journal {journal_uid}")

            return Result.ok(
                {
                    "journal_uid": journal_uid,
                    "transcription_uid": transcription_uid,
                    "project_uid": project_uid,
                    "message": "Transcription processed with LLM and journal created",
                }
            )
        else:
            error_msg = result.error.user_message if result.error else "Unknown error"
            logger.error(f"Processing failed: {error_msg}")
            return Result.fail(Errors.system(error_msg))

    # Collect all routes
    routes.extend(
        [
            transcribe_audio_route,
            process_transcription_with_llm_route,
            search_journals_route,
            get_journals_by_date_range_route,
            get_recent_journals_route,
            get_journal_for_date_route,
            publish_journal_route,
            archive_journal_route,
            get_journals_by_category_route,
            update_insights_route,
            extract_insights_route,
            get_journals_by_mood_route,
            get_transcribed_journals_route,
            get_writing_statistics_route,
            get_mood_trends_route,
            get_writing_streaks_route,
            add_tags_route,
            get_journals_by_tag_route,
            bulk_categorize_journals_route,
            bulk_tag_journals_route,
            export_markdown_route,
        ]
    )

    logger.info(f"Journals API routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_journals_api_routes"]
