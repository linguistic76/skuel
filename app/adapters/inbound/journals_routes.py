"""
Journals Routes - Clean Architecture Factory
============================================

Factory that wires Journals API routes for transcript processing.

**ARCHITECTURE COMMITMENT: Assignments is the Primary Interface**

- **Assignments**: Primary user-facing system for file upload and processing
  - Handles all file types: audio, text, PDF, images, video
  - Provides unified UI at /assignments
  - Manages processing pipeline lifecycle

- **Journals**: Backend processing service (NOT a standalone interface)
  - JournalsService processes transcripts into formatted journal entries
  - Called by ProcessingPipelineService during audio processing
  - Creates Journal entities in Neo4j with relationships

**What This Factory Registers:**
- assignments_content_api.py: JSON API endpoints for content management (categories, tags, search)
- journals_ui.py: ACTIVE (provides full two-tier journal dashboard: PJ1 voice + PJ2 curated)

**User Journey:**
1. User uploads audio via /assignments
2. AssignmentSubmissionService stores file
3. ProcessingPipelineService orchestrates:
   - Deepgram transcription
   - JournalsService.process_transcript() (LLM formatting)
   - Neo4j storage as Journal entity
4. User views formatted journal at /assignments/{uid}/content

**Historical Context:**
- Version 1.0: Had /journals UI routes (redirected to /assignments)
- Version 2.0: Removed UI redirects, committed to Assignments naming
- Current: Pure processing service with API-only access
"""

from adapters.inbound.journals_api import create_journals_api_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.journals")


def create_journals_routes(app, rt, services, _sync_service=None):
    """
    Wire journals API routes for transcript processing.

    **Role**: Backend processing service (NOT primary interface)
    - Assignments is the primary user interface
    - Journals service handles transcript → formatted journal pipeline
    - Called by ProcessingPipelineService during audio processing

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with journals service
        sync_service: Optional sync service for backwards compatibility

    Returns:
        List of route handlers (API only - no UI routes)
    """

    # FAIL-FAST: Validate required services BEFORE any route registration
    if not services:
        raise ValueError("Services container required for journals routes")

    # Get transcript processor (services.journals for backward compat)
    transcript_processor = services.transcript_processor or getattr(services, "journals", None)
    if not transcript_processor:
        raise ValueError("Transcript processor required for journals routes - fail-fast")

    # Wire API routes (JSON endpoints for CRUD, analytics, transcription integration)
    api_routes = create_journals_api_routes(app, rt, transcript_processor, services)

    logger.info("✅ Journals routes registered (processing service)")
    logger.info(f"   - API routes: {len(api_routes)} endpoints (transcript processing)")
    logger.info("   - Role: Backend processing (NOT primary interface)")
    logger.info("   - Primary Interface: /assignments (user-facing system)")
    logger.info("   - Architecture: Assignments → ProcessingPipeline → TranscriptProcessorService")

    return api_routes


# Export the route creation function
__all__ = ["create_journals_routes"]
