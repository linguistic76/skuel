"""
Confidence Filter Utilities
===========================

Standardized confidence filtering for relationship queries.

*Last updated: 2025-12-05*

Problem: Confidence filtering was implemented inconsistently across the codebase:
- Some queries use `coalesce(r.confidence, 1.0)` (assume full confidence)
- Some use `coalesce(r.confidence, 0.8)` (conservative default)
- Some use `coalesce(r.confidence, 0.0)` (strict, require explicit confidence)
- Some use complex multi-field fallbacks

This module provides standardized helpers for consistency.

Usage:
    from core.models.query.confidence_filter import (
        build_confidence_clause,
        build_confidence_field,
        ConfidenceMode,
        CONFIDENCE_DEFAULTS,
    )

    # In WHERE clause
    clause = build_confidence_clause("r", "min_confidence", mode="standard")
    # Returns: "coalesce(r.confidence, 0.8) >= $min_confidence"

    # In RETURN clause
    field = build_confidence_field("r", mode="strict")
    # Returns: "coalesce(r.confidence, 1.0)"
"""

from typing import Literal

# Confidence mode types
ConfidenceMode = Literal["strict", "standard", "lenient", "explicit"]

# Default confidence values by mode
CONFIDENCE_DEFAULTS: dict[ConfidenceMode, float] = {
    "strict": 1.0,  # Assume full confidence if missing (trust explicit relationships)
    "standard": 0.8,  # Conservative default for traversals (most common case)
    "lenient": 0.5,  # Include inferred/weaker relationships
    "explicit": 0.0,  # Require explicit confidence (very strict filtering)
}


def build_confidence_clause(
    rel_var: str = "r",
    param_name: str = "min_confidence",
    mode: ConfidenceMode = "standard",
) -> str:
    """
    Build standardized confidence filter clause for WHERE.

    Args:
        rel_var: Cypher variable for the relationship
        param_name: Parameter name for minimum confidence threshold
        mode: Default mode if relationship has no confidence property
            - "strict": Default 1.0 (assume full confidence if missing)
            - "standard": Default 0.8 (conservative default)
            - "lenient": Default 0.5 (include weaker relationships)
            - "explicit": Default 0.0 (require explicit confidence)

    Returns:
        Cypher WHERE clause fragment (without WHERE keyword)

    Example:
        >>> build_confidence_clause("rel", "min_conf")
        'coalesce(rel.confidence, 0.8) >= $min_conf'

        >>> build_confidence_clause("r", "threshold", mode="strict")
        'coalesce(r.confidence, 1.0) >= $threshold'
    """
    default = CONFIDENCE_DEFAULTS[mode]
    return f"coalesce({rel_var}.confidence, {default}) >= ${param_name}"


def build_confidence_field(
    rel_var: str = "r",
    mode: ConfidenceMode = "standard",
    alias: str | None = None,
) -> str:
    """
    Build confidence extraction for RETURN clause.

    Args:
        rel_var: Cypher variable for the relationship
        mode: Default mode if relationship has no confidence property
        alias: Optional alias for the field (e.g., "as confidence")

    Returns:
        Cypher expression for confidence value

    Example:
        >>> build_confidence_field("r")
        'coalesce(r.confidence, 0.8)'

        >>> build_confidence_field("rel", alias="edge_confidence")
        'coalesce(rel.confidence, 0.8) as edge_confidence'
    """
    default = CONFIDENCE_DEFAULTS[mode]
    expr = f"coalesce({rel_var}.confidence, {default})"

    if alias:
        expr = f"{expr} as {alias}"

    return expr


def build_multi_fallback_confidence(
    rel_var: str = "r",
    fallback_fields: list[str] | None = None,
    final_default: float = 1.0,
    alias: str | None = None,
) -> str:
    """
    Build confidence with multi-field fallback chain.

    For relationships that may store confidence-like values in different fields
    (confidence, alignment_score, strength, weight, etc.).

    Args:
        rel_var: Cypher variable for the relationship
        fallback_fields: Fields to check in order (default: ["confidence", "alignment_score", "strength"])
        final_default: Value if no fields have values
        alias: Optional alias

    Returns:
        Cypher expression with fallback chain

    Example:
        >>> build_multi_fallback_confidence("r")
        'coalesce(r.confidence, r.alignment_score, r.strength, 1.0)'

        >>> build_multi_fallback_confidence("rel", ["weight", "score"], 0.5)
        'coalesce(rel.weight, rel.score, 0.5)'
    """
    if fallback_fields is None:
        fallback_fields = ["confidence", "alignment_score", "strength"]

    fields = [f"{rel_var}.{field}" for field in fallback_fields]
    fields.append(str(final_default))

    expr = f"coalesce({', '.join(fields)})"

    if alias:
        expr = f"{expr} as {alias}"

    return expr


def build_path_confidence_aggregation(
    path_var: str = "path",
    mode: ConfidenceMode = "standard",
    alias: str = "confidences",
) -> str:
    """
    Build confidence extraction for path traversal queries.

    Extracts confidence from all relationships in a path as a list.

    Args:
        path_var: Cypher variable for the path
        mode: Default mode for missing confidence values
        alias: Alias for the list

    Returns:
        Cypher list comprehension expression

    Example:
        >>> build_path_confidence_aggregation("p")
        '[rel in relationships(p) | coalesce(rel.confidence, 0.8)] as confidences'
    """
    default = CONFIDENCE_DEFAULTS[mode]
    return f"[rel in relationships({path_var}) | coalesce(rel.confidence, {default})] as {alias}"


__all__ = [
    "CONFIDENCE_DEFAULTS",
    "ConfidenceMode",
    "build_confidence_clause",
    "build_confidence_field",
    "build_multi_fallback_confidence",
    "build_path_confidence_aggregation",
]
