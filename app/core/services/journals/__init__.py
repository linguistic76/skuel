"""
Journals Service Package
========================

This package contains services for the Journals domain.

Architecture: Service Composition Pattern
- JournalsCoreService: CRUD operations, FIFO cleanup, search
- JournalFeedbackService: AI feedback generation (transparent, user-controlled)
- JournalProjectService: Journal project CRUD (Claude/ChatGPT-style projects)
- JournalRelationshipService: Cross-domain relationship management

Domain Separation (January 2026):
- Journals: Personal reflections, metacognition, automatic LLM feedback
- Assignments: File submission, teacher review, gradebook

Two-Tier Journal System:
- VOICE (PJ1): Ephemeral voice journals, max 3 stored (FIFO cleanup)
- CURATED (PJ2): Permanent curated text/markdown journals

Graph Node: :Journal
Relationships:
- (User)-[:OWNS]->(Journal)
- (Journal)-[:RELATED_TO]->(Journal)
- (Journal)-[:SUPPORTS_GOAL]->(Goal)

NOTE: JournalRelationshipService uses DIRECT DRIVER pattern
See: /docs/patterns/GENERIC_RELATIONSHIP_SERVICE_HONEST_ASSESSMENT.md

Version: 1.0.0
Date: 2026-01-21
"""

from core.services.journals.journal_feedback_service import JournalFeedbackService
from core.services.journals.journal_project_service import JournalProjectService
from core.services.journals.journal_relationship_service import JournalRelationshipService
from core.services.journals.journals_core_service import JournalsCoreService
from core.services.journals.journals_types import JournalAIInsights, JournalContext

__all__ = [
    "JournalsCoreService",
    "JournalFeedbackService",
    "JournalProjectService",
    "JournalRelationshipService",
    "JournalContext",
    "JournalAIInsights",
]
