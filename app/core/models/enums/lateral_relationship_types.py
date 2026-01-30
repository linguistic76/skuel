"""
Lateral Relationship Types - Core Graph Modeling
=================================================

Defines explicit lateral relationships between entities at the same or related
hierarchical levels (siblings, cousins, etc.).

This is FUNDAMENTAL to SKUEL's graph model - not a feature add-on.

Relationship Categories:
1. Structural - Derived from hierarchy but made explicit for performance
2. Semantic - Domain meaning beyond tree position
3. Dependency - Ordering and blocking constraints
4. Associative - Recommendations and alternatives

Philosophy:
    "The graph is the model. Lateral relationships are as fundamental as
    hierarchical ones. They capture the rich semantics of how entities relate
    beyond parent-child structure."

See: /docs/architecture/LATERAL_RELATIONSHIPS_CORE.md
"""

from enum import Enum


class LateralRelationType(str, Enum):
    """
    Lateral relationship types for graph-native modeling.

    These relationships exist BETWEEN entities at similar hierarchical levels,
    complementing the parent-child (SUBGOAL, SUBHABIT, etc.) relationships.
    """

    # ==========================================================================
    # STRUCTURAL RELATIONSHIPS - Position in hierarchy
    # ==========================================================================

    SIBLING = "SIBLING"
    """
    Same parent, same hierarchical depth.

    Example: Two goals under "Career Development"
    Properties: order_relationship ("before", "after", "none")
    Bidirectional: Yes (symmetric)
    """

    COUSIN = "COUSIN"
    """
    Same depth, different parents, shared grandparent.

    Example: Two habits under different morning routine subcategories
    Properties: shared_ancestor_uid, degree (1st cousin, 2nd cousin)
    Bidirectional: Yes (symmetric)
    """

    AUNT_UNCLE = "AUNT_UNCLE"
    """
    Parent's sibling (one level up, different branch).

    Example: A task's parent's sibling task
    Properties: through_parent_uid
    Bidirectional: Has inverse (NIECE_NEPHEW)
    """

    NIECE_NEPHEW = "NIECE_NEPHEW"
    """
    Inverse of AUNT_UNCLE (one level down, different branch).

    Properties: through_parent_uid
    Bidirectional: Has inverse (AUNT_UNCLE)
    """

    # ==========================================================================
    # DEPENDENCY RELATIONSHIPS - Ordering and constraints
    # ==========================================================================

    BLOCKS = "BLOCKS"
    """
    Must complete source before target (hard dependency).

    Example: "Learn Basics" blocks "Advanced Topics"
    Properties: reason, severity ("required", "recommended", "suggested")
    Bidirectional: Has inverse (BLOCKED_BY)
    Validation: Typically between siblings or across branches
    """

    BLOCKED_BY = "BLOCKED_BY"
    """
    Inverse of BLOCKS (target cannot start until source completes).

    Properties: reason, severity
    Bidirectional: Has inverse (BLOCKS)
    """

    PREREQUISITE_FOR = "PREREQUISITE_FOR"
    """
    Source is prerequisite for target (similar to BLOCKS but softer).

    Example: Knowledge unit A is prereq for KU B
    Properties: strength (0.0-1.0), topic_area
    Bidirectional: Has inverse (REQUIRES_PREREQUISITE)
    """

    REQUIRES_PREREQUISITE = "REQUIRES_PREREQUISITE"
    """
    Inverse of PREREQUISITE_FOR (target requires source first).

    Properties: strength, topic_area
    Bidirectional: Has inverse (PREREQUISITE_FOR)
    """

    ENABLES = "ENABLES"
    """
    Completing source unlocks/enables target.

    Example: Mastering Python Functions enables learning Decorators
    Properties: confidence (0.0-1.0), domain
    Bidirectional: Has inverse (ENABLED_BY)
    """

    ENABLED_BY = "ENABLED_BY"
    """
    Inverse of ENABLES (target is unlocked by source).

    Properties: confidence, domain
    Bidirectional: Has inverse (ENABLES)
    """

    # ==========================================================================
    # SEMANTIC RELATIONSHIPS - Domain meaning
    # ==========================================================================

    RELATED_TO = "RELATED_TO"
    """
    Semantic connection regardless of hierarchy.

    Example: Two principles that reinforce each other
    Properties: relationship_type, strength (0.0-1.0), description
    Bidirectional: Yes (symmetric)
    """

    SIMILAR_TO = "SIMILAR_TO"
    """
    High semantic similarity (content, topic, approach).

    Example: Two learning paths covering similar material
    Properties: similarity_score (0.0-1.0), basis (content, metadata, user_behavior)
    Bidirectional: Yes (symmetric)
    """

    COMPLEMENTARY_TO = "COMPLEMENTARY_TO"
    """
    Works well together, enhances each other.

    Example: Meditation habit complements Exercise habit
    Properties: synergy_score (0.0-1.0), evidence
    Bidirectional: Yes (symmetric)
    """

    CONFLICTS_WITH = "CONFLICTS_WITH"
    """
    Incompatible or contradictory.

    Example: Two choices that are mutually exclusive
    Properties: conflict_type, severity
    Bidirectional: Yes (symmetric)
    """

    # ==========================================================================
    # ASSOCIATIVE RELATIONSHIPS - Recommendations and alternatives
    # ==========================================================================

    ALTERNATIVE_TO = "ALTERNATIVE_TO"
    """
    Mutually exclusive options (choose one).

    Example: Two career path choices
    Properties: comparison_criteria, tradeoffs
    Bidirectional: Yes (symmetric)
    """

    RECOMMENDED_WITH = "RECOMMENDED_WITH"
    """
    Often done together (collaborative filtering).

    Example: Users who completed A also completed B
    Properties: confidence (0.0-1.0), evidence_count, basis
    Bidirectional: Yes (symmetric - if A→B then B→A)
    """

    STACKS_WITH = "STACKS_WITH"
    """
    Sequential combination (habit stacking, task chaining).

    Example: Meditate STACKS_WITH Exercise (do one after the other)
    Properties: trigger ("after", "before", "during"), strength
    Bidirectional: Has inverse (directional based on trigger)
    """

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def is_symmetric(self) -> bool:
        """Check if relationship is symmetric (bidirectional with same type)."""
        symmetric_types = {
            self.SIBLING,
            self.COUSIN,
            self.RELATED_TO,
            self.SIMILAR_TO,
            self.COMPLEMENTARY_TO,
            self.CONFLICTS_WITH,
            self.ALTERNATIVE_TO,
            self.RECOMMENDED_WITH,
        }
        return self in symmetric_types

    def get_inverse(self) -> "LateralRelationType | None":
        """Get the inverse relationship type if asymmetric."""
        inverses = {
            self.BLOCKS: self.BLOCKED_BY,
            self.BLOCKED_BY: self.BLOCKS,
            self.PREREQUISITE_FOR: self.REQUIRES_PREREQUISITE,
            self.REQUIRES_PREREQUISITE: self.PREREQUISITE_FOR,
            self.ENABLES: self.ENABLED_BY,
            self.ENABLED_BY: self.ENABLES,
            self.AUNT_UNCLE: self.NIECE_NEPHEW,
            self.NIECE_NEPHEW: self.AUNT_UNCLE,
        }
        return inverses.get(self)

    def requires_same_parent(self) -> bool:
        """Check if relationship requires entities to share same parent."""
        return self in {self.SIBLING, self.BLOCKS, self.STACKS_WITH}

    def requires_same_depth(self) -> bool:
        """Check if relationship requires entities at same hierarchical depth."""
        return self in {self.SIBLING, self.COUSIN, self.RELATED_TO, self.ALTERNATIVE_TO}

    def get_category(self) -> str:
        """Get relationship category for grouping/filtering."""
        if self in {self.SIBLING, self.COUSIN, self.AUNT_UNCLE, self.NIECE_NEPHEW}:
            return "structural"
        elif self in {
            self.BLOCKS,
            self.BLOCKED_BY,
            self.PREREQUISITE_FOR,
            self.REQUIRES_PREREQUISITE,
            self.ENABLES,
            self.ENABLED_BY,
        }:
            return "dependency"
        elif self in {
            self.RELATED_TO,
            self.SIMILAR_TO,
            self.COMPLEMENTARY_TO,
            self.CONFLICTS_WITH,
        }:
            return "semantic"
        else:  # ALTERNATIVE_TO, RECOMMENDED_WITH, STACKS_WITH
            return "associative"

    @classmethod
    def get_by_category(cls, category: str) -> list["LateralRelationType"]:
        """Get all relationship types in a category."""
        return [rel for rel in cls if rel.get_category() == category]

    def __str__(self) -> str:
        """Human-readable representation."""
        return self.value


# Export for convenience
__all__ = ["LateralRelationType"]
