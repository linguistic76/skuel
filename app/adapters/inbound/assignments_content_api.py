"""
Assignments Content API Routes
==============================

Content management API routes for Assignment entities.
Handles categories, tags, publish/archive, bulk operations, and search.

FILE ARCHITECTURE:
------------------
- assignments_api.py: File lifecycle (upload, download, process, storage)
- assignments_content_api.py: Content management (categories, tags, search, bulk ops)
- journals_api.py: Journal-specific routes (voice, curated, FIFO)
"""

__version__ = "1.0"

from datetime import date
from typing import Any

from adapters.inbound.response_helpers import error_response, success_response
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


def create_assignments_content_api_routes(app, rt, transcript_processor, services):
    """
    Create assignment content management API routes.

    Args:
        app: FastHTML application instance
        rt: Router instance
        transcript_processor: TranscriptProcessorService - AI transcript processing
        services: Services container (includes assignments_core for content management)

    SERVICE ARCHITECTURE (November 2025):
    ------------------------------------
    - TranscriptProcessorService: AI transcript processing (process_transcript, search_journals)
    - AssignmentsCoreService: Content management (categories, tags, publish/archive, bulk ops)

    Routes use AssignmentsCoreService for content management operations on Assignment entities.
    """

    # FAIL-FAST: Validate required services BEFORE any route registration
    if not transcript_processor:
        raise ValueError("transcript_processor required for assignments content API - fail-fast")
    if not services:
        raise ValueError("Services container required for assignments content API")
    if not services.assignments_core:
        raise ValueError("assignments_core required for content management routes - fail-fast")

    assignments_core = services.assignments_core
    user_service = services.user_service

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

    @rt("/api/assignments/search")
    async def search_journals_route(request):
        """Search journal entries with text query"""
        try:
            params = dict(request.query_params)

            # Required parameter
            query = params.get("query", "").strip()
            if not query:
                return error_response("Query parameter is required")

            # Optional parameters
            limit = int(params.get("limit", 50))
            offset = int(params.get("offset", 0))

            # Use unified journals service - no fallbacks per SKUEL principles
            if not transcript_processor:
                return error_response("Journals service not available", 503)

            result = await transcript_processor.search_journals(
                query=query, limit=limit, offset=offset
            )

            if result.is_success():
                journal_summaries = journals_pure_to_summary_list(result.data)
                return success_response(
                    {"journals": journal_summaries, "query": query, "count": len(journal_summaries)}
                )
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in search journals route: {e}")
            return error_response(f"Failed to search journals: {e!s}", status_code=500)

    # ========================================================================
    # TIME-BASED QUERIES
    # ========================================================================

    @rt("/api/assignments/date-range")
    async def get_journals_by_date_range_route(request):
        """Get journal entries within a date range"""
        try:
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
                return success_response(
                    {
                        "journals": journal_views,
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "count": len(journal_views),
                    }
                )
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in get journals by date range route: {e}")
            return error_response(f"Failed to get journals by date range: {e!s}", status_code=500)

    @rt("/api/assignments/recent")
    async def get_recent_journals_route(request):
        """Get recent journal entries"""
        try:
            params = dict(request.query_params)

            # Optional parameters
            limit = int(params.get("limit", 50))

            # Call service (list already sorts by occurred_at desc)
            result = await transcript_processor.list(limit=limit)

            if result.is_ok:
                journal_summaries = journals_pure_to_summary_list(result.value)
                return success_response(
                    {"journals": journal_summaries, "count": len(journal_summaries)}
                )
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in get recent journals route: {e}")
            return error_response(f"Failed to get recent journals: {e!s}", status_code=500)

    @rt("/api/assignments/date")
    async def get_journal_for_date_route(request, target_date: str):
        """Get journal entry for a specific date"""
        try:
            parsed_date = date.fromisoformat(target_date)
            params = dict(request.query_params)
            user_uid = params.get("user_uid")

            # Use AssignmentsCoreService for journal lookup
            if not assignments_core:
                return error_response("Content management service not available", status_code=503)

            # Call service (filters by JOURNAL type internally)
            result = await assignments_core.get_journal_for_date(parsed_date, user_uid)

            if result.is_ok:
                if result.value:
                    journal_view = await to_journal_view(result.value)
                    return success_response(journal_view)
                else:
                    return success_response(None)  # No journal for this date
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in get journal for date route: {e}")
            return error_response(f"Failed to get journal for date: {e!s}", status_code=500)

    # ========================================================================
    # STATUS OPERATIONS
    # ========================================================================

    @rt("/api/assignments/publish")
    async def publish_journal_route(request, uid: str):
        """Publish a journal entry"""
        try:
            if not assignments_core:
                return error_response("Content management service not available", status_code=503)

            result = await assignments_core.publish_journal(uid)

            if result.is_ok:
                journal_view = await to_journal_view(result.value)
                logger.info(f"Journal published via API: {uid}")
                return success_response(journal_view)
            else:
                return error_response(
                    result.error.user_message,
                    result.error.details,
                    404 if "not found" in result.error.user_message.lower() else 400,
                )

        except Exception as e:
            logger.error(f"Error in publish journal route: {e}")
            return error_response(f"Failed to publish journal: {e!s}", status_code=500)

    @rt("/api/assignments/archive")
    async def archive_journal_route(request, uid: str):
        """Archive a journal entry"""
        try:
            if not assignments_core:
                return error_response("Content management service not available", status_code=503)

            result = await assignments_core.archive_journal(uid)

            if result.is_ok:
                journal_view = await to_journal_view(result.value)
                logger.info(f"Journal archived via API: {uid}")
                return success_response(journal_view)
            else:
                return error_response(
                    result.error.user_message,
                    result.error.details,
                    404 if "not found" in result.error.user_message.lower() else 400,
                )

        except Exception as e:
            logger.error(f"Error in archive journal route: {e}")
            return error_response(f"Failed to archive journal: {e!s}", status_code=500)

    # ========================================================================
    # CATEGORY OPERATIONS
    # ========================================================================

    @rt("/api/assignments/category")
    async def get_journals_by_category_route(request, category: str):
        """Get journal entries by category"""
        try:
            params = dict(request.query_params)

            # Optional parameters
            limit = int(params.get("limit", 50))
            user_uid = params.get("user_uid")

            if not assignments_core:
                return error_response("Content management service not available", status_code=503)

            # Call service (uses string category, stored in metadata)
            result = await assignments_core.get_journals_by_category(
                category=category, limit=limit, user_uid=user_uid
            )

            if result.is_ok:
                journal_summaries = journals_pure_to_summary_list(result.value)
                return success_response(
                    {
                        "journals": journal_summaries,
                        "category": category,
                        "count": len(journal_summaries),
                    }
                )
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in get journals by category route: {e}")
            return error_response(f"Failed to get journals by category: {e!s}", status_code=500)

    # ========================================================================
    # INSIGHT OPERATIONS
    # ========================================================================

    @rt("/api/assignments/insights")
    async def update_insights_route(request, uid: str):
        """Update journal with insights"""
        try:
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
                return success_response(journal_view)
            else:
                return error_response(
                    result.error.user_message,
                    result.error.details,
                    404 if "not found" in result.error.user_message.lower() else 400,
                )

        except Exception as e:
            logger.error(f"Error in update insights route: {e}")
            return error_response(f"Failed to update insights: {e!s}", status_code=500)

    @rt("/api/assignments/extract-insights")
    async def extract_insights_route(request, uid: str):
        """Extract basic insights from journal content"""
        try:
            result = await transcript_processor.extract_basic_insights(uid)

            if result.is_success():
                journal_view = await to_journal_view(result.data)
                logger.info(f"Insights extracted for journal via API: {uid}")
                return success_response(journal_view)
            else:
                return error_response(
                    result.error.user_message,
                    result.error.details,
                    404 if "not found" in result.error.user_message.lower() else 400,
                )

        except Exception as e:
            logger.error(f"Error in extract insights route: {e}")
            return error_response(f"Failed to extract insights: {e!s}", status_code=500)

    # ========================================================================
    # MOOD AND ENERGY OPERATIONS
    # ========================================================================

    @rt("/api/assignments/mood")
    async def get_journals_by_mood_route(request, mood: str):
        """Get journal entries by mood"""
        try:
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
                return success_response(
                    {"journals": journal_summaries, "mood": mood, "count": len(journal_summaries)}
                )
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in get journals by mood route: {e}")
            return error_response(f"Failed to get journals by mood: {e!s}", status_code=500)

    @rt("/api/assignments/transcribed")
    async def get_transcribed_journals_route(request):
        """Get journal entries created from transcriptions"""
        try:
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
                return success_response({"journals": journal_views, "count": len(journal_views)})
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in get transcribed journals route: {e}")
            return error_response(f"Failed to get transcribed journals: {e!s}", status_code=500)

    # ========================================================================
    # ANALYTICS ROUTES
    # ========================================================================

    @rt("/api/assignments/analytics/statistics")
    async def get_writing_statistics_route(request):
        """Get comprehensive writing statistics"""
        try:
            params = dict(request.query_params)

            # Required parameters
            start_date = date.fromisoformat(params["start_date"])
            end_date = date.fromisoformat(params["end_date"])

            # Call service
            result = await transcript_processor.get_writing_statistics(start_date, end_date)

            if result.is_success():
                return success_response(
                    {
                        "statistics": result.data,
                        "period": {
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                        },
                    }
                )
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in get writing statistics route: {e}")
            return error_response(f"Failed to get writing statistics: {e!s}", status_code=500)

    @rt("/api/assignments/analytics/mood-trends")
    async def get_mood_trends_route(request):
        """Get mood trends over time"""
        try:
            params = dict(request.query_params)

            # Required parameters
            date.fromisoformat(params["start_date"])
            date.fromisoformat(params["end_date"])

            # Optional parameter
            params.get("granularity", "daily")

            return error_response("Mood trends feature not yet implemented", 501)

        except Exception as e:
            logger.error(f"Error in get mood trends route: {e}")
            return error_response(f"Failed to get mood trends: {e!s}", status_code=500)

    @rt("/api/assignments/analytics/streaks")
    async def get_writing_streaks_route(request):
        """Get writing streak information"""
        try:
            params = dict(request.query_params)
            params.get("user_id")

            return error_response("Writing streaks feature not yet implemented", 501)

        except Exception as e:
            logger.error(f"Error in get writing streaks route: {e}")
            return error_response(f"Failed to get writing streaks: {e!s}", status_code=500)

    # ========================================================================
    # TAG OPERATIONS
    # ========================================================================

    @rt("/api/assignments/tags", methods=["POST"])
    async def add_tags_route(request, uid: str):
        """Add tags to journal entry"""
        try:
            body = await request.json()

            tags = body.get("tags", [])
            if not tags:
                return error_response("No tags provided")

            if not assignments_core:
                return error_response("Content management service not available", status_code=503)

            # Call service
            result = await assignments_core.add_tags(uid, tags)

            if result.is_ok:
                journal_view = await to_journal_view(result.value)
                logger.info(f"Tags added to journal via API: {uid}")
                return success_response(journal_view)
            else:
                return error_response(
                    result.error.user_message,
                    result.error.details,
                    404 if "not found" in result.error.user_message.lower() else 400,
                )

        except Exception as e:
            logger.error(f"Error in add tags route: {e}")
            return error_response(f"Failed to add tags: {e!s}", status_code=500)

    @rt("/api/assignments/tag")
    async def get_journals_by_tag_route(request, tag: str):
        """Get journal entries with specific tag"""
        try:
            params = dict(request.query_params)

            limit = int(params.get("limit", 50))
            user_uid = params.get("user_uid")

            if not assignments_core:
                return error_response("Content management service not available", status_code=503)

            result = await assignments_core.get_assignments_by_tag(tag, limit, user_uid)

            if result.is_ok:
                assignments = result.value
                # Convert to summary format for response
                summaries = journals_pure_to_summary_list(assignments)
                return success_response(
                    {"assignments": summaries, "tag": tag, "count": len(summaries)}
                )
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in get journals by tag route: {e}")
            return error_response(f"Failed to get journals by tag: {e!s}", status_code=500)

    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================

    @rt("/api/assignments/bulk/categorize")
    async def bulk_categorize_journals_route(request):
        """Bulk categorize multiple journal entries"""
        try:
            body = await request.json()

            journal_uids = body.get("journal_uids", [])
            category = body.get("category")

            if not journal_uids or not category:
                return error_response("journal_uids and category are required")

            if not assignments_core:
                return error_response("Content management service not available", status_code=503)

            # Call service (uses string category, stored in metadata)
            result = await assignments_core.bulk_categorize(journal_uids, category)

            if result.is_ok:
                logger.info(f"Bulk categorized {result.value} journals to {category}")
                return success_response(
                    {
                        "updated_count": result.value,
                        "category": category,
                    }
                )
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in bulk categorize journals route: {e}")
            return error_response(f"Failed to bulk categorize journals: {e!s}", status_code=500)

    @rt("/api/assignments/bulk/tag")
    async def bulk_tag_journals_route(request):
        """Bulk add tags to multiple journal entries"""
        try:
            body = await request.json()

            journal_uids = body.get("journal_uids", [])
            tags = body.get("tags", [])

            if not journal_uids or not tags:
                return error_response("journal_uids and tags are required")

            if not assignments_core:
                return error_response("Content management service not available", status_code=503)

            # Call service
            result = await assignments_core.bulk_tag(journal_uids, tags)

            if result.is_ok:
                logger.info(f"Bulk tagged {result.value} journals")
                return success_response(
                    {
                        "updated_count": result.value,
                        "tags": tags,
                    }
                )
            else:
                return error_response(result.error.user_message, result.error.details)

        except Exception as e:
            logger.error(f"Error in bulk tag journals route: {e}")
            return error_response(f"Failed to bulk tag journals: {e!s}", status_code=500)

    # ========================================================================
    # EXPORT OPERATIONS
    # ========================================================================

    @rt("/api/assignments/export/markdown")
    async def export_markdown_route(request, uid: str):
        """Export journal to markdown format"""
        try:
            if not assignments_core:
                return error_response("Content management service not available", status_code=503)

            result = await assignments_core.export_to_markdown(uid)

            if result.is_ok:
                return success_response({"markdown": result.value, "journal_uid": uid})
            else:
                return error_response(
                    result.error.user_message,
                    result.error.details,
                    404 if "not found" in result.error.user_message.lower() else 400,
                )

        except Exception as e:
            logger.error(f"Error in export markdown route: {e}")
            return error_response(f"Failed to export journal: {e!s}", status_code=500)

    @rt("/api/transcribe")
    async def transcribe_audio_route(request):
        """Transcribe audio file and return transcription"""
        import tempfile
        from pathlib import Path

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
                return error_response("No audio file provided", status_code=400)

            # Read file content
            file_content = await audio_file.read()
            filename = audio_file.filename
            logger.info(f"File received: {filename}, size: {len(file_content)} bytes")

            # Get audio transcription service from services
            logger.info(f"Services object: {services}")
            logger.info(f"Services.audio: {services.audio if services else 'services is None'}")
            audio_service = services.audio if services else None
            if not audio_service:
                logger.error(
                    f"Audio service not available. Services: {services}, audio: {audio_service}"
                )
                return error_response("Audio transcription service not available", status_code=503)

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

                return success_response(
                    {
                        "transcription_text": transcription.transcript_text,
                        "uid": transcription.uid,
                        "status": status_value,
                        "message": "Transcription complete. Use /api/assignments/process-transcription to format with LLM.",
                    }
                )
            else:
                error_msg = result.error.user_message if result.error else "Unknown error"
                error_details = result.error.details if result.error else {}
                logger.error(f"Transcription failed: {error_msg}, details: {error_details}")
                return error_response(error_msg, error_details, status_code=500)

        except Exception as e:
            logger.error(f"Error in transcribe audio route: {e}", exc_info=True)
            return error_response(f"Failed to transcribe audio: {e!s}", status_code=500)
        finally:
            # Clean up temporary file
            if temp_file_path and Path(temp_file_path).exists():
                try:
                    Path(temp_file_path).unlink()
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file: {cleanup_error}")

    @rt("/api/assignments/process-transcription")
    @boundary_handler()
    async def process_transcription_with_llm_route(request):
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
        try:
            # Get parameters
            transcription_uid = request.query_params.get("transcription_uid")
            if not transcription_uid:
                return error_response("transcription_uid is required", status_code=400)

            project_uid = request.query_params.get("project_uid", "jp.transcript_default")
            user_uid = request.query_params.get("user_uid", "demo_user")
            title = request.query_params.get("title")  # Optional

            # Get audio service
            audio_service = services.audio if services else None
            if not audio_service:
                return error_response("Audio transcription service not available", status_code=503)

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

                return success_response(
                    {
                        "journal_uid": journal_uid,
                        "transcription_uid": transcription_uid,
                        "project_uid": project_uid,
                        "message": "Transcription processed with LLM and journal created",
                    }
                )
            else:
                error_msg = result.error.user_message if result.error else "Unknown error"
                error_details = result.error.details if result.error else {}
                logger.error(f"Processing failed: {error_msg}, details: {error_details}")
                return error_response(error_msg, error_details, status_code=500)

        except Exception as e:
            logger.error(f"Error in process transcription route: {e}", exc_info=True)
            return error_response(f"Failed to process transcription: {e!s}", status_code=500)

    logger.info("Journals API routes created successfully")

    return [
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
