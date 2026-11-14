"""
Askesis Converters
==================

Conversion functions between the Askesis request (Tier 1) and DTO (Tier 2)
layers, plus the DTO-level update patch and expand helpers used by AskesisCoreService.

Tier 2 ↔ Tier 3 (``AskesisDTO`` ↔ ``Askesis``) conversions deliberately do NOT
live here — they are ``Askesis.from_dto`` / ``Askesis.to_dto`` on the domain
class. The earlier converter copies here were stale (they didn't tuple-coerce
the frozen dataclass's collection fields) and were removed; call the domain
methods directly.
"""

from dataclasses import fields
from datetime import datetime
from enum import Enum
from typing import Any

# Direct imports to avoid circular dependency with __init__.py
from core.models.askesis.askesis_dto import (
    AskesisCreateDTO,
    AskesisDTO,
    AskesisUpdateDTO,
)
from core.models.askesis.askesis_request import (
    AskesisCreateRequest,
    AskesisUpdateRequest,
)
from core.models.type_hints import UserUID
from core.utils.uid_generator import UIDGenerator

# ==========================================================================
# Request → DTO Conversions
# ==========================================================================


def _enum_value(maybe_enum: Any) -> Any:
    """Return ``.value`` if given an Enum instance, else pass through.

    AskesisCreate/UpdateRequest use ``model_config = ConfigDict(use_enum_values=True)``,
    which Pydantic applies inconsistently in V2: explicit enum *inputs* are
    coerced to their str values, but enum *defaults* keep the enum instance
    on attribute access. Always normalize at the converter boundary.
    """
    return maybe_enum.value if isinstance(maybe_enum, Enum) else maybe_enum


def askesis_create_request_to_dto(
    request: AskesisCreateRequest, user_uid: UserUID
) -> AskesisCreateDTO:
    """Convert create request to DTO."""
    return AskesisCreateDTO(
        user_uid=user_uid,
        name=request.name,
        version=request.version,
        preferred_guidance_mode=_enum_value(request.preferred_guidance_mode),
        preferred_complexity_level=_enum_value(request.preferred_complexity_level),
    )


def askesis_update_request_to_dto(
    request: AskesisUpdateRequest, askesis_uid: str
) -> AskesisUpdateDTO:
    """Convert update request to DTO."""
    return AskesisUpdateDTO(
        uid=askesis_uid,
        name=request.name,
        version=request.version,
        preferred_guidance_mode=_enum_value(request.preferred_guidance_mode)
        if request.preferred_guidance_mode is not None
        else None,
        preferred_complexity_level=_enum_value(request.preferred_complexity_level)
        if request.preferred_complexity_level is not None
        else None,
        last_intelligence_update=datetime.now(),
    )


# ==========================================================================
# Update Application Functions
# ==========================================================================


# boundary: a pre-serialization patch of the DTO's mixed field types (str, float, int,
# list[str], datetime), serialized at the write (``to_neo4j_patch``).
def askesis_update_changes(update_dto: AskesisUpdateDTO) -> dict[str, Any]:
    """The partial patch an update DTO asks for: every field it sets, nothing else.

    A field left ``None`` is not in the patch, so the write leaves what the node holds.
    """
    return {
        field.name: getattr(update_dto, field.name)
        for field in fields(update_dto)
        if field.name != "uid" and getattr(update_dto, field.name) is not None
    }


# ==========================================================================
# Helper Functions
# ==========================================================================


def create_askesis_dto_from_create_dto(create_dto: AskesisCreateDTO) -> AskesisDTO:
    """Expand a CreateDTO into a full AskesisDTO with a fresh UID.

    UID is generated via UIDGenerator for consistency with the rest of SKUEL —
    the prior timestamp-and-user-uid format was a sketch from the initial
    commit that never reached the live path.
    """
    return AskesisDTO(
        uid=UIDGenerator.generate_random_uid("askesis"),
        user_uid=create_dto.user_uid,
        name=create_dto.name,
        version=create_dto.version,
        preferred_guidance_mode=create_dto.preferred_guidance_mode,
        preferred_complexity_level=create_dto.preferred_complexity_level,
        created_at=datetime.now(),
    )
