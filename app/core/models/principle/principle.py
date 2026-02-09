"""
Principle Domain Model (Tier 3 - Core)
=======================================

Immutable domain model with business logic for principles.
Principles are fundamental values that guide learning, goals, and habits.
They provide the 'why' behind all actions and decisions.

Phase 1-4 Integration (October 3, 2025):
- Phase 1: APOC query building for manifestations and knowledge foundation
- Phase 3: GraphContext for cross-domain principle intelligence
- Phase 4: QueryIntent selection for principle-specific patterns
"""

__version__ = "2.1"  # Updated for Phase 1-4 integration


from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth
from core.models.query import QueryIntent

# Phase 1: Query Infrastructure
from core.models.query.graph_traversal import build_graph_context_query
from core.models.enums import Priority

if TYPE_CHECKING:
    from .principle_dto import PrincipleDTO


class PrincipleCategory(str, Enum):
    """Categories of principles aligned with learning domains"""

    SPIRITUAL = "spiritual"  # Transcendent values
    ETHICAL = "ethical"  # Moral values
    RELATIONAL = "relational"  # Interpersonal values
    PERSONAL = "personal"  # Self-development
    PROFESSIONAL = "professional"  # Work values
    INTELLECTUAL = "intellectual"  # Knowledge values
    HEALTH = "health"  # Wellbeing values
    CREATIVE = "creative"  # Expression values


class PrincipleSource(str, Enum):
    """Where principles originate from"""

    PHILOSOPHICAL = "philosophical"  # Philosophy traditions
    RELIGIOUS = "religious"  # Religious teachings
    CULTURAL = "cultural"  # Cultural heritage
    PERSONAL = "personal"  # Personal experience
    SCIENTIFIC = "scientific"  # Evidence-based
    MENTOR = "mentor"  # From teachers
    LITERATURE = "literature"  # Books and texts


class PrincipleStrength(str, Enum):
    """How strongly held a principle is"""

    CORE = "core"  # Non-negotiable, identity-defining
    STRONG = "strong"  # Very important
    MODERATE = "moderate"  # Important but flexible
    DEVELOPING = "developing"  # Newly adopted
    EXPLORING = "exploring"  # Testing and learning


class AlignmentLevel(str, Enum):
    """How well actions align with principles"""

    ALIGNED = "aligned"
    MOSTLY_ALIGNED = "mostly_aligned"
    PARTIAL = "partial"
    MISALIGNED = "misaligned"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PrincipleExpression:
    """How a principle manifests in specific contexts"""

    context: str  # Where it applies (work, family, etc.)
    behavior: str  # How it's expressed
    example: str | None = None  # Concrete example


@dataclass(frozen=True)
class AlignmentAssessment:
    """Assessment of how well current actions align with principle"""

    assessed_date: date
    alignment_level: AlignmentLevel
    evidence: str  # What was observed
    reflection: str | None = None


