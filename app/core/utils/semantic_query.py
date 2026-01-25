"""
Semantic Query Utilities
=========================

Utilities for building semantic queries, extracting context,
and ranking results by relevance.
"""

from typing import Any, Protocol, runtime_checkable

from core.infrastructure.relationships.semantic_relationships import (
    SemanticRelationship,
    SemanticRelationshipType,
)
from core.utils.semantic_inference import RelationshipInferencer
from core.utils.semantic_patterns import TriplePattern


# Define protocols for semantic entities locally
@runtime_checkable
class HasSemanticRelationships(Protocol):
    """Protocol for objects with semantic_relationships attribute."""

    semantic_relationships: list[Any]


@runtime_checkable
class HasIsPrerequisite(Protocol):
    """Protocol for objects with is_prerequisite attribute."""

    is_prerequisite: bool


def build_semantic_cypher(pattern: TriplePattern, return_fields: list[str] | None = None) -> str:
    """Build a Cypher query from a semantic pattern."""
    # Build MATCH clause
    subject_match = pattern.subject if pattern.subject else "s"
    object_match = pattern.object if pattern.object else "o"

    rel_match = f"[r:{pattern.predicate.local_name.upper()}]" if pattern.predicate else "[r]"

    cypher = f"MATCH ({subject_match})-{rel_match}->({object_match})"

    # Add WHERE constraints
    where_clauses: list[str] = []
    for key, value in pattern.constraints.items():
        if "." in key:
            where_clauses.append(f"{key} = '{value}'")
        else:
            where_clauses.append(f"r.{key} = '{value}'")

    if where_clauses:
        cypher += " WHERE " + " AND ".join(where_clauses)

    # Add RETURN clause
    if return_fields:
        cypher += f" RETURN {', '.join(return_fields)}"
    else:
        cypher += f" RETURN {subject_match}, r, {object_match}"

    return cypher


def extract_semantic_context(
    entity_uid: str, relationships: list[SemanticRelationship], depth: int = 2
) -> dict[str, Any]:
    """Extract semantic context for an entity."""
    context: dict[str, Any] = {
        "entity": entity_uid,
        "direct_relationships": [],  # list[SemanticRelationship]
        "inferred_relationships": [],  # list[SemanticRelationship]
        "semantic_neighborhood": set(),  # set[str]
        "relationship_types": set(),  # set[str]
        "confidence_scores": {},  # dict[str, float]
    }

    # Process direct relationships
    for rel in relationships:
        if rel.subject_uid == entity_uid or rel.object_uid == entity_uid:
            context["direct_relationships"].append(rel)
            context["relationship_types"].add(rel.predicate.value)
            context["confidence_scores"][rel.object_uid] = rel.metadata.confidence

            # Add to neighborhood
            context["semantic_neighborhood"].add(rel.object_uid)
            if rel.subject_uid != entity_uid:
                context["semantic_neighborhood"].add(rel.subject_uid)

    # Infer additional relationships
    if depth > 1:
        inferencer = RelationshipInferencer()
        inferred = inferencer.infer_relationships(context["direct_relationships"])
        context["inferred_relationships"] = inferred

    return context


def rank_by_semantic_relevance(
    results: list[Any],
    query_context: dict[str, Any],
    relationship_weights: dict[SemanticRelationshipType, float] | None = None,
) -> list[tuple[Any, float]]:
    """Rank results by semantic relevance."""
    if not relationship_weights:
        relationship_weights = {
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING: 3.0,
            SemanticRelationshipType.BUILDS_MENTAL_MODEL: 2.5,
            SemanticRelationshipType.APPLIES_KNOWLEDGE_TO: 2.0,
            SemanticRelationshipType.SHARES_PRINCIPLE_WITH: 1.5,
            SemanticRelationshipType.COMPLEMENTS: 1.0,
        }

    ranked: list[tuple[Any, float]] = []
    for result in results:
        score = 0.0

        # Score based on relationship types
        if isinstance(result, HasSemanticRelationships):
            for rel in result.semantic_relationships:
                weight = relationship_weights.get(rel.predicate, 1.0)
                confidence = rel.metadata.confidence if rel.metadata else 0.5
                score += weight * confidence

        # Score based on query context match
        if (
            "intent" in query_context
            and query_context["intent"] == "prerequisites"
            and isinstance(result, HasIsPrerequisite)
        ):
            score += 5.0 if result.is_prerequisite else 0.0

        ranked.append((result, score))

    # Sort by score descending
    def get_score(item) -> Any:
        """Get score from (result, score) tuple."""
        return item[1]

    ranked.sort(key=get_score, reverse=True)

    return ranked
