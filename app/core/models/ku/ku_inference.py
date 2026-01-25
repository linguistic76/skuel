"""
Knowledge Inference Data Models
================================

Core data structures for knowledge inference operations.
Used by ku_inference_service for automatic knowledge connection detection.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KnowledgeConnection:
    """Represents a connection between domain entity and knowledge"""

    knowledge_uid: str
    connection_type: str  # 'applies', 'requires', 'generates', 'validates'
    confidence: float  # 0.0 to 1.0
    source: str  # 'explicit', 'inferred', 'system'
    metadata: dict[str, Any] | None = None  # type: ignore[assignment]


@dataclass(frozen=True)
class LearningOpportunity:
    """Represents a learning opportunity extracted from domain activity"""

    title: str
    description: str
    knowledge_domain: str
    estimated_value: float  # 0.0 to 1.0
    prerequisites: list[str] | None = None  # type: ignore[assignment]
    outcomes: list[str] | None = None  # type: ignore[assignment]


@dataclass(frozen=True)
class KnowledgeInsight:
    """Represents an insight that could become new knowledge"""

    title: str
    content: str
    insight_type: str  # 'pattern', 'best_practice', 'anti_pattern', 'technique'
    confidence: float
    source_entities: list[str]
    domain: str
    metadata: dict[str, Any] | None = None  # type: ignore[assignment]
