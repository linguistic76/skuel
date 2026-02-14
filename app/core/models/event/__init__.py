"""
Event Models - Preserved Types
==============================

Event domain now uses the unified Ku model (core.models.ku).
This package preserves event-specific types that have no Ku equivalent:
- event_request.py - Event API request/response models (Pydantic)
- event_intelligence.py - Event intelligence dataclasses
- calendar_models.py - Calendar display models
"""

# Intelligence models
from .event_intelligence import (
    EnergyImpact,
    EventIntelligence,
    EventParticipationContext,
    EventPreparationLevel,
)
from .event_request import (
    EventCreateRequest,
    EventListResponse,
    EventResponse,
    EventType,
    EventUpdateRequest,
)

__all__ = [
    "EnergyImpact",
    # API models
    "EventCreateRequest",
    # Intelligence models
    "EventIntelligence",
    "EventListResponse",
    "EventParticipationContext",
    "EventPreparationLevel",
    "EventResponse",
    "EventType",
    "EventUpdateRequest",
]
