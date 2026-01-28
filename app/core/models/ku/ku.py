"""
Knowledge Domain Model (Tier 3 - Core)
======================================

Immutable domain model with business logic.
This is THE authoritative knowledge model - frozen and containing all business rules.

Phase 1-4 Integration (October 3, 2025):
- Phase 1: APOC query building for prerequisite/hierarchical queries
- Phase 2: Domain Intelligence models (ku_intelligence.py) for learning analytics
- Phase 3: GraphContext integration for relationship discovery
- Phase 4: Cross-domain relationship methods

Graph-Native Migration (October 6, 2025):
- Phase 3: Relationship fields removed - query via backend.get_related_*() methods
- Relationships stored ONLY as Neo4j edges, not model properties
- See: /docs/migrations/GRAPH_NATIVE_MIGRATION_PLAN.md Phase 3
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.constants import GraphDepth

# Phase 1: Query Infrastructure
from core.models.ku.ku_dto import KuDTO
from core.models.query import QueryIntent
from core.models.query.graph_traversal import build_graph_context_query
from core.models.shared_enums import Domain, LearningLevel, SELCategory, SystemConstants


@dataclass(frozen=True)
class Ku:
    """
    Immutable domain model representing a Knowledge Unit (KU).

    This model:
    - Is frozen (immutable) to ensure data integrity
    - Contains all business logic and rules
    - Represents the "truth" about knowledge in the system
    - Should be used for all business operations

    Naming Convention (October 9, 2025):
    - Class name 'Ku' matches module path 'core.models.ku' and UID prefix 'ku'
    - Follows same pattern as Task, Habit, Goal (module name = class name)

    SEL Integration (October 7, 2025):
    - Integrated with Social Emotional Learning (SEL) framework
    - Each KU is mapped to a primary SEL category
    - Supports adaptive learning paths via learning_level and relationships
    """

    # Core identity (required fields - no defaults)
    uid: str
    title: str
    content: str
    domain: Domain
    sel_category: SELCategory  # Primary SEL category for this knowledge unit

    # Optional fields (with defaults)
    summary: str = ""  # Brief description (auto-generated or user-provided)
    learning_level: LearningLevel = LearningLevel.BEGINNER  # Target learning level

    # Semantic analysis results (immutable after creation)
    quality_score: float = 0.0
    complexity: str = "medium"
    semantic_links: tuple[str, ...] = ()

    # Metadata (immutable)
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    # Adaptive Learning Hints
    estimated_time_minutes: int = 15  # Estimated completion time
    difficulty_rating: float = 0.5  # 0.0-1.0, helps with personalized recommendations

    # =========================================================================
    # NEO4J GENAI PLUGIN INTEGRATION (January 2026)
    # Vector embeddings for semantic search and similarity matching
    # =========================================================================
    # Embedding fields for Neo4j GenAI plugin vector search
    # Generated automatically during ingestion using ai.text.embed()
    # Enables semantic similarity search via db.index.vector.queryNodes()
    embedding: tuple[float, ...] | None = None  # 1536-dimensional vector for semantic search
    embedding_model: str | None = None  # Model used (e.g., "text-embedding-3-small")
    embedding_updated_at: datetime | None = None  # type: ignore[assignment]  # When embedding was generated

    # =========================================================================
    # SUBSTANCE TRACKING (October 17, 2025)
    # "Applied knowledge, not pure theory" - Philosophical Foundation
    # =========================================================================
    # Substance metrics track how knowledge is applied in real life.
    # These fields are updated via event-driven architecture when:
    # - Tasks apply this knowledge (TaskKnowledgeApplied event)
    # - Events practice this knowledge (EventKnowledgePracticed event)
    # - Habits build on this knowledge (HabitKnowledgeBuilt event)
    # - Journal entries reflect on this knowledge (JournalKnowledgeReflected event)
    # - Choices are informed by this knowledge (ChoiceKnowledgeInformed event)

    # Raw substantiation counts (updated via events)
    times_applied_in_tasks: int = 0
    times_practiced_in_events: int = 0
    times_built_into_habits: int = 0
    journal_reflections_count: int = 0
    choices_informed_count: int = 0

    # Timestamps for decay calculation (spaced repetition)
    last_applied_date: datetime | None = None  # type: ignore[assignment]
    last_practiced_date: datetime | None = None  # type: ignore[assignment]
    last_built_into_habit_date: datetime | None = None  # type: ignore[assignment]
    last_reflected_date: datetime | None = None  # type: ignore[assignment]
    last_choice_informed_date: datetime | None = None  # type: ignore[assignment]

    # Substance cache (lazy calculation with 1-hour TTL)
    _cached_substance_score: float | None = None
    _substance_cache_timestamp: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # GRAPH-NATIVE RELATIONSHIPS (October 2025)
    # =========================================================================
    # Relationship data stored as Neo4j edges, not serialized fields.
    # This eliminates data duplication and ensures graph is source of truth.
    #
    # Curriculum relationships (KU ↔ KU):
    # GRAPH-NATIVE: prerequisite_uids removed - query via KuRelationships.fetch() or backend.get_prerequisites()
    # GRAPH-NATIVE: enables_uids removed - query via KuRelationships.fetch() or backend.get_enables()
    # GRAPH-NATIVE: related_uids removed - query via KuRelationships.fetch()
    # GRAPH-NATIVE: broader_uids removed - query via KuRelationships.fetch()
    # GRAPH-NATIVE: narrower_uids removed - query via KuRelationships.fetch()
    #
    # Curriculum relationships (KU ↔ LS/LP):
    # GRAPH-NATIVE: in_learning_steps_uids removed - query via ku_service.find_learning_steps_containing()
    # GRAPH-NATIVE: in_learning_paths_uids removed - query via ku_service.find_learning_paths_teaching()
    #
    # Cross-domain Activity applications (Phase 2 - January 2026):
    # GRAPH-NATIVE: applied_in_task_uids removed - query via ku_service.find_tasks_applying_knowledge()
    # GRAPH-NATIVE: required_by_goal_uids removed - query via ku_service.find_goals_requiring_knowledge()
    # GRAPH-NATIVE: practiced_in_event_uids removed - query via ku_service.find_events_applying_knowledge()
    # GRAPH-NATIVE: reinforced_by_habit_uids removed - query via ku_service.find_habits_reinforcing_knowledge()
    # GRAPH-NATIVE: informs_choice_uids removed - query via ku_service.find_choices_informed_by_knowledge()
    # GRAPH-NATIVE: grounds_principle_uids removed - query via ku_service.find_principles_embodying_knowledge()
    #
    # For bulk relationship fetching, use:
    #   KuRelationships.fetch(ku_uid, neo4j_adapter, user_uid)
    #   KuRelationships.fetch_via_unified(ku_uid, relationship_service)
    #
    # IMPORTANT: Substance tracking fields (times_applied_in_tasks, etc.) are NOT
    # GRAPH-NATIVE - they are stored as KU properties for spaced repetition calculations.
    # See "Substance Tracking Properties" section below.
    # =========================================================================

    def __post_init__(self) -> None:
        """Set defaults for datetime fields if not provided."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())

    # ==========================================================================
    # KNOWLEDGE CARRIER PROTOCOL IMPLEMENTATION
    # ==========================================================================
    # KU implements KnowledgeCarrier, SubstantiatedKnowledge, and CurriculumCarrier.
    # KU IS knowledge - it always returns full relevance and its own UID.

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        KU IS knowledge - always returns 1.0.

        Returns:
            1.0 (maximum relevance - KU is the primary knowledge container)
        """
        return 1.0

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this entity carries.

        KU IS knowledge - returns its own UID.

        Returns:
            tuple containing this KU's UID
        """
        return (self.uid,)

    # ==========================================================================
    # BUSINESS LOGIC METHODS
    # ==========================================================================

    def is_advanced(self) -> bool:
        """Check if this is advanced knowledge."""
        return self.complexity == "advanced"

    def is_basic(self) -> bool:
        """Check if this is basic knowledge."""
        return self.complexity == "basic"

    def requires_prerequisites(self) -> bool:
        """
        Determine if this knowledge requires prerequisites.

        Business rule: Advanced tech knowledge always requires prerequisites,
        even if none are explicitly defined yet.

        Phase 3: Returns True for advanced tech knowledge. Use backend.get_prerequisites()
        to get actual prerequisite count.
        """
        # Phase 3: Simplified - advanced tech always requires prerequisites
        return self.domain == Domain.TECH and self.is_advanced()

    def is_high_quality(self) -> bool:
        """Check if content meets quality threshold."""
        return self.quality_score >= SystemConstants.MIN_QUALITY_THRESHOLD

    def is_semantic_analyzed(self) -> bool:
        """Check if semantic analysis has been performed."""
        return self.quality_score > 0 and len(self.semantic_links) > 0

    def word_count(self) -> int:
        """Calculate word count of content."""
        return len(self.content.split())

    def estimated_reading_time(self) -> int:
        """
        Estimate reading time in minutes.

        Assumes average reading speed of 200 words per minute.
        """
        return max(1, self.word_count() // 200)

    def is_substantial(self) -> bool:
        """
        Check if content is substantial enough.

        Business rule: Content should have at least 100 words to be meaningful.
        """
        return self.word_count() >= 100

    def has_tag(self, tag: str) -> bool:
        """Check if knowledge has a specific tag."""
        return tag.lower() in [t.lower() for t in self.tags]

    def is_connected(self) -> bool:
        """
        Check if this knowledge is connected to others.

        GRAPH-NATIVE: Limited implementation using semantic links only.
        For complete relationship checking across all graph edges:

        # Check any relationship type
        has_rels = await backend.get_related_uids(uid, relationship_type, "both")

        # Or use specific relationship queries
        has_prereqs = await backend.get_related_uids(uid, "REQUIRES_KNOWLEDGE", "incoming")
        has_enables = await backend.get_related_uids(uid, "ENABLES_KNOWLEDGE", "outgoing")
        """
        return len(self.semantic_links) > 0

    def get_all_connections(self) -> set[str]:
        """
        Get all knowledge units connected to this one.

        GRAPH-NATIVE: Returns semantic links only (content-based connections).
        For comprehensive graph traversal including all relationship types:

        # Curriculum relationships (KU ↔ KU)
        prereqs = await backend.get_related_uids(uid, "REQUIRES_KNOWLEDGE", "both")
        enables = await backend.get_related_uids(uid, "ENABLES_KNOWLEDGE", "both")
        related = await backend.get_related_uids(uid, "RELATED_TO", "both")

        # Curriculum relationships (KU ↔ LS/LP)
        steps = await ku_service.find_learning_steps_containing(uid, user_uid)
        paths = await ku_service.find_learning_paths_teaching(uid, user_uid)

        # Activity Domain applications (Phase 2 - January 2026)
        tasks = await ku_service.find_tasks_applying_knowledge(uid, user_uid)
        goals = await ku_service.find_goals_requiring_knowledge(uid, user_uid)
        events = await ku_service.find_events_applying_knowledge(uid, user_uid)
        habits = await ku_service.find_habits_reinforcing_knowledge(uid, user_uid)
        choices = await ku_service.find_choices_informed_by_knowledge(uid, user_uid)
        principles = await ku_service.find_principles_embodying_knowledge(uid, user_uid)
        """
        return set(self.semantic_links)

    def matches_domain(self, domain: Domain) -> bool:
        """Check if knowledge matches a specific domain."""
        return self.domain == domain

    def is_foundational(self) -> bool:
        """
        Check if this is foundational knowledge.

        Foundational knowledge:
        - Is basic complexity
        - Has high quality score (trusted foundation)

        Phase 3: Simplified check. Use backend.get_prerequisites() and
        backend.get_enables() for complete foundational analysis.
        """
        return self.complexity == "basic" and self.is_high_quality()

    def is_terminal(self) -> bool:
        """
        Check if this is terminal knowledge.

        Terminal knowledge:
        - Is typically advanced

        Phase 3: Simplified check. Use backend.get_enables() to check
        if this knowledge enables other concepts.
        """
        return self.is_advanced()

    def complexity_score(self) -> int:
        """
        Get numeric complexity score.

        Returns:
            1 for basic, 2 for medium, 3 for advanced
        """
        mapping = {"basic": 1, "medium": 2, "advanced": 3}
        return mapping.get(self.complexity, 2)

    def is_recent(self, days: int = 7) -> bool:
        """Check if knowledge was created recently."""
        if not self.created_at:
            return False
        age = datetime.now() - self.created_at
        return age.days <= days

    def is_updated(self) -> bool:
        """Check if knowledge has been updated after creation."""
        if not self.created_at or not self.updated_at:
            return False
        return self.updated_at > self.created_at

    # ==========================================================================
    # CURRICULUM INTEGRATION (ku → ls → lp)
    # ==========================================================================
    # Phase 3 (October 6, 2025): Curriculum relationship methods REMOVED.
    # Curriculum relationships are stored ONLY as Neo4j graph edges.
    #
    # Use KuService methods instead:
    # - service.get_learning_steps_using_knowledge(uid)
    # - service.get_learning_paths_featuring_knowledge(uid)
    # - backend.get_related_uids(uid, "USED_IN_STEP", "incoming")
    # - backend.get_related_uids(uid, "FEATURED_IN_PATH", "incoming")
    #
    # Deprecated methods removed: is_curriculum_integrated(), is_in_learning_steps(),
    # is_in_learning_paths(), curriculum_reach(), get_curriculum_context()
    # ==========================================================================

    # ==========================================================================
    # FACTORY METHODS
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "Ku":
        """
        Create immutable Ku from mutable DTO.

        Converts mutable lists to immutable tuples.

        Phase 3: Relationship fields removed - only core fields converted.
        """

        from core.models.shared_enums import SELCategory

        return cls(
            uid=dto.uid,
            title=dto.title,
            content=dto.content,
            domain=dto.domain,
            sel_category=getattr(
                dto, "sel_category", SELCategory.SELF_MANAGEMENT
            ),  # Default for backward compat
            learning_level=getattr(dto, "learning_level", LearningLevel.BEGINNER),
            quality_score=dto.quality_score,
            complexity=dto.complexity,
            semantic_links=tuple(dto.semantic_links),
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            tags=tuple(dto.tags),
        )

    def to_dto(self) -> "KuDTO":
        """
        Convert to mutable DTO for data operations.

        Converts immutable tuples back to mutable lists.

        Phase 3: Relationship fields removed - only core fields converted.
        """

        return KuDTO(
            uid=self.uid,
            title=self.title,
            content=self.content,
            domain=self.domain,
            quality_score=self.quality_score,
            complexity=self.complexity,
            semantic_links=list(self.semantic_links),
            created_at=self.created_at,
            updated_at=self.updated_at,
            tags=list(self.tags),
        )

    def has_content(self) -> bool:
        """
        Check if this knowledge has associated content.

        Note: Content is stored separately in KnowledgeContent for efficiency.
        """
        # This would be checked via the service/repository layer
        # The Knowledge model itself doesn't store content
        return len(self.content) > 0

    def needs_chunking(self) -> bool:
        """
        Check if content needs chunking.

        All content should be chunked for RAG retrieval.
        """
        return self.has_content() and self.word_count() > 50

    def __str__(self) -> str:
        """String representation."""
        return f"Ku(uid={self.uid}, title='{self.title}', domain={self.domain.value})"

    def __repr__(self) -> str:
        """Developer representation."""
        return (
            f"Ku(uid='{self.uid}', title='{self.title}', "
            f"domain={self.domain}, complexity='{self.complexity}', "
            f"quality={self.quality_score:.2f})"
        )

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_prerequisite_query(self, depth: int = 3) -> str:
        """
        Build pure Cypher query for prerequisite chain.

        Uses infrastructure QueryIntent.PREREQUISITE for semantic
        understanding and pattern-based graph traversal.

        Args:
            depth: Maximum prerequisite depth to traverse

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PREREQUISITE, depth=depth
        )

    def build_enables_query(self, depth: int = 3) -> str:
        """
        Build pure Cypher query for what this knowledge enables.

        Finds all knowledge units that can be learned after mastering this one.

        Args:
            depth: Maximum depth to traverse enables relationships

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid,
            intent=QueryIntent.HIERARCHICAL,  # Follow hierarchical structure
            depth=depth,
        )

    def build_related_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for related knowledge.

        Finds knowledge with similar topics or semantic relationships.

        Args:
            depth: Maximum depth for relationship traversal

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.RELATIONSHIP, depth=depth
        )

    def build_practice_query(self) -> str:
        """
        Build pure Cypher query for practice opportunities.

        Finds tasks, events, and exercises for practicing this knowledge.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PRACTICE, depth=GraphDepth.DIRECT
        )

    def get_suggested_query_intent(self) -> QueryIntent:
        """
        Get suggested QueryIntent based on knowledge characteristics.

        Business rules:
        - Foundational knowledge → HIERARCHICAL (explore what it enables)
        - Terminal knowledge → PREREQUISITE (understand requirements)
        - Connected knowledge → RELATIONSHIP (explore connections)
        - Basic knowledge → PRACTICE (find practice opportunities)

        Returns:
            Recommended QueryIntent for this knowledge
        """
        if self.is_foundational():
            return QueryIntent.HIERARCHICAL
        elif self.is_terminal():
            return QueryIntent.PREREQUISITE
        elif self.is_connected():
            return QueryIntent.RELATIONSHIP
        elif self.is_basic():
            return QueryIntent.PRACTICE
        else:
            return QueryIntent.EXPLORATORY

    # ==========================================================================
    # PHASE 2: GRAPHENTITY PROTOCOL IMPLEMENTATION
    # ==========================================================================

    def explain_existence(self) -> str:
        """
        WHY does this knowledge unit exist? One-sentence reasoning.

        Returns:
            Human-readable explanation of knowledge unit's purpose and context

        Phase 3: Simplified - relationship counts removed. Use service methods
        for full explanation with graph relationship context.
        """
        parts = [self.title]

        # Domain and complexity context
        parts.append(f"{self.domain.value} knowledge at {self.complexity} level")

        # Knowledge graph position
        if self.is_foundational():
            parts.append("Foundational knowledge")
        elif self.is_terminal():
            parts.append("Advanced knowledge")

        # Application context
        if self.is_substantial():
            parts.append(f"{self.word_count()} words, ~{self.estimated_reading_time()} min read")

        # Quality indicator
        if self.is_high_quality():
            parts.append(f"Quality score: {self.quality_score:.1f}")

        return ". ".join(parts)

    def get_upstream_influences(self) -> list[dict[str, Any]]:
        """
        WHAT shaped this knowledge unit? Entities that influenced its creation.

        Returns:
            List of dicts representing upstream influences:
            - Semantic links (discovered relationships)
            - Domain context

        Phase 3: Simplified - relationship fields removed.
        Use KuService.get_upstream_influences(uid) for complete graph analysis.
        """
        # 1. Semantic links (discovered relationships)
        influences = [
            {
                "uid": semantic_uid,
                "entity_type": "knowledge",
                "relationship_type": "semantically_linked",
                "reasoning": "Semantically related through content analysis",
                "strength": 0.6,
            }
            for semantic_uid in self.semantic_links
        ]

        # 2. Domain context (implicit influence)
        influences.append(
            {
                "uid": f"domain:{self.domain.value}",
                "entity_type": "domain",
                "relationship_type": "categorized_by",
                "reasoning": f"Knowledge belongs to {self.domain.value} domain",
                "strength": 1.0,
            }
        )

        return influences

    def get_downstream_impacts(self) -> list[dict[str, Any]]:
        """
        WHAT does this knowledge shape? Entities influenced by this knowledge.

        Returns:
            List of dicts representing downstream impacts (placeholder)

        Phase 3: Simplified - returns application pattern only.
        Use KuService.get_downstream_impacts(uid) for complete graph analysis.
        """
        impacts = []

        # Note: Tasks and Events that apply/practice this knowledge
        # These are tracked in Task/Event models via their knowledge_uid fields
        impacts.append(
            {
                "uid": f"applications:{self.uid}",
                "entity_type": "application_pattern",
                "relationship_type": "applied_in",
                "reasoning": "Tasks and events apply/practice this knowledge (query via graph)",
                "strength": 0.8,
                "note": "Use KuService.get_downstream_impacts() for complete impact analysis",
            }
        )

        return impacts

    def get_relationship_summary(self) -> dict[str, Any]:
        """
        Get comprehensive relationship context for this knowledge unit.

        Returns:
            Dict containing:
            - explanation: Why this knowledge exists
            - upstream: What shaped it (simplified)
            - downstream: What it shapes (simplified)
            - knowledge_metrics: Quality, complexity, content metrics

        Phase 3: Simplified summary - relationship counts removed.
        Use KuService.get_relationship_summary(uid) for complete graph analysis.
        """
        return {
            "explanation": self.explain_existence(),
            "upstream": self.get_upstream_influences(),
            "downstream": self.get_downstream_impacts(),
            "upstream_count": len(self.get_upstream_influences()),
            "downstream_count": len(self.get_downstream_impacts()),
            "knowledge_metrics": {
                "domain": self.domain.value,
                "complexity": self.complexity,
                "quality_score": self.quality_score,
                "word_count": self.word_count(),
                "reading_time_minutes": self.estimated_reading_time(),
                "is_foundational": self.is_foundational(),
                "is_terminal": self.is_terminal(),
                "is_connected": self.is_connected(),
                "semantic_links_count": len(self.semantic_links),
                "tags": list(self.tags),
            },
            "note": "Phase 3: Use KuService.get_relationship_summary() for complete graph data",
        }

    # ==========================================================================
    # SEL FRAMEWORK INTEGRATION (October 7, 2025)
    # ==========================================================================

    def is_beginner_level(self) -> bool:
        """Check if this KU is for beginners"""
        return self.learning_level == LearningLevel.BEGINNER

    def is_intermediate_level(self) -> bool:
        """Check if this KU is for intermediate learners"""
        return self.learning_level == LearningLevel.INTERMEDIATE

    def is_advanced_level(self) -> bool:
        """Check if this KU is for advanced learners"""
        return self.learning_level == LearningLevel.ADVANCED

    def is_expert_level(self) -> bool:
        """Check if this KU is for experts"""
        return self.learning_level == LearningLevel.EXPERT

    def is_appropriate_for_level(self, user_level: LearningLevel) -> bool:
        """
        Check if this KU is appropriate for a user's learning level.

        Business rules:
        - Beginners should only see BEGINNER content
        - Intermediate can see BEGINNER and INTERMEDIATE
        - Advanced can see up to ADVANCED
        - Experts can see all levels
        """
        level_hierarchy = {
            LearningLevel.BEGINNER: [LearningLevel.BEGINNER],
            LearningLevel.INTERMEDIATE: [LearningLevel.BEGINNER, LearningLevel.INTERMEDIATE],
            LearningLevel.ADVANCED: [
                LearningLevel.BEGINNER,
                LearningLevel.INTERMEDIATE,
                LearningLevel.ADVANCED,
            ],
            LearningLevel.EXPERT: [
                LearningLevel.BEGINNER,
                LearningLevel.INTERMEDIATE,
                LearningLevel.ADVANCED,
                LearningLevel.EXPERT,
            ],
        }
        return self.learning_level in level_hierarchy.get(user_level, [])

    def is_quick_win(self) -> bool:
        """
        Check if this is a 'quick win' KU.

        Quick wins are:
        - Short duration (≤ 10 minutes)
        - Low difficulty (≤ 0.4)
        - Great for motivation and momentum
        """
        return self.estimated_time_minutes <= 10 and self.difficulty_rating <= 0.4

    def is_challenging(self) -> bool:
        """Check if this KU is challenging (high difficulty)"""
        return self.difficulty_rating >= 0.7

    def matches_time_available(self, minutes_available: int) -> bool:
        """Check if user has enough time for this KU"""
        return self.estimated_time_minutes <= minutes_available

    def get_sel_context(self) -> dict[str, Any]:
        """
        Get SEL-specific context for this knowledge unit.

        Returns comprehensive SEL metadata for adaptive curriculum delivery.
        """
        return {
            "sel_category": self.sel_category.value,
            "sel_category_icon": self.sel_category.get_icon(),
            "sel_category_color": self.sel_category.get_color(),
            "sel_category_description": self.sel_category.get_description(),
            "learning_level": self.learning_level.value,
            "estimated_time_minutes": self.estimated_time_minutes,
            "difficulty_rating": self.difficulty_rating,
            "is_beginner_friendly": self.is_beginner_level(),
            "is_quick_win": self.is_quick_win(),
            "is_challenging": self.is_challenging(),
        }

    # ==========================================================================
    # SUBSTANCE TRACKING METHODS (October 17, 2025)
    # "Applied knowledge, not pure theory" - Track real-world application
    # ==========================================================================

    def substance_score(self, force_recalculate: bool = False) -> float:
        """
        Calculate substance score with time decay (spaced repetition).

        Substance measures how well knowledge is applied in real life:
        - Pure theory = 0.0
        - Well-practiced, lifestyle-integrated = 1.0

        Weighting Strategy:
        - Habits (0.10 per habit, max 0.30): Lifestyle integration
        - Journals (0.07 per entry, max 0.20): Active metacognition
        - Events (0.05 per event, max 0.25): Dedicated practice
        - Tasks (0.05 per task, max 0.25): Practical application
        - Choices (0.07 per choice, max 0.15): Decision-making

        Time Decay (Spaced Repetition):
        - Exponential decay with 30-day half-life
        - Encourages regular review and practice
        - Floor at 0.2 (knowledge never fully disappears)

        Args:
            force_recalculate: Skip cache, always recalculate

        Returns:
            Substance score from 0.0 to 1.0
        """
        # Use cache if fresh (< 1 hour old)
        if (
            not force_recalculate
            and self._cached_substance_score is not None
            and self._substance_cache_timestamp
        ):
            cache_age = datetime.now() - self._substance_cache_timestamp
            if cache_age.total_seconds() < 3600:  # 1 hour TTL
                return self._cached_substance_score

        # Recalculate with decay
        return self._calculate_substance_with_decay()

    def _calculate_substance_with_decay(self) -> float:
        """
        Internal calculation with time-based decay.

        Uses exponential decay formula: weight = e^(-days / half_life)
        where half_life = 30 days
        """
        now = datetime.now()
        half_life_days = 30.0
        score = 0.0

        # Habits (highest weight - lifestyle integration)
        if self.times_built_into_habits > 0:
            habit_weight = self._decay_weight(self.last_built_into_habit_date, now, half_life_days)
            score += min(0.30, self.times_built_into_habits * 0.10 * habit_weight)

        # Journals (high weight - metacognition)
        if self.journal_reflections_count > 0:
            journal_weight = self._decay_weight(self.last_reflected_date, now, half_life_days)
            score += min(0.20, self.journal_reflections_count * 0.07 * journal_weight)

        # Events (medium weight - dedicated practice)
        if self.times_practiced_in_events > 0:
            event_weight = self._decay_weight(self.last_practiced_date, now, half_life_days)
            score += min(0.25, self.times_practiced_in_events * 0.05 * event_weight)

        # Tasks (medium weight - project application)
        if self.times_applied_in_tasks > 0:
            task_weight = self._decay_weight(self.last_applied_date, now, half_life_days)
            score += min(0.25, self.times_applied_in_tasks * 0.05 * task_weight)

        # Choices (high weight - informed decision-making)
        if self.choices_informed_count > 0:
            choice_weight = self._decay_weight(self.last_choice_informed_date, now, half_life_days)
            score += min(0.15, self.choices_informed_count * 0.07 * choice_weight)

        return min(1.0, score)

    def _decay_weight(
        self, last_use_date: datetime | None, now: datetime, half_life_days: float
    ) -> float:
        """
        Calculate exponential decay weight for spaced repetition.

        Args:
            last_use_date: When knowledge was last used
            now: Current datetime
            half_life_days: Number of days for knowledge to decay to half strength

        Returns:
            Decay weight from 0.2 (old, needs review) to 1.0 (recent use)
        """
        if not last_use_date:
            return 0.2  # Never used = minimal weight

        days_since_use = (now - last_use_date).days

        # Exponential decay: weight = e^(-days / half_life)
        from math import exp

        decay = exp(-days_since_use / half_life_days)

        # Floor at 0.2 (knowledge never fully disappears)
        return max(0.2, decay)

    def is_theoretical_only(self) -> bool:
        """
        Check if knowledge lacks practical application.

        Returns True if substance score < 0.2 (less than 20% applied)
        """
        return self.substance_score() < 0.2

    def is_well_practiced(self) -> bool:
        """
        Check if knowledge is deeply embedded in user's life.

        Returns True if substance score >= 0.7 (70%+ applied)
        """
        return self.substance_score() >= 0.7

    def needs_more_practice(self) -> bool:
        """
        Check if knowledge needs more application.

        Business rules:
        - Fewer than 3 task applications
        - Fewer than 2 event practices
        - Not built into any habits
        """
        return (
            self.times_applied_in_tasks < 3
            or self.times_practiced_in_events < 2
            or self.times_built_into_habits == 0
        )

    def get_substantiation_gaps(self) -> list[str]:
        """
        Identify missing substantiation types.

        Returns:
            List of gap descriptions for UI recommendations
        """
        gaps = []

        if self.times_applied_in_tasks == 0:
            gaps.append("No tasks apply this knowledge")

        if self.times_practiced_in_events == 0:
            gaps.append("No events practice this knowledge")

        if self.times_built_into_habits == 0:
            gaps.append("Not built into any habits")

        if self.journal_reflections_count == 0:
            gaps.append("No journal reflections")

        if self.choices_informed_count == 0:
            gaps.append("Has not informed any choices/decisions")

        return gaps

    def needs_review(self) -> bool:
        """
        Check if knowledge needs review (spaced repetition).

        Returns True if:
        - Was once well-substantiated
        - Has decayed below 0.5 threshold
        """
        return self.substance_score() < 0.5 and self._was_once_substantiated()

    def _was_once_substantiated(self) -> bool:
        """Check if knowledge was ever well-practiced."""
        return (
            self.times_applied_in_tasks > 2
            or self.times_practiced_in_events > 1
            or self.times_built_into_habits > 0
        )

    def days_until_review_needed(self) -> int | None:
        """
        Predict when this knowledge will need review (spaced repetition).

        Returns:
            Days until substance drops below 0.5 threshold,
            or None if knowledge was never substantiated
        """
        if not self._was_once_substantiated():
            return None

        current_score = self.substance_score(force_recalculate=True)
        if current_score < 0.5:
            return 0  # Needs review now!

        # Find most recent activity date
        activity_dates = [
            d
            for d in [
                self.last_applied_date,
                self.last_practiced_date,
                self.last_built_into_habit_date,
                self.last_reflected_date,
                self.last_choice_informed_date,
            ]
            if d is not None
        ]

        if not activity_dates:
            return 0  # No activity dates = needs review

        most_recent_date = max(activity_dates)

        # Solve: 0.5 = e^(-days / 30)
        # days = -30 * ln(0.5) ≈ 20.8 days
        from math import log

        half_life_days = 30
        threshold_days = -half_life_days * log(0.5)  # ~21 days

        days_since_use = (datetime.now() - most_recent_date).days
        days_remaining = int(threshold_days - days_since_use)

        return max(0, days_remaining)

    def get_substantiation_summary(self) -> dict[str, Any]:
        """
        Get comprehensive substantiation summary for UI display.

        Returns:
            Dictionary with:
            - substance_score: Overall 0.0-1.0 score
            - breakdown: Counts for each substantiation type
            - progress_bars: Progress toward max caps
            - gaps: Missing substantiation types
            - review_status: Spaced repetition info
            - recommendations: Actionable next steps
        """
        score = self.substance_score()
        gaps = self.get_substantiation_gaps()

        # Calculate progress bars (toward max caps)
        task_progress = min(1.0, (self.times_applied_in_tasks * 0.05) / 0.25)
        event_progress = min(1.0, (self.times_practiced_in_events * 0.05) / 0.25)
        habit_progress = min(1.0, (self.times_built_into_habits * 0.10) / 0.30)
        journal_progress = min(1.0, (self.journal_reflections_count * 0.07) / 0.20)
        choice_progress = min(1.0, (self.choices_informed_count * 0.07) / 0.15)

        # Generate recommendations
        recommendations = []
        if "No tasks apply this knowledge" in gaps:
            recommendations.append(
                {
                    "type": "task",
                    "message": f"Create a task that applies: {self.title}",
                    "impact": "+0.05 substance per task (max +0.25)",
                }
            )

        if "Not built into any habits" in gaps:
            recommendations.append(
                {
                    "type": "habit",
                    "message": f"Build a habit around: {self.title}",
                    "impact": "+0.10 substance per habit (max +0.30)",
                }
            )

        if "No journal reflections" in gaps:
            recommendations.append(
                {
                    "type": "journal",
                    "message": f"Reflect on your experience with: {self.title}",
                    "impact": "+0.07 substance per reflection (max +0.20)",
                }
            )

        # Determine status message
        if score >= 0.8:
            status = "Mastered! Consider teaching others."
        elif score >= 0.7:
            status = "Well practiced! Keep it up."
        elif score >= 0.5:
            status = "Solid foundation. Practice more to deepen mastery."
        elif score >= 0.3:
            status = "Applied but not yet integrated. Build habits."
        elif score > 0:
            status = "Theoretical knowledge. Apply in projects."
        else:
            status = "Pure theory. Create tasks and practice."

        return {
            "substance_score": round(score, 2),
            "breakdown": {
                "tasks": {
                    "count": self.times_applied_in_tasks,
                    "progress": round(task_progress, 2),
                    "max_score": 0.25,
                },
                "events": {
                    "count": self.times_practiced_in_events,
                    "progress": round(event_progress, 2),
                    "max_score": 0.25,
                },
                "habits": {
                    "count": self.times_built_into_habits,
                    "progress": round(habit_progress, 2),
                    "max_score": 0.30,
                },
                "journals": {
                    "count": self.journal_reflections_count,
                    "progress": round(journal_progress, 2),
                    "max_score": 0.20,
                },
                "choices": {
                    "count": self.choices_informed_count,
                    "progress": round(choice_progress, 2),
                    "max_score": 0.15,
                },
            },
            "gaps": gaps,
            "review_status": {
                "needs_review": self.needs_review(),
                "days_until_review": self.days_until_review_needed(),
            },
            "recommendations": recommendations,
            "status_message": status,
            "is_theoretical_only": self.is_theoretical_only(),
            "is_well_practiced": self.is_well_practiced(),
        }
