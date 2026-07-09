"""Canon retrieval — draw resonant passages from the curated book shelf.

Domain-agnostic capability that voice-infuses LLM reasoning with a curated canon
(Phase 3 of the canon journaling companion). Journals is the first caller;
Askesis-ready later.
"""

from core.services.canon.canon_models import CanonContext, CanonPassage, CanonSource
from core.services.canon.canon_retrieval_service import CanonRetrievalService

__all__ = ["CanonContext", "CanonPassage", "CanonRetrievalService", "CanonSource"]
