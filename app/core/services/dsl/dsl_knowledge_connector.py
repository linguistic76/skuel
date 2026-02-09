"""
DSL Knowledge Graph Connector
=============================

Connects DSL-parsed activities (with type-safe EntityType contexts) to the semantic knowledge graph.

This is the bridge that makes journals truly semantic:
- @ku() tags create APPLIES_KNOWLEDGE edges
- @link(goal:) tags create CONTRIBUTES_TO_GOAL edges
- @link(principle:) tags create ALIGNS_WITH_PRINCIPLE edges
- @energy() states can link to energy-related knowledge units

The connector transforms user intent (expressed via DSL) into graph relationships,
building a rich semantic network that captures how knowledge flows into action.

**Type Safety:**

ParsedActivityLine now uses `list[EntityType]` for contexts. This module uses
EntityType enum comparisons for determining relationship types, providing
compile-time verification of entity type handling.

Philosophy:
    "Applied knowledge, not pure theory" - SKUEL measures knowledge by how it's LIVED.
    This connector is the mechanism that tracks when knowledge moves from theory to practice.

Version: 0.2.0 (Type-safe EntityType contexts)
Date: 2025-11-28
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from core.infrastructure.relationships.semantic_relationships import (
    SemanticRelationshipType,
)
from core.models.enums import EntityType
from core.services.dsl.activity_dsl_parser import ParsedActivityLine, ParsedJournal
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.dsl.knowledge_connector")


# ============================================================================
# RELATIONSHIP SERVICE PROTOCOLS
# ============================================================================


@runtime_checkable
class HasLinkKnowledge(Protocol):
    """Protocol for relationship services with link_knowledge() method."""

    async def link_knowledge(
        self,
        entity_uid: str,
        knowledge_uid: str,
        relationship_type: Any,
        properties: dict[str, Any],
    ) -> Result[bool]:
        """Link entity to knowledge unit."""
        ...


@runtime_checkable
class HasLinkGoal(Protocol):
    """Protocol for relationship services with link_goal() method."""

    async def link_goal(
        self,
        entity_uid: str,
        goal_uid: str,
        relationship_type: Any,
        properties: dict[str, Any],
    ) -> Result[bool]:
        """Link entity to goal."""
        ...


@runtime_checkable
class HasLinkPrinciple(Protocol):
    """Protocol for relationship services with link_principle() method."""

    async def link_principle(
        self,
        entity_uid: str,
        principle_uid: str,
        relationship_type: Any,
        properties: dict[str, Any],
    ) -> Result[bool]:
        """Link entity to principle."""
        ...


@runtime_checkable
class HasCreateRelationship(Protocol):
    """Protocol for relationship services with generic create_relationship() method."""

    async def create_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: str,
        properties: dict[str, Any],
    ) -> Result[bool]:
        """Create a generic relationship."""
        ...


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class KnowledgeConnection:
    """
    Represents a connection between an activity and a knowledge unit.

    This is the intermediate representation before graph edge creation.
    """

    source_uid: str  # The activity UID (task:123, habit:456)
    target_uid: str  # The knowledge unit UID (ku:tech/python)
    relationship_type: SemanticRelationshipType
    confidence: float = 0.8  # How confident we are in this connection
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_cypher_params(self) -> dict[str, Any]:
        """Convert to parameters for Cypher relationship creation."""
        return {
            "source_uid": self.source_uid,
            "target_uid": self.target_uid,
            "rel_type": self.relationship_type.value,
            "confidence": self.confidence,
            "created_at": datetime.now().isoformat(),
            "source": "dsl_parser",
            **self.metadata,
        }


@dataclass
class GoalConnection:
    """Connection between an activity and a goal."""

    source_uid: str
    goal_uid: str
    relationship_type: SemanticRelationshipType = field(
        default=SemanticRelationshipType.CONTRIBUTES_TO_GOAL
    )
    contribution_weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PrincipleConnection:
    """Connection between an activity and a guiding principle."""

    source_uid: str
    principle_uid: str
    relationship_type: SemanticRelationshipType = field(
        default=SemanticRelationshipType.ALIGNS_WITH_PRINCIPLE
    )
    alignment_score: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DSLConnectionPlan:
    """
    Complete plan for graph connections from a parsed activity.

    This encapsulates all the relationships that should be created
    when an activity is converted to an entity.
    """

    activity_description: str
    knowledge_connections: list[KnowledgeConnection] = field(default_factory=list)
    goal_connections: list[GoalConnection] = field(default_factory=list)
    principle_connections: list[PrincipleConnection] = field(default_factory=list)

    @property
    def total_connections(self) -> int:
        return (
            len(self.knowledge_connections)
            + len(self.goal_connections)
            + len(self.principle_connections)
        )

    @property
    def has_knowledge_links(self) -> bool:
        return len(self.knowledge_connections) > 0

    @property
    def has_goal_links(self) -> bool:
        return len(self.goal_connections) > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API responses or debugging."""
        return {
            "activity": self.activity_description,
            "knowledge_connections": [
                {
                    "target": c.target_uid,
                    "type": c.relationship_type.value,
                    "confidence": c.confidence,
                }
                for c in self.knowledge_connections
            ],
            "goal_connections": [
                {
                    "goal": c.goal_uid,
                    "type": c.relationship_type.value,
                    "weight": c.contribution_weight,
                }
                for c in self.goal_connections
            ],
            "principle_connections": [
                {
                    "principle": c.principle_uid,
                    "type": c.relationship_type.value,
                    "alignment": c.alignment_score,
                }
                for c in self.principle_connections
            ],
            "total_connections": self.total_connections,
        }


