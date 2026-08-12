"""
Askesis Domain Models Package
=============================

Three-tier models for Askesis - the AI assistant and domain integration orchestrator.

Tier 1 (External): Pydantic models for API validation
Tier 2 (Transfer): Mutable DTOs for data movement
Tier 3 (Core): Immutable domain models with business logic
"""

from .askesis import (
    Askesis,
)
from .askesis_converters import (
    apply_askesis_update_to_dto,
    askesis_create_request_to_dto,
    askesis_update_request_to_dto,
    create_askesis_dto_from_create_dto,
)
from .askesis_dto import (
    AskesisCreateDTO,
    AskesisDTO,
    AskesisUpdateDTO,
)
from .askesis_request import (
    AskesisCreateRequest,
    AskesisUpdateRequest,
)

# Socratic tutoring models (Askesis RAG pipeline refactor)
from .learning_objective import StructuredLearningObjective
from .pedagogical_intent import PedagogicalIntent
from .ps_bundle import PsBundle

__all__ = [
    # Core domain models
    "Askesis",
    "PsBundle",
    "PedagogicalIntent",
    "StructuredLearningObjective",
    "AskesisCreateDTO",
    # Request models
    "AskesisCreateRequest",
    # DTOs
    "AskesisDTO",
    "AskesisUpdateDTO",
    "AskesisUpdateRequest",
    "apply_askesis_update_to_dto",
    # Converters
    "askesis_create_request_to_dto",
    "askesis_update_request_to_dto",
    "create_askesis_dto_from_create_dto",
]
