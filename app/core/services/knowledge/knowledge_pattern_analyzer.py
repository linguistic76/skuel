"""
KnowledgePatternAnalyzer
========================

Generic knowledge-pattern detection across any activity domain that has
Ku links. Detects five LearningPatternTypes that are meaningful for Goals,
Habits, Events, Choices, and Principles as well as Tasks.

Tasks extends this with a sixth pattern (MASTERY_VALIDATION) and
knowledge-aware priority scoring — see TaskKnowledgeAnalyzer.

Callers supply a ``fetch_rels`` coroutine that resolves the domain's
*Relationships object for a given entity UID. This decouples the analyzer
from any specific domain.

Usage::

    async def _fetch_goal_rels(uid: str) -> GoalRelationships:
        return await GoalRelationships.fetch(uid, self.relationships)


    analyzer = KnowledgePatternAnalyzer(graph_intel=self.graph_intel)
    result = await analyzer.analyze_learning_patterns(
        goals, fetch_rels=_fetch_goal_rels
    )
"""

from __future__ import annotations

import asyncio
import statistics
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel, CrossDomainImpactScore, InsightThreshold
from core.ports.knowledge_pattern_protocol import KnowledgeLinkedRelationships
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.entity import Entity
    from core.services.infrastructure.graph_intelligence_service import (
        GraphIntelligenceService,
    )


# ---------------------------------------------------------------------------
# Shared data classes (generic — used by all 6 activity domains)
# ---------------------------------------------------------------------------


class LearningPatternType(Enum):
    """Types of knowledge-learning patterns detected in user activities."""

    KNOWLEDGE_BUILDING = "knowledge_building"
    CROSS_DOMAIN_APPLICATION = "cross_domain_application"
    MASTERY_VALIDATION = "mastery_validation"  # Task-specific; emitted by TaskKnowledgeAnalyzer
    LEARNING_SPIRAL = "learning_spiral"
    SKILL_SPECIALIZATION = "skill_specialization"
    KNOWLEDGE_BRIDGING = "knowledge_bridging"


@dataclass
class LearningPattern:
    """A detected knowledge-learning pattern across user activities."""

    pattern_type: LearningPatternType
    knowledge_uids: list[str]
    entity_uids: list[str]
    confidence: float  # 0-1
    timeframe_days: int
    frequency: int
    growth_indicator: float  # -1 to 1; negative = decline, positive = growth
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MasteryProgression:
    """Mastery progression for a specific knowledge area."""

    knowledge_uid: str
    current_mastery_level: float  # 0-1
    mastery_trend: float  # -1 to 1
    activities_completed: int
    validation_activities_passed: int
    last_application_date: date | None
    progression_velocity: float  # mastery gain per day
    confidence_in_assessment: float  # 0-1
    next_recommended_difficulty: float  # 0-1