# ============================================================================
# CONNECTION BUILDER
# ============================================================================


class DSLKnowledgeConnector:
    """
    Builds knowledge graph connection plans from DSL-parsed activities.

    This service analyzes ParsedActivityLine objects and determines:
    1. What knowledge units the activity applies (@ku, @link(ku:))
    2. What goals the activity contributes to (@link(goal:))
    3. What principles the activity aligns with (@link(principle:))

    The result is a DSLConnectionPlan that can be executed by relationship services.

    Usage:
        connector = DSLKnowledgeConnector()

        # Plan connections for a single activity
        plan = connector.plan_connections(parsed_activity)

        # Plan connections for entire journal
        plans = connector.plan_journal_connections(parsed_journal)

        # Execute connections (requires relationship service)
        await connector.execute_connections(plan, entity_uid, relationship_service)
    """

    def __init__(self) -> None:
        """Initialize the connector."""
        self.logger = get_logger("skuel.dsl.knowledge_connector")

    def plan_connections(
        self,
        activity: ParsedActivityLine,
        source_uid: str | None = None,
    ) -> DSLConnectionPlan:
        """
        Build a connection plan for a single parsed activity.

        Args:
            activity: The parsed activity line
            source_uid: Optional UID if entity already created

        Returns:
            DSLConnectionPlan with all planned graph connections
        """
        plan = DSLConnectionPlan(activity_description=activity.description)

        # Use placeholder if no UID yet (will be replaced during execution)
        uid = source_uid or "pending:activity"

        # Extract knowledge connections from @ku() and @link(ku:)
        self._add_knowledge_connections(activity, uid, plan)

        # Extract goal connections from @link(goal:)
        self._add_goal_connections(activity, uid, plan)

        # Extract principle connections from @link(principle:)
        self._add_principle_connections(activity, uid, plan)

        self.logger.debug(
            f"Planned {plan.total_connections} connections for: {activity.description[:50]}"
        )

        return plan

    def plan_journal_connections(self, journal: ParsedJournal) -> list[DSLConnectionPlan]:
        """
        Build connection plans for all activities in a parsed journal.

        Args:
            journal: The parsed journal with activities

        Returns:
            List of DSLConnectionPlan, one per activity
        """
        plans = []

        for activity in journal.activities:
            plan = self.plan_connections(activity)
            if plan.total_connections > 0:
                plans.append(plan)

        self.logger.info(
            f"Planned connections for {len(plans)} activities "
            f"({sum(p.total_connections for p in plans)} total connections)"
        )

        return plans

    def _add_knowledge_connections(
        self,
        activity: ParsedActivityLine,
        source_uid: str,
        plan: DSLConnectionPlan,
    ) -> None:
        """Extract and add knowledge unit connections."""
        knowledge_uids = activity.get_linked_knowledge()

        for ku_uid in knowledge_uids:
            # Determine relationship type based on activity context
            rel_type = self._determine_knowledge_relationship(activity)

            connection = KnowledgeConnection(
                source_uid=source_uid,
                target_uid=ku_uid,
                relationship_type=rel_type,
                confidence=0.9 if activity.primary_ku == ku_uid else 0.8,
                metadata={
                    "activity_contexts": activity.context_values,  # String values for serialization
                    "is_primary": activity.primary_ku == ku_uid,
                },
            )
            plan.knowledge_connections.append(connection)

    def _add_goal_connections(
        self,
        activity: ParsedActivityLine,
        source_uid: str,
        plan: DSLConnectionPlan,
    ) -> None:
        """Extract and add goal connections."""
        goal_uids = activity.get_linked_goals()

        for goal_uid in goal_uids:
            # Get primary context as string for metadata, default to "task"
            activity_type = activity.primary_context.value if activity.primary_context else "task"

            connection = GoalConnection(
                source_uid=source_uid,
                goal_uid=goal_uid,
                relationship_type=SemanticRelationshipType.CONTRIBUTES_TO_GOAL,
                contribution_weight=self._calculate_goal_weight(activity),
                metadata={
                    "activity_type": activity_type,
                },
            )
            plan.goal_connections.append(connection)

    def _add_principle_connections(
        self,
        activity: ParsedActivityLine,
        source_uid: str,
        plan: DSLConnectionPlan,
    ) -> None:
        """Extract and add principle connections."""
        principle_uids = activity.get_linked_principles()

        for principle_uid in principle_uids:
            connection = PrincipleConnection(
                source_uid=source_uid,
                principle_uid=principle_uid,
                relationship_type=SemanticRelationshipType.ALIGNS_WITH_PRINCIPLE,
                alignment_score=1.0,
            )
            plan.principle_connections.append(connection)

    def _determine_knowledge_relationship(
        self, activity: ParsedActivityLine
    ) -> SemanticRelationshipType:
        """
        Determine the most appropriate semantic relationship type.

        Based on the activity context (using type-safe EntityType), we choose
        different relationship types:
        - task → APPLIES_KNOWLEDGE_TO (applying knowledge in action)
        - learning → INFORMED_BY_KNOWLEDGE (learning informed by KU)
        - habit → REINFORCES_KNOWLEDGE (habit reinforces understanding)
        - event → PRACTICES_VIA_EVENT (practicing at an event)

        Type Safety:
            Uses EntityType enum comparisons instead of string matching,
            providing compile-time verification of entity type handling.
        """
        # Type-safe EntityType set for O(1) lookup
        contexts = set(activity.contexts)

        if EntityType.LEARNING in contexts:
            return SemanticRelationshipType.INFORMED_BY_KNOWLEDGE

        if EntityType.HABIT in contexts:
            return SemanticRelationshipType.REINFORCES_KNOWLEDGE

        if EntityType.EVENT in contexts:
            return SemanticRelationshipType.PRACTICES_VIA_EVENT

        # Default for tasks
        return SemanticRelationshipType.APPLIES_KNOWLEDGE_TO

    def _calculate_goal_weight(self, activity: ParsedActivityLine) -> float:
        """
        Calculate how much an activity contributes to its linked goal.

        Higher priority tasks contribute more to goal progress.
        """
        if activity.priority is None:
            return 1.0

        # Priority 1 (critical) = 2.0, Priority 5 (low) = 0.5
        weights = {1: 2.0, 2: 1.5, 3: 1.0, 4: 0.75, 5: 0.5}
        return weights.get(activity.priority, 1.0)


