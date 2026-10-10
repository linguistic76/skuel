"""
Link Events
===========

Events published when a link between entities is written or removed.

The classes below are the catalog.
"""

from dataclasses import dataclass
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID


@dataclass(frozen=True)
class EntityLinksChanged(BaseEvent):
    """
    Published when a link door writes or removes an edge from a user's entity.

    ``UnifiedRelationshipService`` publishes it once per owner of the entity the
    link starts from, after the write succeeds — every link kind at once, so no
    door can forget it. An entity nobody owns (shared curriculum) publishes nothing.

    Subscribers:
    - UserService (invalidate the owner's cached context — every link-derived
      field, e.g. ``principle_supported_goals``, ``habits_by_goal``,
      ``life_path_goal_uids``, is read from these edges)
    """

    user_uid: UserUID
    entity_uid: str

    event_type: ClassVar[str] = "links.changed"
