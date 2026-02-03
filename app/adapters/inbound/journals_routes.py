"""
Journals Routes - Clean Architecture Factory
============================================

Factory that wires Journals API routes using DomainRouteConfig.

**ARCHITECTURE COMMITMENT: Assignments is the Primary Interface**

- **Assignments**: Primary user-facing system for file upload and processing
  - Handles all file types: audio, text, PDF, images, video
  - Provides unified UI at /assignments
  - Manages processing pipeline lifecycle

- **Journals**: Backend processing service (NOT a standalone interface)
  - TranscriptProcessorService processes transcripts into formatted journal entries
  - Called by ProcessingPipelineService during audio processing
  - Creates Journal entities in Neo4j with relationships

**User Journey:**
1. User uploads audio via /assignments
2. AssignmentSubmissionService stores file
3. ProcessingPipelineService orchestrates:
   - Deepgram transcription
   - TranscriptProcessorService.process_transcript() (LLM formatting)
   - Neo4j storage as Journal entity
4. User views formatted journal at /assignments/{uid}/content
"""

from adapters.inbound.journals_api import create_journals_api_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

JOURNALS_CONFIG = DomainRouteConfig(
    domain_name="journals",
    primary_service_attr="transcript_processor",
    api_factory=create_journals_api_routes,
    ui_factory=None,  # No UI routes - Assignments is the primary interface
    api_related_services={
        "assignments_core": "assignments_core",
        "user_service": "user_service",
        "audio": "audio",
    },
)


def create_journals_routes(app, rt, services, _sync_service=None):
    """
    Wire journals API routes using configuration-driven registration.

    **Role**: Backend processing service (NOT primary interface)
    - Assignments is the primary user interface
    - Journals service handles transcript → formatted journal pipeline
    - Called by ProcessingPipelineService during audio processing
    """
    return register_domain_routes(app, rt, services, JOURNALS_CONFIG)


__all__ = ["create_journals_routes"]
