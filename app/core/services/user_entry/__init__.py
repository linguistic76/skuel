"""
UserEntry Service Package — ADR-054 Step 5
============================================

Facade + processing dispatcher over ``UserEntryBackend``. Replaces
``core/services/submissions/`` and ``core/services/journal/`` post-migration
(those packages stay in place through Step 13).

See: /home/mike/.claude/plans/woolly-weaving-hejlsberg.md
"""

from core.services.user_entry.assessment_service import AssessmentService
from core.services.user_entry.exercise_linker import (
    ProcessingOutcome,
    UserEntryExerciseLinker,
)
from core.services.user_entry.relationship_service import UserEntryRelationshipService
from core.services.user_entry.user_entry_processing_service import (
    UserEntryProcessingService,
)
from core.services.user_entry.user_entry_service import UserEntryService

__all__ = [
    "AssessmentService",
    "ProcessingOutcome",
    "UserEntryExerciseLinker",
    "UserEntryProcessingService",
    "UserEntryRelationshipService",
    "UserEntryService",
]
