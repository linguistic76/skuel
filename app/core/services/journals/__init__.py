"""
Journals Service Package
=========================

Multi-modal journal processing: Activity tracking, Idea articulation, Critical thinking.

Key Components:
- JournalModeClassifier: LLM-based weight inference
- JournalOutputGenerator: Format je_output based on mode weights
- JournalWeights: Weight distribution dataclass

See: /ACTIVITY_EXTRACTION_ENABLED.md for architecture overview.
"""

from core.services.journals.journal_types import JournalProcessingResult, JournalWeights

__all__ = [
    "JournalWeights",
    "JournalProcessingResult",
]
