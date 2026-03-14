"""
KU Relationships Helper (Graph-Native Pattern - Hybrid Design)

Container for knowledge unit relationship data fetched from graph.
Extends the Domain Relationships Pattern with semantic relationship support.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from core.services.lesson.lesson_graph_service import LessonGraphService
from core.services.lesson.lesson_semantic_service import LessonSemanticService
from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel
from core.utils.result_simplified import Result

# Type alias for consistency with other domains
KuRelationshipService = UnifiedRelationshipService


# Query specifications for fetch_via_unified path
KU_QUERY_SPECS: list[tuple[str, str]] = [
    ("prerequisite_uids", "requires"),
    ("enables_uids", "enables"),
    ("related_uids", "related"),
    ("broader_uids", "broader"),
    ("narrower_uids", "narrower"),
    ("part_of_path_uids", "in_steps"),
    ("applied_in_task_uids", "applied_in_tasks"),
    ("practiced_in_event_uids", "practiced_in_events"),
    ("reinforced_by_habit_uids", "reinforced_by_habits"),
]


@dataclass(frozen=True)
class KuRelationships:
    """
    Container for all knowledge unit relationship data (fetched from Neo4j graph).

    Hybrid Design: Simple UID lists + Optional rich semantic context.

    Two fetch paths:
    - fetch() — via LessonGraphService (supports semantic context)
    - fetch_via_unified() — via UnifiedRelationshipService (consistent pattern)
    """

    # Curriculum relationships (KU → KU)
    prerequisite_uids: list[str] = field(default_factory=list)
    enables_uids: list[str] = field(default_factory=list)
    related_uids: list[str] = field(default_factory=list)
    broader_uids: list[str] = field(default_factory=list)
    narrower_uids: list[str] = field(default_factory=list)

    # Cross-domain relationships (KU → Other Domains)
    part_of_path_uids: list[str] = field(default_factory=list)
    applied_in_task_uids: list[str] = field(default_factory=list)
    practiced_in_event_uids: list[str] = field(default_factory=list)
    reinforced_by_habit_uids: list[str] = field(default_factory=list)

    # Semantic context (rich metadata - optional)
    semantic_context: dict[str, Any] | None = None

    @classmethod
    async def fetch(
        cls,
        ku_uid: str,
        graph_service: LessonGraphService,
        semantic_service: LessonSemanticService | None = None,
        include_semantic_context: bool = False,
    ) -> KuRelationships:
        """Fetch all relationship data from graph in parallel via LessonGraphService."""
        # Execute all relationship queries in parallel
        results = await asyncio.gather(
            _get_prerequisites(graph_service, ku_uid),
            _get_enables(graph_service, ku_uid),
            _get_related_knowledge(graph_service, ku_uid),
            _get_broader_concepts(graph_service, ku_uid),
            _get_narrower_concepts(graph_service, ku_uid),
            _get_learning_paths(graph_service, ku_uid),
            _get_applying_tasks(graph_service, ku_uid),
            _get_practicing_events(graph_service, ku_uid),
            _get_reinforcing_habits(graph_service, ku_uid),
        )

        # Optional: Fetch rich semantic context
        semantic_context = None
        if include_semantic_context and semantic_service:
            context_result = await semantic_service.get_semantic_neighborhood(
                ku_uid, min_confidence=0.7
            )
            semantic_context = context_result.value if context_result.is_ok else None

        return cls(
            prerequisite_uids=_extract_uids(results[0]),
            enables_uids=_extract_uids(results[1]),
            related_uids=_extract_uids(results[2]),
            broader_uids=_extract_uids(results[3]),
            narrower_uids=_extract_uids(results[4]),
            part_of_path_uids=_extract_uids(results[5]),
            applied_in_task_uids=_extract_uids(results[6]),
            practiced_in_event_uids=_extract_uids(results[7]),
            reinforced_by_habit_uids=_extract_uids(results[8]),
            semantic_context=semantic_context,
        )

    @classmethod
    async def fetch_via_unified(
        cls,
        ku_uid: str,
        relationship_service: UnifiedRelationshipService,
    ) -> KuRelationships:
        """Fetch all relationship data via UnifiedRelationshipService."""
        return await fetch_relationships_parallel(
            uid=ku_uid,
            service=relationship_service,
            query_specs=KU_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> KuRelationships:
        """Create empty KuRelationships (for testing or new KUs)."""
        return cls()

    # Simple helpers
    def has_prerequisites(self) -> bool:
        """Check if KU has prerequisite knowledge requirements."""
        return len(self.prerequisite_uids) > 0

    def enables_other_knowledge(self) -> bool:
        """Check if KU enables other knowledge units."""
        return len(self.enables_uids) > 0

    def has_related_knowledge(self) -> bool:
        """Check if KU has related knowledge units."""
        return len(self.related_uids) > 0

    def has_curriculum_relationships(self) -> bool:
        """Check if KU has any curriculum relationships (prerequisites, enables, related)."""
        return (
            len(self.prerequisite_uids) > 0
            or len(self.enables_uids) > 0
            or len(self.related_uids) > 0
        )

    def is_applied_in_practice(self) -> bool:
        """Check if KU is applied in any activities (tasks, events, habits)."""
        return (
            len(self.applied_in_task_uids) > 0
            or len(self.practiced_in_event_uids) > 0
            or len(self.reinforced_by_habit_uids) > 0
        )

    def is_part_of_curriculum(self) -> bool:
        """Check if KU is part of any learning paths."""
        return len(self.part_of_path_uids) > 0

    def is_foundational(self) -> bool:
        """Check if KU is foundational (no prerequisites, enables other knowledge)."""
        return not self.has_prerequisites() and self.enables_other_knowledge()

    def is_advanced(self) -> bool:
        """Check if KU is advanced (has multiple prerequisites)."""
        return len(self.prerequisite_uids) >= 2

    def total_curriculum_connections(self) -> int:
        """Get total count of curriculum relationships."""
        return (
            len(self.prerequisite_uids)
            + len(self.enables_uids)
            + len(self.related_uids)
            + len(self.broader_uids)
            + len(self.narrower_uids)
        )

    def total_application_count(self) -> int:
        """Get total count of activity applications."""
        return (
            len(self.applied_in_task_uids)
            + len(self.practiced_in_event_uids)
            + len(self.reinforced_by_habit_uids)
        )

    def prerequisite_count(self) -> int:
        """Get count of prerequisites."""
        return len(self.prerequisite_uids)

    def enables_count(self) -> int:
        """Get count of knowledge units enabled."""
        return len(self.enables_uids)

    # Semantic helpers (when semantic_context available)
    def get_high_confidence_prerequisites(self, min_confidence: float = 0.8) -> list[str]:
        """Get prerequisites with high confidence scores."""
        if not self.semantic_context:
            return self.prerequisite_uids

        relationships = self.semantic_context.get("relationships", [])
        high_conf_prereqs = []
        for rel in relationships:
            if (
                rel.get("type") == "REQUIRES_KNOWLEDGE"
                and rel.get("confidence", 0.0) >= min_confidence
            ):
                target_uid = rel.get("target_uid")
                if target_uid:
                    high_conf_prereqs.append(target_uid)
        return high_conf_prereqs

    def has_strong_prerequisites(self, min_count: int = 2, min_confidence: float = 0.8) -> bool:
        """Check if KU has well-defined prerequisites."""
        high_conf = self.get_high_confidence_prerequisites(min_confidence)
        return len(high_conf) >= min_count

    def get_all_knowledge_uids(self) -> set[str]:
        """Get all unique knowledge unit UIDs across all curriculum relationships."""
        all_uids: set[str] = set()
        all_uids.update(self.prerequisite_uids)
        all_uids.update(self.enables_uids)
        all_uids.update(self.related_uids)
        all_uids.update(self.broader_uids)
        all_uids.update(self.narrower_uids)
        return all_uids


# ========================================================================
# HELPER QUERY FUNCTIONS (for LessonGraphService fetch path)
# ========================================================================


async def _get_prerequisites(graph_service: LessonGraphService, ku_uid: str) -> Result:
    """Get prerequisite knowledge units (REQUIRES relationship)."""
    try:
        return await graph_service.find_prerequisites(ku_uid, depth=1)
    except Exception as e:
        from core.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to get prerequisites for {ku_uid}: {e}")
        return Result.ok([])


async def _get_enables(graph_service: LessonGraphService, ku_uid: str) -> Result:
    """Get knowledge units this KU enables (ENABLES relationship)."""
    try:
        return await graph_service.find_next_steps(ku_uid, limit=100)
    except Exception as e:
        from core.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to get enables for {ku_uid}: {e}")
        return Result.ok([])


async def _get_related_knowledge(graph_service: LessonGraphService, ku_uid: str) -> Result:
    """Get related knowledge units (RELATED_TO relationship)."""
    try:
        query = """
            MATCH (ku:Entity {uid: $ku_uid})-[:RELATED_TO]-(related:Entity)
            RETURN related.uid as uid
            LIMIT 50
        """
        params = {"ku_uid": ku_uid}
        results = await graph_service.neo4j.execute_query(query, params)
        uids = [record["uid"] for record in results]
        return Result.ok(uids)
    except Exception as e:
        from core.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to get related knowledge for {ku_uid}: {e}")
        return Result.ok([])


async def _get_broader_concepts(graph_service: LessonGraphService, ku_uid: str) -> Result:
    """Get broader concepts (HAS_BROADER relationship)."""
    try:
        query = """
            MATCH (ku:Entity {uid: $ku_uid})-[:HAS_BROADER]->(broader:Entity)
            RETURN broader.uid as uid
            LIMIT 20
        """
        params = {"ku_uid": ku_uid}
        results = await graph_service.neo4j.execute_query(query, params)
        uids = [record["uid"] for record in results]
        return Result.ok(uids)
    except Exception as e:
        from core.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to get broader concepts for {ku_uid}: {e}")
        return Result.ok([])


async def _get_narrower_concepts(graph_service: LessonGraphService, ku_uid: str) -> Result:
    """Get narrower concepts (HAS_NARROWER relationship)."""
    try:
        query = """
            MATCH (ku:Entity {uid: $ku_uid})-[:HAS_NARROWER]->(narrower:Entity)
            RETURN narrower.uid as uid
            LIMIT 50
        """
        params = {"ku_uid": ku_uid}
        results = await graph_service.neo4j.execute_query(query, params)
        uids = [record["uid"] for record in results]
        return Result.ok(uids)
    except Exception as e:
        from core.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to get narrower concepts for {ku_uid}: {e}")
        return Result.ok([])


async def _get_learning_paths(graph_service: LessonGraphService, ku_uid: str) -> Result:
    """Get learning paths containing this KU."""
    try:
        query = """
            MATCH (lp:Lp)-[:CONTAINS_KNOWLEDGE|INCLUDES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
            RETURN lp.uid as uid
            LIMIT 50
        """
        params = {"ku_uid": ku_uid}
        results = await graph_service.neo4j.execute_query(query, params)
        uids = [record["uid"] for record in results]
        return Result.ok(uids)
    except Exception as e:
        from core.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to get learning paths for {ku_uid}: {e}")
        return Result.ok([])


async def _get_applying_tasks(graph_service: LessonGraphService, ku_uid: str) -> Result:
    """Get tasks applying this knowledge."""
    try:
        query = """
            MATCH (task:Task)-[:APPLIES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
            RETURN task.uid as uid
            LIMIT 100
        """
        params = {"ku_uid": ku_uid}
        results = await graph_service.neo4j.execute_query(query, params)
        uids = [record["uid"] for record in results]
        return Result.ok(uids)
    except Exception as e:
        from core.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to get applying tasks for {ku_uid}: {e}")
        return Result.ok([])


async def _get_practicing_events(graph_service: LessonGraphService, ku_uid: str) -> Result:
    """Get events practicing this knowledge."""
    try:
        query = """
            MATCH (event:Event)-[:PRACTICES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
            RETURN event.uid as uid
            LIMIT 100
        """
        params = {"ku_uid": ku_uid}
        results = await graph_service.neo4j.execute_query(query, params)
        uids = [record["uid"] for record in results]
        return Result.ok(uids)
    except Exception as e:
        from core.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to get practicing events for {ku_uid}: {e}")
        return Result.ok([])


async def _get_reinforcing_habits(graph_service: LessonGraphService, ku_uid: str) -> Result:
    """Get habits reinforcing this knowledge."""
    try:
        query = """
            MATCH (habit:Habit)-[:APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
            RETURN habit.uid as uid
            LIMIT 100
        """
        params = {"ku_uid": ku_uid}
        results = await graph_service.neo4j.execute_query(query, params)
        uids = [record["uid"] for record in results]
        return Result.ok(uids)
    except Exception as e:
        from core.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to get reinforcing habits for {ku_uid}: {e}")
        return Result.ok([])


def _extract_uids(result: Result) -> list[str]:
    """Extract UIDs from Result[list[DTO]] or Result[list[str]]."""
    if not result.is_ok:
        return []

    items = result.value
    if not items:
        return []

    if isinstance(items[0], str):
        return items

    return [item.uid for item in items]