@dataclass(frozen=True)
class Principle:
    """
    Immutable domain model representing a principle.

    Principles are the fundamental values that guide all learning,
    goal-setting, and habit formation. They provide the 'why' that
    motivates sustained behavior change and knowledge acquisition.
    """

    # Identity
    uid: str
    user_uid: str  # REQUIRED - principle ownership
    name: str  # Short name (e.g., "Continuous Learning")
    statement: str  # Full statement (e.g., "I commit to learning every day")
    description: str | None = None

    # Classification
    category: PrincipleCategory = PrincipleCategory.PERSONAL
    source: PrincipleSource = PrincipleSource.PERSONAL
    strength: PrincipleStrength = PrincipleStrength.MODERATE

    # Philosophical Context
    tradition: str | None = None  # e.g., "Stoicism", "Buddhism"
    original_source: str | None = None  # e.g., "Marcus Aurelius, Meditations"
    personal_interpretation: str | None = None

    # Learning Integration - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (principle)-[:GROUNDED_IN_KNOWLEDGE]->(ku)
    # Graph relationship: (principle)-[:GUIDES_GOAL]->(goal)
    # Graph relationship: (principle)-[:INSPIRES_HABIT]->(habit)
    # Graph relationship: (principle)-[:RELATED_TO]->(principle)

    # Expressions & Applications
    expressions: tuple[PrincipleExpression, ...] = ()
    key_behaviors: tuple[str, ...] = ()  # Observable behaviors
    decision_criteria: tuple[str, ...] = ()  # How it guides decisions

    # Alignment Tracking
    current_alignment: AlignmentLevel = AlignmentLevel.UNKNOWN
    alignment_history: tuple[AlignmentAssessment, ...] = ()
    last_review_date: date | None = None  # type: ignore[assignment]

    # Conflicts & Tensions
    potential_conflicts: tuple[str, ...] = ()  # Situations where it's challenged
    conflicting_principles: tuple[str, ...] = ()  # Other principles it might conflict with
    resolution_strategies: tuple[str, ...] = ()  # How to resolve conflicts

    # Personal Reflection
    why_important: str | None = None  # Personal significance
    origin_story: str | None = None  # How it was adopted
    evolution_notes: str | None = None  # How understanding has changed

    # Status
    is_active: bool = True
    priority: Priority = Priority.MEDIUM

    # Metadata
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    adopted_date: date | None = None  # type: ignore[assignment]
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = None  # type: ignore[assignment]  # Rich context storage (graph neighborhoods, etc.)

    def __post_init__(self) -> None:
        """Set defaults for datetime and metadata fields."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    # ==========================================================================
    # KNOWLEDGE CARRIER PROTOCOL IMPLEMENTATION
    # ==========================================================================
    # Principle implements KnowledgeCarrier and ActivityCarrier.
    # Principle is GROUNDED IN knowledge - foundational wisdom.

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        Principle relevance based on category and philosophical grounding.

        Returns:
            0.0-1.0 based on knowledge foundation
        """
        score = 0.0

        # Intellectual principles (knowledge-centric)
        if self.category == PrincipleCategory.INTELLECTUAL:
            score = 0.9

        # Core principles (deeply grounded)
        if self.strength == PrincipleStrength.CORE:
            score = max(score, 0.8)

        # Strong principles
        if self.strength == PrincipleStrength.STRONG:
            score = max(score, 0.6)

        # Has philosophical tradition
        if self.tradition:
            score = max(score, 0.7)

        # Has original source
        if self.original_source:
            score = max(score, 0.5)

        # Well-aligned principles (knowledge well-integrated)
        if self.current_alignment == AlignmentLevel.ALIGNED:
            score = max(score, 0.6)

        return score

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this principle is grounded in.

        Principle knowledge is stored as graph relationships.
        This is a GRAPH-NATIVE placeholder - actual data requires service layer.

        Use service.relationships.get_principle_knowledge(principle_uid) for real data.

        Returns:
            Empty tuple (placeholder - actual KU UIDs via graph query)
        """
        # GRAPH-NATIVE: Real implementation requires service layer query
        # Query: MATCH (principle)-[:GROUNDED_IN_KNOWLEDGE]->(ku) RETURN ku.uid
        return ()

    def learning_impact_score(self) -> float:
        """
        Calculate learning impact when this principle is practiced.

        Principles provide the foundational 'why' for knowledge application.

        Returns:
            Impact score 0.0-1.0
        """
        score = 0.0

        # Core principles have highest impact
        if self.strength == PrincipleStrength.CORE:
            score += 0.4
        elif self.strength == PrincipleStrength.STRONG:
            score += 0.3

        # Well-aligned principles
        if self.current_alignment == AlignmentLevel.ALIGNED:
            score += 0.2

        # Has expressions (knowledge manifested in behavior)
        if self.expressions:
            score += min(0.2, len(self.expressions) * 0.05)

        # Has key behaviors (actionable knowledge)
        if self.key_behaviors:
            score += min(0.2, len(self.key_behaviors) * 0.05)

        return min(1.0, score)

    # ==========================================================================
    # STATUS CHECKS
    # ==========================================================================

    def is_core_principle(self) -> bool:
        """Check if this is a core, non-negotiable principle."""
        return self.strength == PrincipleStrength.CORE

    def is_developing(self) -> bool:
        """Check if this principle is still being developed."""
        return self.strength in [PrincipleStrength.DEVELOPING, PrincipleStrength.EXPLORING]

    def needs_review(self, days_threshold: int = 90) -> bool:
        """Check if principle needs alignment review."""
        if not self.last_review_date:
            return True
        days_since = (date.today() - self.last_review_date).days
        return days_since > days_threshold

    # ==========================================================================
    # ALIGNMENT ANALYSIS
    # ==========================================================================

    def is_well_aligned(self) -> bool:
        """Check if current actions align well with this principle."""
        return self.current_alignment in [AlignmentLevel.ALIGNED, AlignmentLevel.MOSTLY_ALIGNED]

    def has_alignment_issues(self) -> bool:
        """Check if there are alignment problems."""
        return self.current_alignment in [AlignmentLevel.MISALIGNED, AlignmentLevel.PARTIAL]

    def get_alignment_trend(self) -> str | None:
        """
        Analyze alignment trend over time.
        Returns: "improving", "declining", "stable", or None
        """
        if len(self.alignment_history) < 2:
            return None

        recent = self.alignment_history[-3:]  # Last 3 assessments
        alignment_scores = {
            AlignmentLevel.ALIGNED: 4,
            AlignmentLevel.MOSTLY_ALIGNED: 3,
            AlignmentLevel.PARTIAL: 2,
            AlignmentLevel.MISALIGNED: 1,
            AlignmentLevel.UNKNOWN: 0,
        }

        scores = [alignment_scores[a.alignment_level] for a in recent]

        if scores[-1] > scores[0]:
            return "improving"
        elif scores[-1] < scores[0]:
            return "declining"
        else:
            return "stable"

    # ==========================================================================
    # LEARNING INTEGRATION (Motivate + Inspire)
    # ==========================================================================

    def supports_learning(self) -> bool:
        """
        Check if this principle directly supports learning.

        GRAPH-NATIVE: Full check requires service layer query for knowledge grounding.
        Use: backend.count_related(uid, "GROUNDED_IN_KNOWLEDGE", "outgoing") > 0

        Returns:
            Partial check from node properties only
        """
        return (
            self.category == PrincipleCategory.INTELLECTUAL
            or
            # NOTE: Knowledge domain support requires graph query
            # Service layer: count_related(uid, "GROUNDED_IN_KNOWLEDGE", "outgoing") > 0
            "learn" in self.name.lower()
            or "knowledge" in self.statement.lower()
        )

    def guides_goals(self) -> bool:
        """
        Check if this principle guides specific goals.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "GUIDES_GOAL", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def inspires_habits(self) -> bool:
        """
        Check if this principle inspires habits.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "INSPIRES_HABIT", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def is_integrated(self) -> bool:
        """
        Check if principle is well-integrated into life.

        GRAPH-NATIVE: Goals and habits require service layer queries.
        Service must enrich with relationship counts.
        """
        return len(self.expressions) > 0  # Partial check - missing goal and habit relationships

    # ==========================================================================
    # CHOICE INTEGRATION (Inspire via values-based decision making)
    # ==========================================================================

    def get_guided_goal_uids(self) -> tuple[str, ...]:
        """
        Get all goals guided by this principle.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.get_related_uids(uid, "GUIDES_GOAL", "outgoing")
        """
        return ()  # Placeholder - service queries backend.get_related_uids()

    def get_inspired_habit_uids(self) -> tuple[str, ...]:
        """
        Get all habits inspired by this principle.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.get_related_uids(uid, "INSPIRES_HABIT", "outgoing")
        """
        return ()  # Placeholder - service queries backend.get_related_uids()

    def get_decision_criteria(self) -> tuple[str, ...]:
        """Get criteria this principle provides for decision-making."""
        return self.decision_criteria

    def provides_decision_guidance(self) -> bool:
        """Check if principle provides guidance for choices."""
        return len(self.decision_criteria) > 0

    def is_value_based_principle(self) -> bool:
        """
        Check if principle is explicitly values-based.

        Values-based principles help guide choices by providing
        clear criteria for evaluating options.
        """
        return len(self.decision_criteria) > 0 and self.strength in [
            PrincipleStrength.CORE,
            PrincipleStrength.STRONG,
        ]

    def get_choice_guidance_summary(self) -> dict:
        """
        Get summary of how this principle guides choices.

        Returns:
            Dictionary with decision guidance information
        """
        return {
            "provides_decision_guidance": self.provides_decision_guidance(),
            "decision_criteria_count": len(self.decision_criteria),
            "decision_criteria": list(self.decision_criteria),
            "is_value_based": self.is_value_based_principle(),
            "strength": self.strength.value,
            "can_guide_choices": self.can_guide_inspirational_choices(),
            "guidance_confidence": self.calculate_guidance_confidence(),
        }

    def can_guide_inspirational_choices(self) -> bool:
        """
        Check if principle is strong enough to guide inspirational choices.

        Inspirational choices align with SKUEL's mission to inspire users
        by presenting possibilities guided by their core values.
        """
        return self.is_value_based_principle() and self.is_active and len(self.key_behaviors) > 0

    def calculate_guidance_confidence(self) -> float:
        """
        Calculate confidence in principle's ability to guide choices (0-1).

        Higher scores indicate stronger, more actionable principles
        with clear decision criteria.
        """
        score = 0.0

        # Strength provides foundation (40%)
        strength_weights = {
            PrincipleStrength.CORE: 0.4,
            PrincipleStrength.STRONG: 0.3,
            PrincipleStrength.MODERATE: 0.2,
            PrincipleStrength.DEVELOPING: 0.1,
            PrincipleStrength.EXPLORING: 0.05,
        }
        score += strength_weights.get(self.strength, 0.2)

        # Decision criteria provide actionable guidance (30%)
        if len(self.decision_criteria) > 0:
            score += min(0.3, len(self.decision_criteria) * 0.1)

        # Observable behaviors show manifestation (20%)
        if len(self.key_behaviors) > 0:
            score += min(0.2, len(self.key_behaviors) * 0.05)

        # Current alignment shows lived experience (10%)
        if self.is_well_aligned():
            score += 0.1

        return min(1.0, score)

    def suggest_choice_application_contexts(self) -> list[str]:
        """
        Suggest contexts where this principle could guide choices.

        Returns:
            List of suggested application contexts
        """
        suggestions = []

        # Use expressions as contexts
        suggestions.extend([f"{expr.context}: {expr.behavior}" for expr in self.expressions])

        # Use decision criteria as contexts
        suggestions.extend(
            [f"When choosing: Consider {criterion}" for criterion in self.decision_criteria]
        )

        # Category-based suggestions
        category_contexts = {
            PrincipleCategory.PROFESSIONAL: "Career path choices, project selection",
            PrincipleCategory.PERSONAL: "Life direction, personal growth decisions",
            PrincipleCategory.INTELLECTUAL: "Learning path selection, skill development",
            PrincipleCategory.HEALTH: "Lifestyle choices, habit formation",
            PrincipleCategory.RELATIONAL: "Social commitments, relationship decisions",
            PrincipleCategory.CREATIVE: "Creative projects, expression methods",
            PrincipleCategory.ETHICAL: "Moral decisions, value conflicts",
            PrincipleCategory.SPIRITUAL: "Purpose-driven choices, meaning-making",
        }

        if self.category in category_contexts:
            suggestions.append(category_contexts[self.category])

        return suggestions if suggestions else ["General life decisions"]

    # ==========================================================================
    # CONFLICT MANAGEMENT
    # ==========================================================================

    def has_conflicts(self) -> bool:
        """Check if this principle has known conflicts."""
        return len(self.potential_conflicts) > 0 or len(self.conflicting_principles) > 0

    def has_resolution_strategies(self) -> bool:
        """Check if conflict resolution strategies are defined."""
        return len(self.resolution_strategies) > 0

    # ==========================================================================
    # EXPRESSION & BEHAVIOR
    # ==========================================================================

    def get_expressions_for_context(self, context: str) -> list[PrincipleExpression]:
        """Get expressions for a specific context."""
        return [e for e in self.expressions if context.lower() in e.context.lower()]

    def has_concrete_behaviors(self) -> bool:
        """Check if principle has concrete behavioral expressions."""
        return len(self.key_behaviors) > 0 or len(self.expressions) > 0

    def is_actionable(self) -> bool:
        """Check if principle is actionable (has clear behaviors)."""
        return len(self.key_behaviors) > 0 and len(self.decision_criteria) > 0

    # ==========================================================================
    # STRENGTH & PRIORITY
    # ==========================================================================

    def get_influence_score(self) -> int:
        """
        Calculate influence score based on connections and strength.
        Higher score = more influential (0-10 scale).
        """
        score = 0

        # Strength contributes most
        strength_scores = {
            PrincipleStrength.CORE: 5,
            PrincipleStrength.STRONG: 4,
            PrincipleStrength.MODERATE: 3,
            PrincipleStrength.DEVELOPING: 2,
            PrincipleStrength.EXPLORING: 1,
        }
        score += strength_scores.get(self.strength, 3)

        # Integration adds to influence
        if self.guides_goals():
            score += 1
        if self.inspires_habits():
            score += 1
        if len(self.expressions) >= 3:
            score += 1

        # Alignment indicates active influence
        if self.is_well_aligned():
            score += 2

        return min(10, score)

    # ==========================================================================
    # EVOLUTION & GROWTH
    # ==========================================================================

    def has_evolved(self) -> bool:
        """Check if principle has evolution notes."""
        return self.evolution_notes is not None

    def has_origin_story(self) -> bool:
        """Check if principle has an origin story."""
        return self.origin_story is not None

    def days_since_adoption(self) -> int | None:
        """Calculate days since formal adoption."""
        if not self.adopted_date:
            return None
        return (date.today() - self.adopted_date).days

    # ==========================================================================
    # CONVERSIONS
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: "PrincipleDTO") -> "Principle":
        """Create immutable Principle from mutable DTO."""
        # Convert expression dicts to PrincipleExpression objects
        expressions = tuple(
            PrincipleExpression(**e) if isinstance(e, dict) else e for e in dto.expressions
        )

        # Convert assessment dicts to AlignmentAssessment objects
        # Parse alignment_level string to enum and assessed_date string to date if coming from serialized dict
        def parse_assessment(a: dict) -> AlignmentAssessment:
            a = dict(a)  # Make a copy to avoid mutating original
            if isinstance(a.get("alignment_level"), str):
                a["alignment_level"] = AlignmentLevel(a["alignment_level"])
            if isinstance(a.get("assessed_date"), str):
                # Handle both date ("2025-10-01") and datetime ("2025-10-01T00:00:00") ISO formats
                date_str = a["assessed_date"]
                if "T" in date_str:
                    a["assessed_date"] = datetime.fromisoformat(date_str).date()
                else:
                    a["assessed_date"] = date.fromisoformat(date_str)
            return AlignmentAssessment(**a)

        assessments = tuple(
            parse_assessment(a) if isinstance(a, dict) else a for a in dto.alignment_history
        )

        # GRAPH-NATIVE: UID list fields are NOT transferred from DTO to domain model.
        # Relationships exist only as Neo4j edges, queried via service layer.
        return cls(
            uid=dto.uid,
            user_uid=dto.user_uid,
            name=dto.name,
            statement=dto.statement,
            description=dto.description,
            category=dto.category,
            source=dto.source,
            strength=dto.strength,
            tradition=dto.tradition,
            original_source=dto.original_source,
            personal_interpretation=dto.personal_interpretation,
            # UID list fields REMOVED - relationships stored as graph edges only:
            # supported_knowledge_domains REMOVED - use (principle)-[:GROUNDED_IN_KNOWLEDGE]->(ku)
            # guided_goal_uids REMOVED - use (principle)-[:GUIDES_GOAL]->(goal)
            # inspired_habit_uids REMOVED - use (principle)-[:INSPIRES_HABIT]->(habit)
            # related_principle_uids REMOVED - use (principle)-[:RELATED_TO]->(principle)
            expressions=expressions,
            key_behaviors=tuple(dto.key_behaviors),
            decision_criteria=tuple(dto.decision_criteria),
            current_alignment=dto.current_alignment,
            alignment_history=assessments,
            last_review_date=dto.last_review_date,
            # Phase 2: Conflict tracking fields removed from DTO (conflicts are derived, not stored)
            potential_conflicts=(),  # Domain model retains these fields but they're empty from DTO
            conflicting_principles=(),
            resolution_strategies=(),
            why_important=dto.why_important,
            origin_story=dto.origin_story,
            evolution_notes=dto.evolution_notes,
            is_active=dto.is_active,
            priority=dto.priority,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            adopted_date=dto.adopted_date,
            tags=tuple(dto.tags),
            metadata=getattr(dto, "metadata", {})
            or {},  # Copy metadata from DTO (rich context storage)
        )

    def to_dto(self) -> "PrincipleDTO":
        """
        Convert to mutable DTO for updates.

        GRAPH-NATIVE: UID list fields set to empty lists.
        Service layer must populate from graph queries before API serialization.
        """
        from .principle_dto import PrincipleDTO

        # Convert expressions to dicts
        expression_dicts = [
            {"context": e.context, "behavior": e.behavior, "example": e.example}
            for e in self.expressions
        ]

        # Convert assessments to dicts
        assessment_dicts = [
            {
                "assessed_date": a.assessed_date,
                "alignment_level": a.alignment_level,
                "evidence": a.evidence,
                "reflection": a.reflection,
            }
            for a in self.alignment_history
        ]

        return PrincipleDTO(
            uid=self.uid,
            user_uid=self.user_uid,
            name=self.name,
            statement=self.statement,
            description=self.description,
            category=self.category,
            source=self.source,
            strength=self.strength,
            tradition=self.tradition,
            original_source=self.original_source,
            personal_interpretation=self.personal_interpretation,
            # Phase 2: Graph-native relationship fields removed from DTO
            # Query via PrinciplesRelationshipService instead:
            #   - get_principle_knowledge() for knowledge grounding
            #   - get_principle_goals() for guided goals
            #   - get_principle_habits() for inspired habits
            #   - get_related_principles() for related principles
            expressions=expression_dicts,
            key_behaviors=list(self.key_behaviors),
            decision_criteria=list(self.decision_criteria),
            current_alignment=self.current_alignment,
            alignment_history=assessment_dicts,
            last_review_date=self.last_review_date,
            # Phase 2: Conflict tracking fields removed from DTO (conflicts are domain logic, not DTO data)
            # These are derived fields computed in domain layer, not stored/transferred
            why_important=self.why_important,
            origin_story=self.origin_story,
            evolution_notes=self.evolution_notes,
            is_active=self.is_active,
            priority=self.priority,
            created_at=self.created_at,
            updated_at=self.updated_at,
            adopted_date=self.adopted_date,
            tags=list(self.tags),
            metadata=self.metadata,  # Copy metadata to DTO (rich context storage)
        )

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_manifestation_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for principle manifestations

        Finds goals, habits, tasks, and choices that embody this principle.

        Args:
            depth: Maximum manifestation depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.HIERARCHICAL, depth=depth
        )

    def build_related_principles_query(self) -> str:
        """
        Build pure Cypher query for related principles

        Finds principles with similar categories, sources, or traditions.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.RELATIONSHIP, depth=GraphDepth.NEIGHBORHOOD
        )

    def build_knowledge_foundation_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for knowledge foundation

        Finds knowledge that supports or explains this principle.

        Args:
            depth: Maximum knowledge graph depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PREREQUISITE, depth=depth
        )

    def build_alignment_assessment_query(self) -> str:
        """
        Build pure Cypher query for alignment assessment

        Finds recent activities to assess alignment with this principle.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.AGGREGATION, depth=GraphDepth.NEIGHBORHOOD
        )

    def get_suggested_query_intent(self) -> QueryIntent:
        """
        Get suggested QueryIntent based on principle characteristics.

        Business rules:
        - Core principles → PRINCIPLE_EMBODIMENT (how is it LIVED?)
        - Developing principles → EXPLORATORY (discover applications)
        - Philosophical principles → RELATIONSHIP (understand connections)
        - Practical principles → PRACTICE (find applications)
        - Default → PRINCIPLE_EMBODIMENT (embodiment analysis)

        Returns:
            Recommended QueryIntent for this principle
        """
        if self.strength == PrincipleStrength.CORE:
            # Core principles: use PRINCIPLE_EMBODIMENT to see full manifestation
            return QueryIntent.PRINCIPLE_EMBODIMENT

        if (
            self.strength == PrincipleStrength.DEVELOPING
            or self.strength == PrincipleStrength.EXPLORING
        ):
            return QueryIntent.EXPLORATORY

        if self.source == PrincipleSource.PHILOSOPHICAL or self.source == PrincipleSource.RELIGIOUS:
            return QueryIntent.RELATIONSHIP

        # Default: use PRINCIPLE_EMBODIMENT for embodiment analysis
        return QueryIntent.PRINCIPLE_EMBODIMENT

    # ==========================================================================
    # PHASE 2: GRAPHENTITY PROTOCOL IMPLEMENTATION
    # ==========================================================================

    def explain_existence(self) -> str:
        """
        WHY does this principle exist? One-sentence reasoning.

        Returns:
            Human-readable explanation of principle's purpose and context
        """
        parts = [self.statement]

        # Core context: category and strength
        parts.append(f"{self.category.value.title()} principle with {self.strength.value} strength")

        # Source and tradition if meaningful
        if self.source != PrincipleSource.PERSONAL:
            parts.append(f"from {self.source.value} tradition")
        if self.tradition:
            parts.append(f"({self.tradition})")

        # NOTE: Integration metrics require service layer queries
        # Service should add:
        # - "Guides N goal(s)" via count_related(uid, "GUIDES_GOAL", "outgoing")
        # - "Inspires N habit(s)" via count_related(uid, "INSPIRES_HABIT", "outgoing")

        # Alignment status
        if self.is_well_aligned():
            parts.append("Well-aligned in practice")
        elif self.current_alignment in [AlignmentLevel.MISALIGNED, AlignmentLevel.PARTIAL]:
            parts.append("Needs better integration")

        return ". ".join(parts)

    def get_upstream_influences(self) -> list[dict]:
        """
        WHAT shaped this principle? Entities that influenced its adoption.

        GRAPH-NATIVE: Knowledge and related principle UIDs require service layer queries.
        Service should enrich this list with graph relationship data.

        Returns:
            List of dicts representing upstream influences (partial - from node properties only)
        """
        influences = []

        # NOTE: Service layer should add:
        # 1. Knowledge foundations - via get_related_uids(uid, "GROUNDED_IN_KNOWLEDGE", "outgoing")
        # 2. Related principles - via get_related_uids(uid, "RELATED_TO", "outgoing")

        # 2. Source attribution (if external) - node property
        if self.original_source and self.source != PrincipleSource.PERSONAL:
            influences.append(
                {
                    "uid": f"source:{self.source.value}:{self.original_source}",
                    "entity_type": "source",
                    "relationship_type": "learned_from",
                    "reasoning": f"Principle derived from {self.source.value} source: {self.original_source}",
                    "strength": None,
                }
            )

        # 3. Origin story context (if exists) - node property
        if self.origin_story:
            influences.append(
                {
                    "uid": f"experience:{self.uid}:origin",
                    "entity_type": "experience",
                    "relationship_type": "inspired_by",
                    "reasoning": self.origin_story,
                    "strength": None,
                }
            )

        return influences

    def get_downstream_impacts(self) -> list[dict]:
        """
        WHAT does this principle shape? Entities guided by this principle.

        GRAPH-NATIVE: Goals and habits require service layer queries.
        Service should enrich this list with graph relationship data.

        Returns:
            List of dicts representing downstream impacts (partial - from node properties only)
        """
        impacts = []

        # NOTE: Service layer should add:
        # 1. Guided goals - via get_related_uids(uid, "GUIDES_GOAL", "outgoing")
        # 2. Inspired habits - via get_related_uids(uid, "INSPIRES_HABIT", "outgoing")

        # 3. Expressions (concrete manifestations)
        impacts.extend(
            [
                {
                    "uid": f"expression:{self.uid}:{idx}",
                    "entity_type": "expression",
                    "relationship_type": "manifests_as",
                    "reasoning": f"In {expression.context}: {expression.behavior}",
                    "strength": None,
                    "example": expression.example,
                }
                for idx, expression in enumerate(self.expressions)
            ]
        )

        # 4. Key behaviors (action patterns)
        impacts.extend(
            [
                {
                    "uid": f"behavior:{self.uid}:{idx}",
                    "entity_type": "behavior",
                    "relationship_type": "prescribes",
                    "reasoning": f"Principle prescribes behavior: {behavior}",
                    "strength": None,
                }
                for idx, behavior in enumerate(self.key_behaviors)
            ]
        )

        return impacts

    def get_relationship_summary(self) -> dict:
        """
        Get comprehensive relationship context for this principle.

        Returns:
            Dict containing:
            - explanation: Why this principle exists
            - upstream: What shaped it
            - downstream: What it shapes
            - upstream_count: Number of upstream influences
            - downstream_count: Number of downstream impacts
            - principle_metrics: Strength, alignment, influence
        """
        return {
            "explanation": self.explain_existence(),
            "upstream": self.get_upstream_influences(),
            "downstream": self.get_downstream_impacts(),
            "upstream_count": len(self.get_upstream_influences()),
            "downstream_count": len(self.get_downstream_impacts()),
            "principle_metrics": {
                "category": self.category.value,
                "source": self.source.value,
                "strength": self.strength.value,
                "current_alignment": self.current_alignment.value,
                "influence_score": self.get_influence_score(),
                "guides_goals": self.guides_goals(),
                "inspires_habits": self.inspires_habits(),
                "is_well_aligned": self.is_well_aligned(),
                "days_since_adoption": self.days_since_adoption(),
            },
        }


# ==========================================================================
# PRINCIPLE RELATIONSHIP MODELS
# ==========================================================================


@dataclass(frozen=True)
class PrincipleConflict:
    """
    Represents a conflict between principles.

    Conflicts arise when two principles suggest different actions
    in the same situation. This model helps track and resolve such tensions.
    """

    conflicting_principle_uid: str  # UID of the conflicting principle
    conflict_description: str  # Description of the conflict
    resolution_strategy: str  # How to resolve when both apply
    priority_in_conflict: int  # Which takes precedence (1 = this principle, 2 = other)

    # Context
    conflict_contexts: tuple[str, ...] = ()  # Situations where conflict arises,
    resolution_examples: tuple[str, ...] = ()  # Examples of successful resolution

    # Tracking
    identified_date: date | None = None  # type: ignore[assignment]
    last_encountered: date | None = None  # type: ignore[assignment]
    resolution_effectiveness: float = 0.5  # 0-1, how well strategy works

    def is_high_priority_conflict(self) -> bool:
        """Check if this principle takes priority in the conflict."""
        return self.priority_in_conflict == 1

    def needs_resolution_update(self) -> bool:
        """Check if resolution strategy needs updating."""
        return self.resolution_effectiveness < 0.7


@dataclass(frozen=True)
class PrincipleAlignment:
    """
    Represents alignment between a principle and a goal/habit.

    This is the key integration point for motivation tracking,
    showing how principles guide specific actions and outcomes.
    """

    principle_uid: str  # UID of the principle
    entity_uid: str  # UID of goal or habit
    entity_type: str  # "goal" or "habit"

    # Alignment assessment
    alignment_level: AlignmentLevel
    alignment_score: float  # 0-1 numeric score

    # Influence description
    influence_description: str  # How principle influences this entity
    influence_weight: float = 1.0  # Strength of influence (0-1)

    # Specific manifestations
    manifestations: tuple[str, ...] = ()  # How principle shows up
    supporting_behaviors: tuple[str, ...] = ()  # Specific behaviors

    # Gaps and tensions
    alignment_gaps: tuple[str, ...] = ()  # Where alignment is weak
    potential_improvements: tuple[str, ...] = ()  # How to strengthen

    # Tracking
    assessed_date: datetime = None  # type: ignore[assignment]
    assessor: str | None = None  # Who made the assessment

    def __post_init__(self) -> None:
        """Set default datetime."""
        if self.assessed_date is None:
            object.__setattr__(self, "assessed_date", datetime.now())

    def is_well_aligned(self) -> bool:
        """Check if alignment is strong."""
        return self.alignment_level in [AlignmentLevel.ALIGNED, AlignmentLevel.MOSTLY_ALIGNED]

    def has_gaps(self) -> bool:
        """Check if there are identified gaps."""
        return len(self.alignment_gaps) > 0

    def strengthen_alignment(self) -> list[str]:
        """
        Generate suggestions to strengthen alignment.

        Returns:
            List of actionable suggestions
        """
        suggestions = []

        # Based on alignment level
        if self.alignment_level == AlignmentLevel.PARTIAL:
            suggestions.extend(
                [
                    "Review and clarify how this supports your principle",
                    "Add specific practices that embody the principle",
                    "Consider adjusting approach to better reflect values",
                ]
            )
        elif self.alignment_level == AlignmentLevel.MOSTLY_ALIGNED:
            suggestions.extend(
                [
                    "Identify and address the remaining gaps",
                    "Make the principle more explicit in your approach",
                    "Strengthen the connecting behaviors",
                ]
            )
        elif self.alignment_level == AlignmentLevel.MISALIGNED:
            suggestions.extend(
                [
                    "Reconsider if this aligns with your values",
                    "Modify the approach to better reflect principles",
                    "Consider if this conflicts with core beliefs",
                ]
            )

        # Add specific improvements if identified
        suggestions.extend(self.potential_improvements)

        return suggestions[:5]  # Return top 5 suggestions


@dataclass(frozen=True)
class PrincipleDecision:
    """
    A decision evaluated through the lens of principles.

    This model captures principle-based decision making,
    helping track how values guide choices and outcomes.
    """

    decision_description: str  # What decision is being made
    options: tuple[str, ...]  # Available options

    # Principle evaluations
    principle_scores: dict[str, dict[str, float]]  # {option: {principle_uid: score}}

    # Recommendation
    recommended_option: str  # Best option based on principles
    recommendation_reason: str  # Why this option aligns best
    recommendation_confidence: float = 0.8  # 0-1 confidence in recommendation

    # Conflicts and tensions
    conflicts: tuple[PrincipleConflict, ...] = ()  # Identified conflicts,
    value_tensions: tuple[str, ...] = ()  # Competing values
    tradeoffs: tuple[str, ...] = ()  # What is sacrificed

    # Decision context
    context: str = ""  # Situation/background,
    importance: str = "medium"  # "high", "medium", "low"
    urgency: str = "normal"  # "urgent", "normal", "flexible"
    stakes: str = "moderate"  # "high", "moderate", "low"

    # Tracking
    timestamp: datetime = None  # type: ignore[assignment]
    decision_maker: str | None = None
    actual_choice: str | None = None  # What was actually chosen,
    outcome_assessment: str | None = None  # How it turned out

    def __post_init__(self) -> None:
        """Set default datetime."""
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    def get_principle_ranking(self) -> list[tuple[str, float]]:
        """
        Rank options by principle alignment.

        Returns:
            List of (option, average_score) tuples sorted by score
        """
        option_scores = []

        for option in self.options:
            if option in self.principle_scores:
                scores = list(self.principle_scores[option].values())
                avg_score = sum(scores) / len(scores) if scores else 0.0
            else:
                avg_score = 0.0
            option_scores.append((option, avg_score))

        return sorted(option_scores, key=itemgetter(1), reverse=True)

    def has_clear_winner(self, threshold: float = 0.2) -> bool:
        """
        Check if there's a clear best option.

        Args:
            threshold: Minimum gap between top options

        Returns:
            True if top option is clearly better
        """
        rankings = self.get_principle_ranking()
        if len(rankings) < 2:
            return True

        top_score = rankings[0][1]
        second_score = rankings[1][1]
        return (top_score - second_score) >= threshold

    def get_conflicting_principles(self) -> list[str]:
        """Get list of principles that conflict in this decision."""
        return [conflict.conflicting_principle_uid for conflict in self.conflicts]

    def was_recommendation_followed(self) -> bool | None:
        """Check if the recommendation was actually followed."""
        if not self.actual_choice:
            return None
        return self.actual_choice == self.recommended_option