# ============================================================================
# CONNECTION EXECUTOR
# ============================================================================


class DSLConnectionExecutor:
    """
    Executes planned graph connections via relationship services.

    This class takes DSLConnectionPlans and creates actual graph edges.
    It requires access to the appropriate relationship services.

    Usage:
        executor = DSLConnectionExecutor(
            tasks_relationship_service=tasks_rels,
            knowledge_backend=ku_backend,
        )

        # Execute a connection plan
        result = await executor.execute_plan(plan, entity_uid="task:123")
    """

    def __init__(
        self,
        tasks_relationship_service: Any | None = None,
        habits_relationship_service: Any | None = None,
        goals_relationship_service: Any | None = None,
        events_relationship_service: Any | None = None,
        knowledge_backend: Any | None = None,
    ) -> None:
        """Initialize with relationship services."""
        self.tasks_rels = tasks_relationship_service
        self.habits_rels = habits_relationship_service
        self.goals_rels = goals_relationship_service
        self.events_rels = events_relationship_service
        self.knowledge_backend = knowledge_backend
        self.logger = get_logger("skuel.dsl.connection_executor")

    async def execute_plan(
        self,
        plan: DSLConnectionPlan,
        entity_uid: str,
        entity_type: str = "task",
    ) -> Result[dict[str, Any]]:
        """
        Execute all connections in a plan.

        Args:
            plan: The connection plan to execute
            entity_uid: The UID of the created entity
            entity_type: Type of entity (task, habit, goal, event)

        Returns:
            Result with execution statistics
        """
        stats = {
            "knowledge_created": 0,
            "knowledge_failed": 0,
            "goal_created": 0,
            "goal_failed": 0,
            "principle_created": 0,
            "principle_failed": 0,
        }

        # Execute knowledge connections
        for conn in plan.knowledge_connections:
            result = await self._create_knowledge_edge(entity_uid, conn, entity_type)
            if result.is_ok:
                stats["knowledge_created"] += 1
            else:
                stats["knowledge_failed"] += 1
                self.logger.warning(f"Failed to create knowledge edge: {conn.target_uid}")

        # Execute goal connections
        for conn in plan.goal_connections:
            result = await self._create_goal_edge(entity_uid, conn, entity_type)
            if result.is_ok:
                stats["goal_created"] += 1
            else:
                stats["goal_failed"] += 1

        # Execute principle connections
        for conn in plan.principle_connections:
            result = await self._create_principle_edge(entity_uid, conn, entity_type)
            if result.is_ok:
                stats["principle_created"] += 1
            else:
                stats["principle_failed"] += 1

        total_created = (
            stats["knowledge_created"] + stats["goal_created"] + stats["principle_created"]
        )
        total_failed = stats["knowledge_failed"] + stats["goal_failed"] + stats["principle_failed"]

        self.logger.info(
            f"Executed connection plan: {total_created} created, {total_failed} failed"
        )

        return Result.ok(stats)

    async def _create_knowledge_edge(
        self,
        entity_uid: str,
        connection: KnowledgeConnection,
        entity_type: str,
    ) -> Result[bool]:
        """Create a knowledge application edge."""
        # Select the appropriate relationship service
        rel_service = self._get_relationship_service(entity_type)

        if not rel_service:
            return Result.fail(
                Errors.system(
                    message=f"No relationship service for {entity_type}",
                    operation="create_knowledge_edge",
                )
            )

        # Use the relationship service to create the edge
        # This will vary based on your actual relationship service API
        try:
            # Most relationship services have a method like:
            # await rel_service.link_knowledge(entity_uid, ku_uid, relationship_type, properties)

            if isinstance(rel_service, HasLinkKnowledge):
                return await rel_service.link_knowledge(
                    entity_uid,
                    connection.target_uid,
                    connection.relationship_type,
                    {
                        "confidence": connection.confidence,
                        "source": "dsl_parser",
                        **connection.metadata,
                    },
                )

            # Fallback: use generic create_relationship if available
            if isinstance(rel_service, HasCreateRelationship):
                return await rel_service.create_relationship(
                    from_uid=entity_uid,
                    to_uid=connection.target_uid,
                    relationship_type=connection.relationship_type.value,
                    properties=connection.to_cypher_params(),
                )

            return Result.fail(
                Errors.system(
                    message="Relationship service missing required methods",
                    operation="create_knowledge_edge",
                )
            )

        except Exception as e:
            return Result.fail(
                Errors.system(
                    message=f"Failed to create edge: {e}",
                    operation="create_knowledge_edge",
                    exception=e,
                )
            )

    async def _create_goal_edge(
        self,
        entity_uid: str,
        connection: GoalConnection,
        entity_type: str,
    ) -> Result[bool]:
        """Create a goal contribution edge."""
        rel_service = self._get_relationship_service(entity_type)

        if not rel_service:
            return Result.fail(
                Errors.system(
                    message=f"No relationship service for {entity_type}",
                    operation="create_goal_edge",
                )
            )

        try:
            if isinstance(rel_service, HasLinkGoal):
                return await rel_service.link_goal(
                    entity_uid,
                    connection.goal_uid,
                    connection.relationship_type,
                    {"contribution_weight": connection.contribution_weight},
                )

            if isinstance(rel_service, HasCreateRelationship):
                return await rel_service.create_relationship(
                    from_uid=entity_uid,
                    to_uid=connection.goal_uid,
                    relationship_type=connection.relationship_type.value,
                    properties={
                        "contribution_weight": connection.contribution_weight,
                        "source": "dsl_parser",
                    },
                )

            return Result.fail(
                Errors.system(
                    message="Missing goal linking method",
                    operation="create_goal_edge",
                )
            )

        except Exception as e:
            return Result.fail(
                Errors.system(
                    message=f"Failed to create goal edge: {e}",
                    exception=e,
                )
            )

    async def _create_principle_edge(
        self,
        entity_uid: str,
        connection: PrincipleConnection,
        entity_type: str,
    ) -> Result[bool]:
        """Create a principle alignment edge."""
        rel_service = self._get_relationship_service(entity_type)

        if not rel_service:
            return Result.fail(
                Errors.system(
                    message=f"No relationship service for {entity_type}",
                    operation="create_principle_edge",
                )
            )

        try:
            if isinstance(rel_service, HasLinkPrinciple):
                return await rel_service.link_principle(
                    entity_uid,
                    connection.principle_uid,
                    connection.relationship_type,
                    {"alignment_score": connection.alignment_score},
                )

            if isinstance(rel_service, HasCreateRelationship):
                return await rel_service.create_relationship(
                    from_uid=entity_uid,
                    to_uid=connection.principle_uid,
                    relationship_type=connection.relationship_type.value,
                    properties={
                        "alignment_score": connection.alignment_score,
                        "source": "dsl_parser",
                    },
                )

            return Result.fail(
                Errors.system(
                    message="Missing principle linking method",
                    operation="create_principle_edge",
                )
            )

        except Exception as e:
            return Result.fail(
                Errors.system(
                    message=f"Failed to create principle edge: {e}",
                    exception=e,
                )
            )

    def _get_relationship_service(self, entity_type: str) -> Any | None:
        """Get the appropriate relationship service for an entity type."""
        services = {
            "task": self.tasks_rels,
            "habit": self.habits_rels,
            "goal": self.goals_rels,
            "event": self.events_rels,
        }
        return services.get(entity_type)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def plan_activity_connections(activity: ParsedActivityLine) -> DSLConnectionPlan:
    """
    Convenience function to plan connections for a single activity.

    Args:
        activity: Parsed activity line

    Returns:
        Connection plan ready for execution
    """
    connector = DSLKnowledgeConnector()
    return connector.plan_connections(activity)


def plan_journal_connections(journal: ParsedJournal) -> list[DSLConnectionPlan]:
    """
    Convenience function to plan connections for a journal.

    Args:
        journal: Parsed journal

    Returns:
        List of connection plans
    """
    connector = DSLKnowledgeConnector()
    return connector.plan_journal_connections(journal)
