"""
Event Models - Three-Tier Architecture
=======================================

Clean three-tier model structure for Events:

1. event_request.py - External API models (Pydantic)
2. event_dto.py - Data transfer objects (Mutable)
3. event.py - Domain models with business logic (Immutable)

Usage:
    from core.models.event import Event, EventDTO, EventCreateRequest
"""

from .event import Event
from .event_dto import EventDTO

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
    # Domain model
    "Event",
    # API models
    "EventCreateRequest",
    # Transfer object
    "EventDTO",
    # Intelligence models
    "EventIntelligence",
    "EventListResponse",
    "EventParticipationContext",
    "EventPreparationLevel",
    "EventResponse",
    "EventType",
    "EventUpdateRequest",
]
