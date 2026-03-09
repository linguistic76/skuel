"""Askesis-specific enums for pedagogical companion interactions."""

from enum import Enum


class ConversationStyle(str, Enum):
    """Communication styles for Askesis interactions."""

    DIRECT = "direct"  # Concise, to-the-point responses
    EXPLORATORY = "exploratory"  # Deep-dive, questioning approach
    SUPPORTIVE = "supportive"  # Encouraging, empathetic tone
    ANALYTICAL = "analytical"  # Data-driven, logical responses
    CREATIVE = "creative"  # Brainstorming, ideation focus
    COACHING = "coaching"  # Guiding questions, self-discovery


class QueryComplexity(str, Enum):
    """Complexity levels of user queries."""

    SIMPLE = "simple"  # Single domain, straightforward
    MODERATE = "moderate"  # 2-3 domains, some complexity
    COMPLEX = "complex"  # Multiple domains, interconnected
    SYSTEMIC = "systemic"  # Life-wide implications, many domains


class IntegrationSuccess(str, Enum):
    """Success levels of domain integration."""

    EXCELLENT = "excellent"  # Perfect synthesis, high user value
    GOOD = "good"  # Effective integration, clear benefit
    ACCEPTABLE = "acceptable"  # Basic integration, some value
    POOR = "poor"  # Weak integration, limited value
    FAILED = "failed"  # No meaningful integration achieved
