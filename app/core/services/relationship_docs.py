"""
Relationship Service Documentation Templates
=============================================

Centralized documentation strings for relationship services.
Eliminates ~30 lines of duplicated documentation per service.

Usage:
    from core.services.relationship_docs import (
        SEMANTIC_DOCS_TEMPLATE,
        format_semantic_docs,
    )

    class MyRelationshipService:
        '''
        {base_docs}

        {semantic_docs}
        '''

Version: 1.0.0
Date: November 28, 2025
"""

# Standard confidence scoring documentation
CONFIDENCE_SCORING_DOCS = """
Confidence Scoring:
- 0.9+: User explicitly defined relationship
- 0.7-0.9: Inferred from entity metadata
- 0.5-0.7: Suggested based on patterns
- <0.5: Low confidence, needs verification
"""

# Standard source tag documentation
SOURCE_TAG_DOCS_TEMPLATE = """
Source Tag: "{domain}_service_explicit"
- Format: "{domain}_service_explicit" for user-created relationships
- Format: "{domain}_service_inferred" for system-generated relationships
"""

# Standard semantic types documentation
SEMANTIC_TYPES_DOCS = """
Semantic Types Used:
- APPLIES_KNOWLEDGE: Entities apply knowledge units practically
- REQUIRES_KNOWLEDGE: Entities require prerequisite knowledge
"""

# SKUEL architecture documentation
SKUEL_ARCHITECTURE_DOCS = """
SKUEL Architecture:
- Uses CypherGenerator for ALL graph queries
- No APOC calls (Phase 5 eliminated those)
- Returns Result[T] for error handling
- Logs operations with structured logging
"""


def format_semantic_docs(domain: str, additional_semantic_types: str | None = None) -> str:
    """
    Format complete semantic documentation block for a domain.

    Args:
        domain: Domain name (e.g., "tasks", "goals", "habits")
        additional_semantic_types: Optional domain-specific semantic types

    Returns:
        Formatted documentation string

    Example:
        >>> docs = format_semantic_docs("tasks", "- DEPENDS_ON: Task dependencies")
        >>> print(docs)
        GRAPH-NATIVE DOCUMENTATION:
        ===========================
        ...
    """
    semantic_types = SEMANTIC_TYPES_DOCS
    if additional_semantic_types:
        semantic_types = semantic_types.rstrip() + f"\n{additional_semantic_types}"

    source_tag = SOURCE_TAG_DOCS_TEMPLATE.format(domain=domain)

    return f"""
GRAPH-NATIVE DOCUMENTATION:
===========================

{semantic_types}

{source_tag}

{CONFIDENCE_SCORING_DOCS}

{SKUEL_ARCHITECTURE_DOCS}
"""


# Pre-formatted documentation for common domains
TASKS_RELATIONSHIP_DOCS = format_semantic_docs(
    "tasks_relationship",
    "- DEPENDS_ON: Task dependencies (bidirectional)",
)

GOALS_RELATIONSHIP_DOCS = format_semantic_docs(
    "goals_relationship",
    "- SUPPORTS_GOAL: Habits supporting goals\n- GUIDED_BY_PRINCIPLE: Principle guidance",
)

HABITS_RELATIONSHIP_DOCS = format_semantic_docs(
    "habits_relationship",
    "- REINFORCES_KNOWLEDGE: Habits that strengthen knowledge",
)

EVENTS_RELATIONSHIP_DOCS = format_semantic_docs(
    "events_relationship",
    "- PRACTICES_KNOWLEDGE: Events that practice knowledge",
)

CHOICES_RELATIONSHIP_DOCS = format_semantic_docs(
    "choices_relationship",
    "- INFORMED_BY: Knowledge informing choices\n- ALIGNED_WITH: Principle alignment",
)

PRINCIPLES_RELATIONSHIP_DOCS = format_semantic_docs(
    "principles_relationship",
    "- GROUNDED_IN: Knowledge grounding principles",
)

FINANCE_RELATIONSHIP_DOCS = format_semantic_docs(
    "finance_relationship",
)

GENERIC_RELATIONSHIP_DOCS = format_semantic_docs(
    "generic_relationship",
)
