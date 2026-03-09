"""
Core Query Types
================

Abstract semantic concepts consumed by domain models and services.
These types are infrastructure-agnostic and belong in the core layer.

Extracted from core/models/query/_query_models.py during the query module
relocation to adapters/persistence/neo4j/query/.
"""

from enum import Enum


class IndexStrategy(Enum):
    """Index utilization strategies for query optimization."""

    UNIQUE_LOOKUP = "unique_lookup"
    FULLTEXT_SEARCH = "fulltext_search"
    RANGE_FILTER = "range_filter"
    VECTOR_SEARCH = "vector_search"
    TEXT_SEARCH = "text_search"
    COMPOSITE_INDEX = "composite_index"
    NO_INDEX = "no_index"


class QueryIntent(Enum):
    """Types of query intents for semantic understanding."""

    # Generic intents (cross-domain)
    EXPLORATORY = "exploratory"
    SPECIFIC = "specific"
    HIERARCHICAL = "hierarchical"
    PREREQUISITE = "prerequisite"
    PRACTICE = "practice"
    AGGREGATION = "aggregation"
    RELATIONSHIP = "relationship"

    # Domain-specific intents (December 2025)
    GOAL_ACHIEVEMENT = "goal_achievement"
    PRINCIPLE_EMBODIMENT = "principle_embodiment"
    PRINCIPLE_ALIGNMENT = "principle_alignment"
    SCHEDULED_ACTION = "scheduled_action"