@dataclass
class ActivityInsight:
    """Insight generated from completed activities (replaces TaskInsight)."""

    insight_type: str
    title: str
    description: str
    knowledge_areas_involved: list[str]
    supporting_evidence: list[str]
    confidence: float  # 0-1
    actionable_recommendations: list[str]
    impact_score: float  # 0-1
    entity_uid: str = ""


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class KnowledgePatternAnalyzer:
    """
    Generic knowledge-pattern analyzer for any Ku-linked activity domain.

    Stateless — construct once per intelligence service; no per-call state.
    Relationship access goes through the caller-supplied ``fetch_rels``
    callable; ``graph_intel`` (optional) batch-resolves linked entities'
    ``sel_category`` field for cross-domain grouping — the field-based
    replacement for the former uid-namespace parsing (ADR-013 never-sniff:
    uids are opaque; without ``graph_intel`` no cross-domain patterns are
    detected rather than fabricating groups from uid strings).
    """

    def __init__(self, graph_intel: GraphIntelligenceService | None = None) -> None:
        self.logger = get_logger("skuel.analytics.knowledge_patterns")
        self.graph_intel = graph_intel

    async def resolve_categories(
        self, knowledge_uids: Sequence[str]
    ) -> dict[str, str]:  # skuel-lint: disable=SKUEL005 -- deliberate degrade-to-{}, see docstring
        """Map knowledge UIDs to their ``sel_category`` field (batch, one query).

        Deliberately NOT Result[T]: pattern analytics must never fail on a
        missing enrichment, so a failed lookup collapses to {} (logged) —
        "no cross-domain signal", never uid-string guessing. Returns {} too
        when ``graph_intel`` is absent or the input is empty.
        """
        unique_uids = list(dict.fromkeys(knowledge_uids))
        if not unique_uids or self.graph_intel is None:
            return {}
        result = await self.graph_intel.get_sel_categories(unique_uids)
        if result.is_error:
            self.logger.warning(
                "sel_category resolution failed — cross-domain detection degraded: %s",
                result.expect_error().message,
            )
            return {}
        return result.value or {}

    async def analyze_learning_patterns(
        self,
        entities: Sequence[Entity],
        fetch_rels: Callable[[str], Awaitable[KnowledgeLinkedRelationships]],
        timeframe_days: int = 30,
        complexity_fn: Callable[[Entity], float] | None = None,
    ) -> Result[list[LearningPattern]]:
        """
        Detect knowledge-learning patterns across a set of domain entities.

        Fetches relationship data for all entities in a single parallel batch,
        then runs five pattern detectors over the result.

        Args:
            entities: Domain entities to analyse (Task, Goal, Habit, …).
            fetch_rels: Coroutine that returns the domain's *Relationships for
                        a given entity UID.
            timeframe_days: Restrict analysis to entities created within this
                            many days.
            complexity_fn: Optional entity-level progression scorer for the
                           KNOWLEDGE_BUILDING detector. When None, falls back to
                           ``rels.knowledge_intensity()`` (edge-count based).
                           Pass a named function (SKUEL012) that extracts a
                           domain-specific difficulty signal from the entity,
                           e.g. ``Task.calculate_knowledge_complexity()``.

        Returns:
            Result[list[LearningPattern]] sorted by (confidence, frequency) desc.
        """
        try:
            cutoff = date.today() - timedelta(days=timeframe_days)
            recent = [e for e in entities if e.created_at.date() >= cutoff]

            if not recent:
                return Result.ok([])

            # Fetch all relationships in a single parallel batch.
            rels_list: list[KnowledgeLinkedRelationships] = list(
                await asyncio.gather(*[fetch_rels(e.uid) for e in recent])
            )
            entity_rels = list(zip(recent, rels_list, strict=False))

            # Filter to entities that actually have knowledge links.
            linked = [(e, r) for e, r in entity_rels if r.has_any_knowledge()]

            # One batched field lookup serves the cross-domain detector.
            all_linked_uids = [
                uid
                for _, r in linked
                for uid in (r.primary_knowledge_uids + r.secondary_knowledge_uids)
            ]
            ku_categories = await self.resolve_categories(all_linked_uids)

            patterns: list[LearningPattern] = []
            patterns.extend(self._detect_knowledge_building_patterns(linked, complexity_fn))
            patterns.extend(self._detect_cross_domain_patterns(linked, ku_categories))
            patterns.extend(self._detect_learning_spiral_patterns(linked))
            patterns.extend(self._detect_skill_specialization_patterns(linked))
            patterns.extend(self._detect_knowledge_bridging_patterns(linked))

            patterns.sort(key=_by_confidence_and_frequency, reverse=True)

            self.logger.info(
                "Knowledge patterns: %d detected across %d entities (%d days)",
                len(patterns),
                len(recent),
                timeframe_days,
            )
            return Result.ok(patterns)

        except DATA_CONVERSION_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(
                    message="Knowledge pattern analysis failed",
                    exception=e,
                    operation="analyze_learning_patterns",
                )
            )
        except Exception as e:  # safety-net: unexpected errors in analytics pipeline
            return Result.fail(
                Errors.system(
                    message="Knowledge pattern analysis failed",
                    exception=e,
                    operation="analyze_learning_patterns",
                )
            )

    # ------------------------------------------------------------------
    # Private pattern detectors
    # ------------------------------------------------------------------

    def _detect_knowledge_building_patterns(
        self,
        entity_rels: list[tuple[Entity, KnowledgeLinkedRelationships]],
        complexity_fn: Callable[[Entity], float] | None = None,
    ) -> list[LearningPattern]:
        """Detect progressive knowledge-building (increasing intensity over time).

        Uses ``complexity_fn(entity)`` when provided (e.g. Task.calculate_knowledge_complexity
        for difficulty-based progression) and falls back to ``rels.knowledge_intensity()``
        (edge-count based) otherwise.
        """
        patterns: list[LearningPattern] = []

        # Group by Ku area.
        ku_groups: dict[str, list[tuple[Entity, KnowledgeLinkedRelationships]]] = {}
        for entity, rels in entity_rels:
            all_uids = rels.primary_knowledge_uids + rels.secondary_knowledge_uids
            for ku_uid in all_uids:
                ku_groups.setdefault(ku_uid, []).append((entity, rels))

        for ku_uid, pairs in ku_groups.items():
            if len(pairs) < 3:
                continue
            pairs.sort(key=_pair_entity_created_at)
            if complexity_fn is not None:
                intensities = [complexity_fn(e) for e, _ in pairs]
            else:
                intensities = [r.knowledge_intensity() for _, r in pairs]
            if self._is_progressive_sequence(intensities):
                patterns.append(
                    LearningPattern(
                        pattern_type=LearningPatternType.KNOWLEDGE_BUILDING,
                        knowledge_uids=[ku_uid],
                        entity_uids=[e.uid for e, _ in pairs],
                        confidence=ConfidenceLevel.STANDARD,
                        timeframe_days=(pairs[-1][0].created_at - pairs[0][0].created_at).days,
                        frequency=len(pairs),
                        growth_indicator=self._calculate_growth_indicator(intensities),
                        metadata={"intensity_progression": intensities},
                    )
                )
        return patterns

    def _detect_cross_domain_patterns(
        self,
        entity_rels: list[tuple[Entity, KnowledgeLinkedRelationships]],
        ku_categories: dict[str, str],
    ) -> list[LearningPattern]:
        """Detect cross-domain knowledge application (entity spans ≥2 SEL categories).

        Grouping comes from the linked entities' ``sel_category`` FIELD
        (``ku_categories``, pre-resolved in one batch) — never from parsing
        uid strings, so authored and generated uids contribute alike.
        """
        patterns: list[LearningPattern] = []

        cross_domain = [
            (e, r)
            for e, r in entity_rels
            if len(
                set(
                    self._categories_for(
                        r.primary_knowledge_uids + r.secondary_knowledge_uids, ku_categories
                    )
                )
            )
            >= 2
        ]
        if len(cross_domain) < 2:
            return patterns

        domain_combos: dict[tuple[str, ...], list[tuple[Entity, KnowledgeLinkedRelationships]]] = {}
        for entity, rels in cross_domain:
            all_uids = rels.primary_knowledge_uids + rels.secondary_knowledge_uids
            domains = tuple(sorted(set(self._categories_for(all_uids, ku_categories))))
            domain_combos.setdefault(domains, []).append((entity, rels))

        for domains, pairs in domain_combos.items():
            if len(pairs) < 2:
                continue
            combined_ku: set[str] = set()
            for _, rels in pairs:
                combined_ku.update(rels.primary_knowledge_uids)
                combined_ku.update(rels.secondary_knowledge_uids)
            patterns.append(
                LearningPattern(
                    pattern_type=LearningPatternType.CROSS_DOMAIN_APPLICATION,
                    knowledge_uids=list(combined_ku),
                    entity_uids=[e.uid for e, _ in pairs],
                    confidence=ConfidenceLevel.MEDIUM,
                    timeframe_days=(pairs[-1][0].created_at - pairs[0][0].created_at).days,
                    frequency=len(pairs),
                    growth_indicator=CrossDomainImpactScore.NEUTRAL_GROWTH,
                    metadata={"sel_categories": list(domains)},
                )
            )
        return patterns

    def _detect_learning_spiral_patterns(
        self,
        entity_rels: list[tuple[Entity, KnowledgeLinkedRelationships]],
    ) -> list[LearningPattern]:
        """Detect spiral learning (returning to a Ku area after a gap)."""
        patterns: list[LearningPattern] = []

        ku_timelines: dict[str, list[tuple[datetime, Entity]]] = {}
        for entity, rels in entity_rels:
            all_uids = rels.primary_knowledge_uids + rels.secondary_knowledge_uids
            for ku_uid in all_uids:
                ku_timelines.setdefault(ku_uid, []).append((entity.created_at, entity))

        for ku_uid, timeline in ku_timelines.items():
            if len(timeline) < 4:
                continue
            timeline.sort(key=itemgetter(0))
            gaps = self._find_learning_gaps(timeline)
            if len(gaps) < 1:
                continue
            spiral_entities = [item[1] for item in timeline]
            patterns.append(
                LearningPattern(
                    pattern_type=LearningPatternType.LEARNING_SPIRAL,
                    knowledge_uids=[ku_uid],
                    entity_uids=[e.uid for e in spiral_entities],
                    confidence=ConfidenceLevel.LOW,
                    timeframe_days=(timeline[-1][0] - timeline[0][0]).days,
                    frequency=len(gaps) + 1,
                    growth_indicator=CrossDomainImpactScore.REINFORCEMENT_GROWTH,
                    metadata={"learning_cycles": len(gaps) + 1, "gaps_days": gaps},
                )
            )
        return patterns

    def _detect_skill_specialization_patterns(
        self,
        entity_rels: list[tuple[Entity, KnowledgeLinkedRelationships]],
    ) -> list[LearningPattern]:
        """Detect Ku specialization (≥30 % of entities touch the same Ku area)."""
        patterns: list[LearningPattern] = []
        if not entity_rels:
            return patterns

        total = len(entity_rels)
        ku_counts: dict[str, int] = {}
        for _, rels in entity_rels:
            for ku_uid in rels.primary_knowledge_uids + rels.secondary_knowledge_uids:
                ku_counts[ku_uid] = ku_counts.get(ku_uid, 0) + 1

        for ku_uid, count in ku_counts.items():
            ratio = count / total
            if ratio < CrossDomainImpactScore.SPECIALIZATION_RATIO_THRESHOLD or count < 3:
                continue
            specialized = [
                (e, r)
                for e, r in entity_rels
                if ku_uid in (r.primary_knowledge_uids + r.secondary_knowledge_uids)
            ]
            first_date = min(e.created_at for e, _ in specialized)
            last_date = max(e.created_at for e, _ in specialized)
            patterns.append(
                LearningPattern(
                    pattern_type=LearningPatternType.SKILL_SPECIALIZATION,
                    knowledge_uids=[ku_uid],
                    entity_uids=[e.uid for e, _ in specialized],
                    confidence=min(0.9, ratio * 2),
                    timeframe_days=(last_date - first_date).days,
                    frequency=count,
                    growth_indicator=CrossDomainImpactScore.SPECIALIZATION_GROWTH,
                    metadata={"specialization_ratio": ratio, "focus_intensity": count},
                )
            )
        return patterns

    def _detect_knowledge_bridging_patterns(
        self,
        entity_rels: list[tuple[Entity, KnowledgeLinkedRelationships]],
    ) -> list[LearningPattern]:
        """Detect knowledge bridges (entity links both primary and secondary Ku)."""
        patterns: list[LearningPattern] = []

        # An entity bridges knowledge if it has both primary (applied) and
        # secondary (prerequisite/inferred) Ku connections.
        bridging = [
            (e, r)
            for e, r in entity_rels
            if r.primary_knowledge_uids and r.secondary_knowledge_uids
        ]
        if len(bridging) < 2:
            return patterns

        bridge_combos: dict[tuple[frozenset[str], frozenset[str]], list[Entity]] = {}
        for entity, rels in bridging:
            key = (frozenset(rels.secondary_knowledge_uids), frozenset(rels.primary_knowledge_uids))
            bridge_combos.setdefault(key, []).append(entity)

        for (prereqs, applied), bridge_entities in bridge_combos.items():
            if len(bridge_entities) < 2:
                continue
            first_date = min(e.created_at for e in bridge_entities)
            last_date = max(e.created_at for e in bridge_entities)
            patterns.append(
                LearningPattern(
                    pattern_type=LearningPatternType.KNOWLEDGE_BRIDGING,
                    knowledge_uids=list(prereqs | applied),
                    entity_uids=[e.uid for e in bridge_entities],
                    confidence=ConfidenceLevel.STANDARD,
                    timeframe_days=(last_date - first_date).days,
                    frequency=len(bridge_entities),
                    growth_indicator=CrossDomainImpactScore.BRIDGING_GROWTH,
                    metadata={
                        "prerequisite_knowledge": list(prereqs),
                        "applied_knowledge": list(applied),
                    },
                )
            )
        return patterns

    # ------------------------------------------------------------------
    # Pure helpers (no I/O)
    # ------------------------------------------------------------------

    def _is_progressive_sequence(self, values: list[float]) -> bool:
        """True if ≥60 % of consecutive pairs show an increase."""
        if len(values) < 3:
            return False
        increases = sum(1 for i in range(1, len(values)) if values[i] > values[i - 1])
        return increases >= len(values) * 0.6

    def _calculate_growth_indicator(self, values: list[float]) -> float:
        """Growth indicator in [-1, 1]: compares first-half avg to second-half avg."""
        if len(values) < 2:
            return 0.0
        mid = len(values) // 2
        first_avg = statistics.mean(values[:mid]) if values[:mid] else 0.0
        second_avg = statistics.mean(values[mid:]) if values[mid:] else 0.0
        if first_avg == 0:
            return 1.0 if second_avg > 0 else 0.0
        return max(-1.0, min(1.0, (second_avg - first_avg) / first_avg))

    @staticmethod
    def _categories_for(knowledge_uids: list[str], ku_categories: dict[str, str]) -> list[str]:
        """SEL categories of the given knowledge UIDs, via the resolved field map.

        Replaces the former uid-namespace parser: uids are opaque identity
        (ADR-013 never-sniff) — grouping comes from the ``sel_category``
        field. UIDs with no resolved category drop out (deliberately
        unassigned is valid; they simply carry no cross-domain signal).
        """
        return [ku_categories[uid] for uid in knowledge_uids if uid in ku_categories]

    def _find_learning_gaps(self, timeline: list[tuple[datetime, Any]]) -> list[int]:
        """Return gap lengths (days) that exceed InsightThreshold.LEARNING_GAP_DAYS."""
        gaps = []
        for i in range(1, len(timeline)):
            gap = (timeline[i][0] - timeline[i - 1][0]).days
            if gap > InsightThreshold.LEARNING_GAP_DAYS:
                gaps.append(gap)
        return gaps


# ---------------------------------------------------------------------------
# Module-level sort key (SKUEL012 — no lambdas)
# ---------------------------------------------------------------------------


def _by_confidence_and_frequency(pattern: LearningPattern) -> tuple[float, int]:
    return (pattern.confidence, pattern.frequency)


def _pair_entity_created_at(pair: tuple[Entity, Any]) -> datetime:
    return pair[0].created_at
