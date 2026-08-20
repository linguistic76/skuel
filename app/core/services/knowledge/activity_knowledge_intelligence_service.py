"""
Activity Knowledge Intelligence Service
========================================

Knowledge intelligence for ANY activity domain entity.

Extracted from TasksIntelligenceService (March 2026) because these methods
are domain-agnostic — they work on entity titles, graph relationships, and
shared utilities. All 6 activity domains have the same graph connections
to Knowledge Units:

    Tasks:      APPLIES_KNOWLEDGE, REQUIRES_KNOWLEDGE
    Goals:      REQUIRES_KNOWLEDGE
    Habits:     REINFORCES_KNOWLEDGE
    Events:     APPLIES_KNOWLEDGE, REINFORCES_KNOWLEDGE
    Choices:    INFORMS_CHOICE (reversed direction)
    Principles: GROUNDED_IN_KNOWLEDGE

Provides:
- Knowledge suggestions from entity patterns
- Knowledge unit generation from completed entities
- Knowledge prerequisites analysis
- Learning opportunities discovery

Architecture:
- Extends BaseAnalyticsService (graph-based, NO AI dependencies)
- Uses shared intelligence utilities (PatternAnalyzer, intelligence_queries)
- Uses GraphIntelligenceService for graph traversal (infrastructure only)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth
from core.models.type_hints import EntityUID, UserUID

if TYPE_CHECKING:
    from core.ports.query_types import KnowledgePrerequisitesResult
from core.models.entity import Entity
from core.models.enums import EntityStatus, Priority
from core.models.enums.neo_labels import NeoLabel
from core.ports.base_protocols import BackendOperations
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import PatternAnalyzer
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_second_item

# =============================================================================
# HELPER FUNCTIONS (SKUEL012 - no lambdas)
# =============================================================================


def _extract_lowercase_title(entity: Any) -> str:
    """Extract lowercase title from entity for text analysis."""
    return entity.title.lower()


class ActivityKnowledgeIntelligenceService(BaseAnalyticsService[BackendOperations[Entity], Entity]):
    """
    Knowledge intelligence for ANY activity domain entity.

    Satisfies the KnowledgeIntelligenceOperations protocol (4 methods):
    get_knowledge_suggestions, generate_knowledge_from_entities,
    get_knowledge_prerequisites, get_learning_opportunities.

    These methods analyze how activities connect to knowledge — they are not
    specific to any single activity domain. All 6 activity domains (Tasks,
    Goals, Habits, Events, Choices, Principles) have graph relationships
    to Knowledge Units.

    Uses an Entity-level backend (NeoLabel.ENTITY) so queries like
    find_by(user_uid=...) return user-owned activity entities across all
    domains. Shared entities (PathStep, Ku, etc.) lack user_uid and naturally
    filter out.

    NOTE: This service does NOT use AI (LLM/embeddings).
    All methods are pure graph queries + Python calculations.
    """

    _service_name = "knowledge.activity_intelligence"

    # ========================================================================
    # KNOWLEDGE INTELLIGENCE - Domain-agnostic implementations
    # ========================================================================

    async def get_knowledge_suggestions(
        self, user_uid: UserUID, entity_uid: EntityUID | None = None
    ) -> Result[dict[str, Any]]:
        """
        Generate knowledge suggestions from entity patterns.

        Analyzes:
        - Frequent entity types and patterns
        - Repeated problem-solving approaches
        - Skills used across entities
        - Knowledge gaps from incomplete entities

        Returns:
            Result containing:
            - entity_patterns: List of patterns with knowledge suggestions
            - learning_opportunities: Identified learning opportunities
            - knowledge_gaps: Areas where knowledge would help
        """
        scope = f"entity {entity_uid}" if entity_uid else f"all entities for user {user_uid}"
        self.logger.info(f"Generating knowledge suggestions for {scope}")

        if entity_uid:
            entity_result = await self.backend.get(entity_uid)
            if entity_result.is_error:
                return Result.fail(entity_result)

            if not entity_result.value:
                return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))

            entities = [entity_result.value]
        else:
            entities_result = await self.backend.find_by(
                user_uid=user_uid, status=EntityStatus.COMPLETED
            )

            if entities_result.is_error:
                return Result.fail(entities_result)

            entities = entities_result.value

        # Analyze entity patterns
        patterns = self._analyze_entity_patterns(entities)

        # Generate suggestions from patterns
        suggestions = [
            {
                "pattern": pattern["name"],
                "knowledge_suggestion": f"Create knowledge unit for {pattern['name']}",
                "confidence": min(0.5 + (pattern["frequency"] / 20), 0.95),
                "frequency": pattern["frequency"],
            }
            for pattern in patterns
            if pattern["frequency"] >= 3
        ]

        # Identify learning opportunities
        learning_opportunities = self._identify_learning_opportunities(entities)

        # Identify knowledge gaps
        knowledge_gaps = self._identify_knowledge_gaps(entities)

        # Build metadata
        metadata: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "user_uid": user_uid,
            "entities_analyzed": len(entities),
        }
        if entity_uid:
            metadata["entity_uid"] = entity_uid
            metadata["scope"] = "single_entity"
        else:
            metadata["scope"] = "all_user_entities"

        return Result.ok(
            {
                "entity_patterns": suggestions,
                "learning_opportunities": learning_opportunities,
                "knowledge_gaps": knowledge_gaps,
                "metadata": metadata,
            }
        )

    async def generate_knowledge_from_entities(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Generate knowledge units from completed entities.

        Args:
            user_uid: User identifier
            period_days: Period to analyze (default 30 days)

        Returns:
            Result containing:
            - knowledge_units: Proposed knowledge units
            - patterns_discovered: Discovered patterns
            - documentation_suggestions: Documentation recommendations
        """
        self.logger.info(f"Generating knowledge units from entities for user {user_uid}")

        cutoff_date = datetime.now() - timedelta(days=period_days)
        entities_result = await self.backend.find_by(
            user_uid=user_uid, status=EntityStatus.COMPLETED
        )

        if entities_result.is_error:
            return Result.fail(entities_result)

        entities = entities_result.value
        recent_entities = [
            entity for entity in entities if entity.updated_at and entity.updated_at >= cutoff_date
        ]

        # Extract patterns
        patterns = self._analyze_entity_patterns(recent_entities)

        # Generate knowledge units from patterns
        knowledge_units = [
            {
                "title": f"{pattern['name']} Best Practices",
                "content": f"Knowledge extracted from {pattern['frequency']} {pattern['name']} entities",
                "source_entities": [
                    e.uid for e in recent_entities if pattern["name"].lower() in e.title.lower()
                ],
                "confidence": min(0.5 + (pattern["frequency"] / 10), 0.95),
                "type": "best_practice",
            }
            for pattern in patterns
            if pattern["frequency"] >= 2
        ]

        return Result.ok(
            {
                "knowledge_units": knowledge_units,
                "patterns_discovered": [p["name"] for p in patterns],
                "documentation_suggestions": self._generate_documentation_suggestions(patterns),
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "period_days": period_days,
                    "entities_analyzed": len(recent_entities),
                },
            }
        )

    async def get_knowledge_prerequisites(
        self, entity_uid: EntityUID
    ) -> Result[KnowledgePrerequisitesResult]:
        """
        Analyze knowledge prerequisites for any entity using graph intelligence.

        Uses shared intelligence utilities (no cross-service dependency).

        Args:
            entity_uid: Entity UID (any activity domain)

        Returns:
            Result containing prerequisite knowledge and learning path
        """
        from core.utils.intelligence_queries import get_knowledge_prerequisites

        if self.graph_intel is None:
            empty: KnowledgePrerequisitesResult = {}
            return Result.ok(empty)

        return await get_knowledge_prerequisites(
            graph=self.graph_intel, entity_uid=entity_uid, depth=GraphDepth.DEFAULT
        )

    # ========================================================================
    # LEARNING INTELLIGENCE - Domain-agnostic implementations
    # ========================================================================

    async def get_learning_opportunities(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """
        Discover learning opportunities from entity patterns.

        Analyzes:
        - Failed or incomplete entities
        - Entities taking longer than expected
        - Entities blocked by knowledge gaps
        - Skills used successfully

        Returns:
            Result containing:
            - opportunities: List of learning opportunities
            - recommended_focus: Suggested focus areas
            - estimated_impact: Impact assessment
        """
        self.logger.info(f"Discovering learning opportunities for user {user_uid}")

        entities_result = await self.backend.find_by(user_uid=user_uid)

        if entities_result.is_error:
            return Result.fail(entities_result)

        entities = entities_result.value

        opportunities: list[dict[str, Any]] = []

        # Find entities with knowledge requirements (requires graph intelligence)
        if self.graph_intel:
            for entity in entities:
                context_result = await self.graph_intel.get_entity_context(
                    entity.uid, GraphDepth.NEIGHBORHOOD
                )

                if context_result.is_ok:
                    context = context_result.value
                    knowledge_nodes = [
                        node
                        for node in context.nodes
                        if node.labels and NeoLabel.ENTITY.value in node.labels
                    ]

                    if knowledge_nodes:
                        priority_value = getattr(entity, "priority", None)
                        is_high = (
                            priority_value is not None
                            and Priority(priority_value).to_numeric() >= 3
                        )
                        opportunities.append(
                            {
                                "type": "knowledge_gap",
                                "title": f"Learn concepts for: {entity.title}",
                                "entity_uid": entity.uid,
                                "required_knowledge": [
                                    n.properties.get("title", "Unknown") for n in knowledge_nodes
                                ],
                                "priority": "high" if is_high else "medium",
                            }
                        )

        # Identify skill development opportunities
        skill_opportunities = await self._identify_skill_opportunities(entities)
        opportunities.extend(skill_opportunities)

        # Determine recommended focus
        recommended_focus = self._determine_focus_areas(opportunities)

        # Estimate impact
        impact_assessment = self._estimate_learning_impact(opportunities)

        return Result.ok(
            {
                "opportunities": opportunities[:10],
                "recommended_focus": recommended_focus,
                "estimated_impact": impact_assessment,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "opportunities_found": len(opportunities),
                },
            }
        )

    # ========================================================================
    # HELPER METHODS - Internal analysis functions
    # ========================================================================

    def _analyze_entity_patterns(self, entities: list) -> list[dict[str, Any]]:
        """Analyze patterns in entity titles and descriptions."""
        return PatternAnalyzer.extract_word_frequencies(
            [entity.title for entity in entities], min_word_length=5, top_n=10
        )

    def _identify_learning_opportunities(self, entities: list) -> list[str]:
        """Identify learning opportunities from entity patterns."""
        return PatternAnalyzer.detect_by_keywords(
            entities,
            keyword_sets=[
                (
                    ["debug", "fix", "error", "bug", "issue"],
                    "Error handling patterns from repeated bug fixes",
                ),
                (["api", "integration", "connect", "sync"], "API integration best practices"),
            ],
            text_extractor=_extract_lowercase_title,
            min_matches=2,
        )

    def _identify_knowledge_gaps(self, entities: list) -> list[str]:
        """Identify knowledge gaps from entity patterns."""
        return PatternAnalyzer.detect_by_indicator_tuples(
            entities,
            indicators=[
                ("test", "Testing strategies"),
                ("performance", "Performance optimization"),
                ("security", "Security best practices"),
                ("deploy", "Deployment automation"),
            ],
            text_extractor=_extract_lowercase_title,
            min_matches=2,
        )

    def _generate_documentation_suggestions(self, patterns: list[dict]) -> list[str]:
        """Generate documentation suggestions from patterns."""
        return [
            f"Document {pattern['name']} workflow and best practices" for pattern in patterns[:5]
        ]

    async def _get_skill_vocabulary(self) -> list[str]:
        """Derive skill vocabulary from Ku titles/tags in the graph."""
        if not self.graph_intel:
            return []
        results = await self.graph_intel.backend.get_ku_titles_and_tags()
        if results.is_error:
            return []

        keywords: set[str] = set()
        for record in results.value:
            title = record.get("title", "")
            if title:
                # Use individual words >= 4 chars from Ku titles
                for word in title.lower().split():
                    if len(word) >= 4:
                        keywords.add(word)
            tags = record.get("tags")
            if tags:
                tag_list = tags if isinstance(tags, list) else [tags]
                for tag in tag_list:
                    if isinstance(tag, str) and len(tag) >= 3:
                        keywords.add(tag.lower())
        return list(keywords)

    async def _identify_skill_opportunities(self, entities: list) -> list[dict[str, Any]]:
        """Identify skill development opportunities from entity titles using graph-derived vocabulary."""
        skill_keywords = await self._get_skill_vocabulary()
        if not skill_keywords:
            return []
        return PatternAnalyzer.extract_skill_keywords(
            entities,
            text_extractor=_extract_lowercase_title,
            skill_keywords=skill_keywords,
        )

    def _determine_focus_areas(self, opportunities: list[dict]) -> list[str]:
        """Determine recommended focus areas."""
        focus_areas = []

        type_counts: dict[str, int] = {}
        for opp in opportunities:
            opp_type = opp.get("type", "general")
            type_counts[opp_type] = type_counts.get(opp_type, 0) + 1

        sorted_types = sorted(type_counts.items(), key=get_second_item, reverse=True)
        for opp_type, count in sorted_types[:3]:
            focus_areas.append(f"Focus on {opp_type.replace('_', ' ')} ({count} opportunities)")

        return focus_areas

    def _estimate_learning_impact(self, opportunities: list[dict]) -> dict[str, Any]:
        """Estimate impact of addressing learning opportunities."""
        return {
            "potential_time_savings": f"{len(opportunities) * 2} hours per week",
            "quality_improvement": "Estimated 20-40% improvement",
            "confidence_boost": "High" if len(opportunities) >= 5 else "Medium",
        }
