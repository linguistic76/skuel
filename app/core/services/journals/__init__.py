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

from core.services.journals.journal_mode_classifier import JournalModeClassifier
from core.services.journals.journal_output_generator import JournalOutputGenerator
from core.services.journals.journal_types import JournalProcessingResult, JournalWeights

__all__ = [
    "JournalModeClassifier",
    "JournalOutputGenerator",
    "JournalWeights",
    "JournalProcessingResult",
]
