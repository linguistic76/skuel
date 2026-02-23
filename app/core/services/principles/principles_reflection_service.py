"""
Principles Reflection Service
==============================

Handles reflection persistence and analytics for principles.

Responsibilities:
- Save reflections with graph relationships
- Get reflection history for a principle
- Calculate alignment trends
- Cross-domain insights (which activities align best)
- Conflict detection

Follows HabitCompletion pattern: reflections are graph-connected entities
that capture moments of alignment assessment.

Graph Schema:
    (User)-[:MADE_REFLECTION]->(PrincipleReflection)-[:REFLECTS_ON]->(Principle)
                                        |
                                        +-[:TRIGGERED_BY]->(Goal|Habit|Event|Choice)
                                        |
                                        +-[:REVEALS_CONFLICT]->(Principle)
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from core.events import publish_event
from core.events.principle_events import PrincipleConflictRevealed, PrincipleReflectionRecorded
from core.models.enums.principle_enums import AlignmentLevel
from core.models.principle.reflection import PrincipleReflection
from core.models.principle.reflection_dto import PrincipleReflectionDTO
from core.models.relationship_names import RelationshipName
from core.ports import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import (
    get_alignment_average,
    get_conflict_count,
    make_dict_count_getter,
)

logger = get_logger(__name__)


@dataclass
class AlignmentTrend:
    """Alignment trend data for a principle over time."""

    principle_uid: str
    period_start: date
    period_end: date
    reflection_count: int
    average_alignment: float  # 0-4 scale based on AlignmentLevel
    trend_direction: str  # "improving", "declining", "stable"
    quality_average: float  # 0-1 based on reflection quality
    trigger_distribution: dict[str, int]  # Count by trigger type


@dataclass
class CrossDomainInsight:
    """Insight about which domain triggers align best with a principle."""

    principle_uid: str
    trigger_type: str
    reflection_count: int
    alignment_average: float
    most_common_alignment: str


class PrinciplesReflectionService:
    """
    Service for principle reflection operations.

    This service handles:
    - Saving reflections with full graph connectivity
    - Retrieving reflection history
    - Calculating alignment trends
    - Cross-domain insight generation
    - Conflict detection and tracking

    Graph Relationships Created:
    - (User)-[:MADE_REFLECTION]->(Reflection)
    - (Reflection)-[:REFLECTS_ON]->(Principle)
    - (Reflection)-[:TRIGGERED_BY]->(Goal|Habit|Event|Choice) (if triggered)
    - (Reflection)-[:REVEALS_CONFLICT]->(Principle) (if conflict detected)

    Architecture Note:
        This service intentionally does NOT extend BaseService.
        PrincipleReflection is a "secondary entity" - it tracks user engagement
        with a primary entity (Principle). Secondary entities:
        - Are queried via their parent entity, not directly
        - Don't need CRUD route factories
        - Handle ownership via User relationship, not verify_ownership()
        - Have simpler lifecycle (create, query - rarely update)

        See: /docs/patterns/SECONDARY_ENTITY_PATTERN.md
    """

    def __init__(
        self,
        backend: "BackendOperations[PrincipleReflection]",
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize reflection service.

        Args:
            backend: Backend for reflection persistence
            event_bus: Event bus for publishing domain events
        """
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("principles.reflection")

    # ========================================================================
    # CORE OPERATIONS
    # ========================================================================

    @with_error_handling("save_reflection", error_type="database")
    async def save_reflection(
        self,
        principle_uid: str,
        user_uid: str,
        alignment_level: AlignmentLevel,
        evidence: str,
        reflection_notes: str | None = None,
        trigger_type: str | None = None,
        trigger_uid: str | None = None,
        trigger_context: str | None = None,
        conflicting_principle_uids: Sequence[str] | None = None,
    ) -> Result[PrincipleReflection]:
        """
        Save a reflection with full graph connectivity.

        Creates the reflection node and establishes relationships:
        - MADE_REFLECTION from user
        - REFLECTS_ON to principle
        - TRIGGERED_BY to triggering entity (if provided)
        - REVEALS_CONFLICT to conflicting principles (if provided)

        Args:
            principle_uid: UID of the principle being reflected on
            user_uid: UID of the user making the reflection
            alignment_level: How well actions aligned with the principle
            evidence: What was observed (required)
            reflection_notes: Optional additional thoughts
            trigger_type: What triggered this reflection (goal, habit, event, choice, manual)
            trigger_uid: UID of triggering entity
            trigger_context: Context description for the trigger
            conflicting_principle_uids: UIDs of principles that conflict

        Returns:
            Result containing the created PrincipleReflection
        """
        # Validate required fields
        if not evidence or len(evidence.strip()) < 5:
            return Result.fail(
                Errors.validation(
                    message="Evidence must be at least 5 characters",
                    field="evidence",
                    value=evidence,
                )
            )

        # Create DTO with quality scoring
        dto = PrincipleReflectionDTO.create(
            principle_uid=principle_uid,
            user_uid=user_uid,
            alignment_level=alignment_level,
            evidence=evidence,
            reflection_notes=reflection_notes,
            trigger_type=trigger_type,
            trigger_uid=trigger_uid,
            trigger_context=trigger_context,
        )

        # Persist to Neo4j
        create_result = await self.backend.create(dto.to_dict())
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        reflection_uid = dto.uid

        # Create relationships
        await self._create_reflection_relationships(
            reflection_uid=reflection_uid,
            principle_uid=principle_uid,
            user_uid=user_uid,
            trigger_type=trigger_type,
            trigger_uid=trigger_uid,
            conflicting_principle_uids=conflicting_principle_uids,
        )

        # Publish events
        await self._publish_reflection_events(
            dto=dto,
            conflicting_principle_uids=conflicting_principle_uids,
        )

        # Convert to domain model
        reflection = PrincipleReflection.from_dto(dto)

        self.logger.info(
            f"Saved reflection {reflection_uid} on principle {principle_uid} "
            f"(alignment: {alignment_level.value}, quality: {dto.reflection_quality_score:.2f})"
        )

        return Result.ok(reflection)

    async def _create_reflection_relationships(
        self,
        reflection_uid: str,
        principle_uid: str,
        user_uid: str,
        trigger_type: str | None,
        trigger_uid: str | None,
        conflicting_principle_uids: Sequence[str] | None,
    ) -> None:
        """Create graph relationships for a reflection."""
        # (User)-[:MADE_REFLECTION]->(Reflection)
        await self.backend.add_relationship(
            from_uid=user_uid,
            to_uid=reflection_uid,
            relationship_type=RelationshipName.MADE_REFLECTION,
        )

        # (Reflection)-[:REFLECTS_ON]->(Principle)
        await self.backend.add_relationship(
            from_uid=reflection_uid,
            to_uid=principle_uid,
            relationship_type=RelationshipName.REFLECTS_ON,
        )

        # (Reflection)-[:TRIGGERED_BY]->(Trigger) if triggered by entity
        if trigger_type and trigger_uid and trigger_type != "manual":
            await self.backend.add_relationship(
                from_uid=reflection_uid,
                to_uid=trigger_uid,
                relationship_type=RelationshipName.TRIGGERED_BY,
                properties={"trigger_type": trigger_type},
            )

        # (Reflection)-[:REVEALS_CONFLICT]->(Principle) for each conflict
        if conflicting_principle_uids:
            for conflict_uid in conflicting_principle_uids:
                await self.backend.add_relationship(
                    from_uid=reflection_uid,
                    to_uid=conflict_uid,
                    relationship_type=RelationshipName.REVEALS_CONFLICT,
                )

    async def _publish_reflection_events(
        self,
        dto: PrincipleReflectionDTO,
        conflicting_principle_uids: Sequence[str] | None,
    ) -> None:
        """Publish events for a saved reflection."""
        # Main reflection event
        event = PrincipleReflectionRecorded(
            reflection_uid=dto.uid,
            principle_uid=dto.principle_uid,
            user_uid=dto.user_uid,
            alignment_level=dto.alignment_level.value,
            evidence=dto.evidence,
            occurred_at=dto.created_at,
            trigger_type=dto.trigger_type,
            trigger_uid=dto.trigger_uid,
            reflection_quality_score=dto.reflection_quality_score,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Conflict events
        if conflicting_principle_uids:
            for conflict_uid in conflicting_principle_uids:
                conflict_event = PrincipleConflictRevealed(
                    reflection_uid=dto.uid,
                    principle_uid=dto.principle_uid,
                    conflicting_principle_uid=conflict_uid,
                    user_uid=dto.user_uid,
                    occurred_at=dto.created_at,
                    conflict_context=dto.trigger_context,
                )
                await publish_event(self.event_bus, conflict_event, self.logger)

    # ========================================================================
    # RETRIEVAL OPERATIONS
    # ========================================================================

    @with_error_handling("get_reflections_for_principle", error_type="database")
    async def get_reflections_for_principle(
        self,
        principle_uid: str,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[PrincipleReflection]]:
        """
        Get reflection history for a principle.

        Args:
            principle_uid: UID of the principle
            user_uid: UID of the user (for ownership verification)
            limit: Maximum number of reflections to return

        Returns:
            Result containing list of reflections, ordered by date descending
        """
        query = """
        MATCH (r:PrincipleReflection)-[:REFLECTS_ON]->(p:Principle {uid: $principle_uid})
        WHERE r.user_uid = $user_uid
        RETURN r
        ORDER BY r.reflection_date DESC, r.created_at DESC
        LIMIT $limit
        """

        params = {
            "principle_uid": principle_uid,
            "user_uid": user_uid,
            "limit": limit,
        }

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        reflections = []
        for record in result.value:
            data = dict(record["r"])
            dto = PrincipleReflectionDTO.from_dict(data)
            reflection = PrincipleReflection.from_dto(dto)
            reflections.append(reflection)

        return Result.ok(reflections)

    @with_error_handling("get_recent_reflections", error_type="database")
    async def get_recent_reflections(
        self,
        user_uid: str,
        days: int = 7,
        limit: int = 20,
    ) -> Result[list[PrincipleReflection]]:
        """
        Get recent reflections across all principles.

        Args:
            user_uid: UID of the user
            days: Number of days to look back
            limit: Maximum number of reflections

        Returns:
            Result containing list of recent reflections
        """
        cutoff_date = date.today() - timedelta(days=days)

        query = """
        MATCH (r:PrincipleReflection)
        WHERE r.user_uid = $user_uid
          AND r.reflection_date >= date($cutoff_date)
        RETURN r
        ORDER BY r.reflection_date DESC, r.created_at DESC
        LIMIT $limit
        """

        params = {
            "user_uid": user_uid,
            "cutoff_date": cutoff_date.isoformat(),
            "limit": limit,
        }

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        reflections = []
        for record in result.value:
            data = dict(record["r"])
            dto = PrincipleReflectionDTO.from_dict(data)
            reflection = PrincipleReflection.from_dto(dto)
            reflections.append(reflection)

        return Result.ok(reflections)

    # ========================================================================
    # ANALYTICS
    # ========================================================================

    @with_error_handling("calculate_alignment_trend", error_type="database")
    async def calculate_alignment_trend(
        self,
        principle_uid: str,
        user_uid: str,
        days: int = 30,
    ) -> Result[AlignmentTrend]:
        """
        Calculate alignment trend for a principle over time.

        Args:
            principle_uid: UID of the principle
            user_uid: UID of the user
            days: Number of days to analyze

        Returns:
            Result containing alignment trend data
        """
        period_start = date.today() - timedelta(days=days)
        period_end = date.today()

        # Get reflections in period
        query = """
        MATCH (r:PrincipleReflection)-[:REFLECTS_ON]->(p:Principle {uid: $principle_uid})
        WHERE r.user_uid = $user_uid
          AND r.reflection_date >= date($period_start)
          AND r.reflection_date <= date($period_end)
        RETURN r.alignment_level as alignment,
               r.reflection_quality_score as quality,
               r.trigger_type as trigger_type
        """

        params = {
            "principle_uid": principle_uid,
            "user_uid": user_uid,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        }

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if not records:
            return Result.ok(
                AlignmentTrend(
                    principle_uid=principle_uid,
                    period_start=period_start,
                    period_end=period_end,
                    reflection_count=0,
                    average_alignment=0.0,
                    trend_direction="stable",
                    quality_average=0.0,
                    trigger_distribution={},
                )
            )

        # Calculate metrics
        alignment_scores = []
        quality_scores = []
        trigger_counts: dict[str, int] = {}

        for record in records:
            # Map alignment level to numeric score
            alignment_str = record["alignment"]
            alignment = AlignmentLevel(alignment_str)
            score = self._alignment_to_score(alignment)
            alignment_scores.append(score)

            quality_scores.append(record.get("quality", 0.0) or 0.0)

            trigger = record.get("trigger_type") or "manual"
            trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1

        # Calculate average and trend
        avg_alignment = sum(alignment_scores) / len(alignment_scores)
        avg_quality = sum(quality_scores) / len(quality_scores)

        # Determine trend direction by comparing first half to second half
        mid = len(alignment_scores) // 2
        if mid > 0:
            first_half_avg = sum(alignment_scores[:mid]) / mid
            second_half_avg = sum(alignment_scores[mid:]) / (len(alignment_scores) - mid)
            diff = second_half_avg - first_half_avg

            if diff > 0.5:
                trend_direction = "improving"
            elif diff < -0.5:
                trend_direction = "declining"
            else:
                trend_direction = "stable"
        else:
            trend_direction = "stable"

        return Result.ok(
            AlignmentTrend(
                principle_uid=principle_uid,
                period_start=period_start,
                period_end=period_end,
                reflection_count=len(records),
                average_alignment=avg_alignment,
                trend_direction=trend_direction,
                quality_average=avg_quality,
                trigger_distribution=trigger_counts,
            )
        )

    def _alignment_to_score(self, alignment: AlignmentLevel) -> float:
        """Convert alignment level to numeric score (0-4)."""
        scores = {
            AlignmentLevel.ALIGNED: 4.0,
            AlignmentLevel.MOSTLY_ALIGNED: 3.0,
            AlignmentLevel.PARTIAL: 2.0,
            AlignmentLevel.MISALIGNED: 1.0,
            AlignmentLevel.UNKNOWN: 0.0,
        }
        return scores.get(alignment, 0.0)

    @with_error_handling("get_cross_domain_insights", error_type="database")
    async def get_cross_domain_insights(
        self,
        principle_uid: str,
        user_uid: str,
    ) -> Result[list[CrossDomainInsight]]:
        """
        Get insights about which domains align best with a principle.

        Analyzes reflections to determine which trigger types
        (goals, habits, events, choices) produce the best alignment.

        Args:
            principle_uid: UID of the principle
            user_uid: UID of the user

        Returns:
            Result containing insights by trigger type
        """
        query = """
        MATCH (r:PrincipleReflection)-[:REFLECTS_ON]->(p:Principle {uid: $principle_uid})
        WHERE r.user_uid = $user_uid
          AND r.trigger_type IS NOT NULL
        WITH r.trigger_type as trigger_type,
             collect(r.alignment_level) as alignments
        RETURN trigger_type,
               size(alignments) as count,
               alignments
        """

        params = {
            "principle_uid": principle_uid,
            "user_uid": user_uid,
        }

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        insights = []
        for record in result.value:
            trigger_type = record["trigger_type"]
            alignments = record["alignments"]
            count = record["count"]

            # Calculate average alignment
            scores = [self._alignment_to_score(AlignmentLevel(a)) for a in alignments]
            avg_alignment = sum(scores) / len(scores) if scores else 0.0

            # Find most common alignment
            alignment_counts: dict[str, int] = {}
            for a in alignments:
                alignment_counts[a] = alignment_counts.get(a, 0) + 1
            count_getter = make_dict_count_getter(alignment_counts)
            most_common = max(alignment_counts.keys(), key=count_getter)

            insights.append(
                CrossDomainInsight(
                    principle_uid=principle_uid,
                    trigger_type=trigger_type,
                    reflection_count=count,
                    alignment_average=avg_alignment,
                    most_common_alignment=most_common,
                )
            )

        # Sort by alignment average descending
        insights.sort(key=get_alignment_average, reverse=True)

        return Result.ok(insights)

    @with_error_handling("get_reflection_frequency", error_type="database")
    async def get_reflection_frequency(
        self,
        user_uid: str,
        days: int = 30,
    ) -> Result[dict[str, Any]]:
        """
        Get reflection frequency metrics for a user.

        Args:
            user_uid: UID of the user
            days: Number of days to analyze

        Returns:
            Result containing frequency metrics
        """
        cutoff_date = date.today() - timedelta(days=days)

        query = """
        MATCH (r:PrincipleReflection)
        WHERE r.user_uid = $user_uid
          AND r.reflection_date >= date($cutoff_date)
        WITH r.reflection_date as ref_date, count(*) as daily_count
        RETURN collect({date: ref_date, count: daily_count}) as daily_reflections,
               sum(daily_count) as total_count
        """

        params = {
            "user_uid": user_uid,
            "cutoff_date": cutoff_date.isoformat(),
        }

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.ok(
                {
                    "total_reflections": 0,
                    "days_with_reflections": 0,
                    "average_per_day": 0.0,
                    "reflection_streak": 0,
                }
            )

        record = result.value[0]
        total = record.get("total_count", 0) or 0
        daily = record.get("daily_reflections", []) or []

        days_with_reflections = len(daily)
        avg_per_day = total / days if days > 0 else 0.0

        return Result.ok(
            {
                "total_reflections": total,
                "days_with_reflections": days_with_reflections,
                "average_per_day": round(avg_per_day, 2),
                "period_days": days,
            }
        )

    @with_error_handling("get_conflict_analysis", error_type="database")
    async def get_conflict_analysis(
        self,
        principle_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Analyze conflicts revealed through reflections for a principle.

        This method:
        - Finds all conflicts revealed through reflections
        - Counts occurrences of each conflicting principle
        - Identifies patterns in when conflicts arise
        - Provides resolution insights

        Args:
            principle_uid: UID of the principle to analyze
            user_uid: UID of the user

        Returns:
            Result containing conflict analysis data:
            - conflicting_principles: List of {uid, name, conflict_count, contexts}
            - total_conflicts: Total conflict revelations
            - most_frequent_conflict: UID of most frequent conflicting principle
            - conflict_contexts: Common situations where conflicts arise
        """
        query = """
        MATCH (r:PrincipleReflection)-[:REFLECTS_ON]->(p:Principle {uid: $principle_uid})
        WHERE r.user_uid = $user_uid
        OPTIONAL MATCH (r)-[:REVEALS_CONFLICT]->(cp:Principle)
        WITH r, cp
        WHERE cp IS NOT NULL
        RETURN cp.uid as conflict_uid,
               cp.name as conflict_name,
               r.trigger_context as context,
               r.trigger_type as trigger_type,
               r.reflection_date as date
        """

        params = {
            "principle_uid": principle_uid,
            "user_uid": user_uid,
        }

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.ok(
                {
                    "conflicting_principles": [],
                    "total_conflicts": 0,
                    "most_frequent_conflict": None,
                    "conflict_contexts": [],
                }
            )

        # Aggregate conflict data
        conflicts_by_principle: dict[str, dict[str, Any]] = {}
        all_contexts: list[str] = []

        for record in result.value:
            conflict_uid = record["conflict_uid"]
            conflict_name = record.get("conflict_name", "Unknown")
            context = record.get("context")
            trigger_type = record.get("trigger_type")

            if conflict_uid not in conflicts_by_principle:
                conflicts_by_principle[conflict_uid] = {
                    "uid": conflict_uid,
                    "name": conflict_name,
                    "conflict_count": 0,
                    "contexts": [],
                    "trigger_types": [],
                }

            conflicts_by_principle[conflict_uid]["conflict_count"] += 1

            if context:
                conflicts_by_principle[conflict_uid]["contexts"].append(context)
                all_contexts.append(context)

            if trigger_type:
                conflicts_by_principle[conflict_uid]["trigger_types"].append(trigger_type)

        # Sort by conflict count and convert to list
        conflicting_principles = sorted(
            conflicts_by_principle.values(),
            key=get_conflict_count,
            reverse=True,
        )

        # Find most frequent
        most_frequent = conflicting_principles[0]["uid"] if conflicting_principles else None

        # Deduplicate contexts (get unique situations)
        unique_contexts = list(set(all_contexts))[:10]  # Top 10 unique contexts

        total_conflicts = sum(p["conflict_count"] for p in conflicting_principles)

        return Result.ok(
            {
                "conflicting_principles": conflicting_principles,
                "total_conflicts": total_conflicts,
                "most_frequent_conflict": most_frequent,
                "conflict_contexts": unique_contexts,
            }
        )
