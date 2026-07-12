"""Canon retrieval — draw resonant passages from the curated book shelf or vault.

Domain-agnostic capability that voice-infuses LLM reasoning with a curated canon
(Phase 3 of the canon journaling companion) or the user's own vault notes
(canon P3, ADR-077 — same contract, VAULT source kind). Journals is the first
caller; Askesis consumes the canon side.
"""

from core.services.canon.canon_models import (
    CanonContext,
    CanonPassage,
    CanonSource,
    SourceKind,
    merged_attribution_footer,
)
from core.services.canon.canon_retrieval_service import CanonRetrievalService

__all__ = [
    "CanonContext",
    "CanonPassage",
    "CanonRetrievalService",
    "CanonSource",
    "SourceKind",
    "merged_attribution_footer",
]
