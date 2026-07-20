"""
Relationship Backend Protocol
=============================

Port for the relationship backend that lives below the hexagonal
boundary (``adapters/persistence/neo4j/``) and authors parameterized Cypher
against a ``Neo4jQueryExecutor``:

- ``UserRelationshipOperations`` — user-centric graph edges (PINNED,
  PINNED_TODAY, PURSUING_GOAL, FOLLOWS, MEMBER_OF).
  Implementation: ``adapters/persistence/neo4j/user_relationship_backend.py``

Core-layer consumers (orchestrators, the user-intelligence factory) depend on
this protocol, never on the concrete adapter class — keeping the
dependency arrow pointed inward (ADR-044).

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.models.type_hints import EntityUID, UserUID
from core.utils.result_simplified import Result


@runtime_checkable
class UserRelationshipOperations(Protocol):
    """Graph relationship operations for User entities.

    Replaces denormalized UID list fields (pinned/goals/following/teams) with
    pure Neo4j graph queries. All values are passed as ``$param`` placeholders;
    labels and relationship types come from the ``RelationshipName`` enum.
    """

    # Pinned entities
    async def get_pinned_entities(self, user_uid: UserUID) -> Result[list[str]]: ...
    async def pin_entity(self, user_uid: UserUID, entity_uid: EntityUID) -> Result[bool]: ...
    async def unpin_entity(self, user_uid: UserUID, entity_uid: EntityUID) -> Result[bool]: ...

    # Today-scoped pins
    async def get_today_pinned(self, user_uid: UserUID) -> Result[set[str]]: ...
    async def pin_for_today(self, user_uid: UserUID, entity_uid: EntityUID) -> Result[bool]: ...
    async def unpin_for_today(self, user_uid: UserUID, entity_uid: EntityUID) -> Result[bool]: ...
    async def reorder_pins(
        self, user_uid: UserUID, ordered_entity_uids: list[str]
    ) -> Result[int]: ...

    # Current goals
    async def get_current_goals(self, user_uid: UserUID) -> Result[list[str]]: ...

    # Social connections
    async def get_following(self, user_uid: UserUID) -> Result[set[str]]: ...
    async def get_followers(self, user_uid: UserUID) -> Result[set[str]]: ...

    # Group membership
    async def get_teams(self, user_uid: UserUID) -> Result[set[str]]: ...

    # Existence checks
    async def has_pinned_entities(self, user_uid: UserUID) -> Result[bool]: ...
    async def has_active_goals(self, user_uid: UserUID) -> Result[bool]: ...
    async def is_following(self, user_uid: UserUID, other_user_uid: UserUID) -> Result[bool]: ...
    async def is_team_member(self, user_uid: UserUID, team_uid: str) -> Result[bool]: ...

    # Counts / summaries
    async def count_pinned_entities(self, user_uid: UserUID) -> Result[int]: ...
    async def get_social_stats(self, user_uid: UserUID) -> Result[dict[str, int]]: ...
    async def get_user_summary(self, user_uid: UserUID) -> Result[dict[str, Any]]: ...

    # Batch creation
    async def create_user_relationships(
        self,
        user_uid: UserUID,
        pinned_entity_uids: list[str] | None = None,
        current_goal_uids: list[str] | None = None,
        following_uids: list[str] | None = None,
        team_uids: list[str] | None = None,
    ) -> Result[int]: ...
