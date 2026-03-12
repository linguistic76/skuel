"""
Intelligence Tier Configuration
================================

Two-layer system controlling whether AI/LLM services are enabled.

CORE: Analytics only — BaseAnalyticsService, UserContextIntelligence,
      GraphIntelligenceService. Pure Python + Cypher. No API costs.

FULL: Analytics + AI — all CORE features plus BaseAIService, OpenAIService,
      HuggingFaceEmbeddingsService, embeddings, LLM chat, content processing.
      Costs money per API call.

Usage:
    from core.config.intelligence_tier import IntelligenceTier

    tier = IntelligenceTier.from_env()
    if tier.ai_enabled:
        # create LLM/embedding services

See: /docs/decisions/ADR-043-intelligence-tier-toggle.md
"""

import os
from enum import StrEnum


class IntelligenceTier(StrEnum):
    """System-level intelligence tier controlling AI service availability."""

    CORE = "core"  # Analytics only — no API costs
    FULL = "full"  # Analytics + AI services

    @classmethod
    def from_env(cls) -> "IntelligenceTier":
        """Read tier from INTELLIGENCE_TIER env var (default: full)."""
        raw = os.getenv("INTELLIGENCE_TIER", "full").strip().lower()
        try:
            return cls(raw)
        except ValueError:
            from core.utils.logging import get_logger

            logger = get_logger("skuel.config")
            logger.warning(f"Unknown INTELLIGENCE_TIER '{raw}', defaulting to FULL")
            return cls.FULL

    @property
    def ai_enabled(self) -> bool:
        """True when LLM/embedding services should be created."""
        return self == IntelligenceTier.FULL
