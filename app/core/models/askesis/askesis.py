"""
Askesis Application Models
==========================

Tier 3 (Core) domain model for Askesis — the AI tutor/assistant.

`Askesis` is the immutable representation of a user's personalised assistant:
learned preferences, per-domain expertise, and intelligence metrics.

Three-tier pattern:
- Tier 1 (External): `askesis_request.py` (Pydantic)
- Tier 2 (Transfer): `askesis_dto.py` (mutable dataclasses)
- Tier 3 (Core): this module (frozen dataclasses)
"""

__version__ = "2.1"

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.models.askesis.askesis_dto import AskesisDTO
from core.models.enums import GuidanceMode
from core.models.enums.askesis_enums import QueryComplexity
from core.models.type_hints import UserUID


def _utcnow() -> Any:
    """Factory function for datetime.now(timezone.utc)"""
    return datetime.now(UTC)


# ============================================================================
# ASKESIS DOMAIN MODEL (Tier 3 - Frozen)
# ============================================================================


@dataclass(frozen=True, kw_only=True)
class Askesis:
    """
    Immutable Askesis domain model - AI Learning Assistant instance.

    Represents a personalized AI assistant that learns user preferences,
    domain expertise, and provides intelligent guidance across domains.

    Following three-tier pattern:
    - Tier 1 (External): AskesisCreateRequest/AskesisUpdateRequest (Pydantic)
    - Tier 2 (Transfer): AskesisDTO (mutable dataclass)
    - Tier 3 (Core): Askesis (frozen dataclass) - THIS CLASS
    """

    # Identity
    uid: str
    user_uid: UserUID
    name: str = "Askesis"  # Fixed: string value, not tuple
    version: str = "1.0"

    # Intelligence Metrics
    intelligence_confidence: float = 0.5  # 0.0 to 1.0
    total_conversations: int = 0  # Fixed: int value, not tuple
    total_domain_integrations: int = 0  # Fixed: int value, not tuple
    integration_success_rate: float = 0.0  # Fixed: float value, not tuple
    pattern_recognition_accuracy: float = 0.0  # Fixed: float value, not tuple
    proactive_guidance_success_rate: float = 0.0

    # User Preferences (learned)
    preferred_guidance_mode: GuidanceMode = GuidanceMode.DIRECT  # Fixed: enum value, not tuple
    preferred_complexity_level: QueryComplexity = (
        QueryComplexity.MODERATE
    )  # Fixed: enum value, not tuple
    response_preferences: tuple[tuple[str, float], ...] = ()  # Immutable dict as tuple of tuples

    # Domain Knowledge (immutable collections)
    domain_expertise_levels: tuple[
        tuple[str, float], ...
    ] = ()  # Fixed: empty tuple, not nested ((),)
    domain_usage_patterns: tuple[
        tuple[str, float], ...
    ] = ()  # Fixed: empty tuple, not nested ((),)
    cross_domain_synergies: tuple[tuple[str, float], ...] = ()

    # Learning State (immutable lists as tuples)
    active_learning_areas: tuple[str, ...] = ()  # Fixed: empty tuple, not nested ((),)
    knowledge_gaps: tuple[str, ...] = ()  # Fixed: empty tuple, not nested ((),)
    optimization_opportunities: tuple[str, ...] = ()

    # Metadata
    created_at: datetime = field(default_factory=_utcnow)  # Fixed: field, not tuple-wrapped
    updated_at: datetime = field(default_factory=_utcnow)
    last_interaction: datetime | None = None
    last_intelligence_update: datetime | None = None

    # ========================================================================
    # BUSINESS LOGIC METHODS
    # ========================================================================

    def get_expertise_level(self, domain: str) -> float:
        """Get user's expertise level in a specific domain (0.0 to 1.0)."""
        expertise_dict = dict(self.domain_expertise_levels)
        return expertise_dict.get(domain, 0.0)

    def get_domain_synergy(self, domain_pair: str) -> float:
        """Get synergy score between two domains."""
        synergy_dict = dict(self.cross_domain_synergies)
        return synergy_dict.get(domain_pair, 0.0)

    def is_learning_area_active(self, area: str) -> bool:
        """Check if an area is currently being actively learned."""
        return area in self.active_learning_areas

    def has_knowledge_gap(self, gap: str) -> bool:
        """Check if a specific knowledge gap exists."""
        return gap in self.knowledge_gaps

    def get_overall_intelligence_score(self) -> float:
        """Calculate overall AI intelligence score (0.0 to 1.0)."""
        metrics = [
            self.intelligence_confidence,
            self.integration_success_rate,
            self.pattern_recognition_accuracy,
            self.proactive_guidance_success_rate,
        ]
        return sum(metrics) / len(metrics) if metrics else 0.0

    def needs_intelligence_update(self, hours_threshold: int = 24) -> bool:
        """Check if intelligence metrics need updating."""
        if not self.last_intelligence_update:
            return True

        hours_since_update = (
            datetime.now(UTC) - self.last_intelligence_update
        ).total_seconds() / 3600
        return hours_since_update >= hours_threshold

    @classmethod
    def from_dto(cls, dto: "AskesisDTO") -> "Askesis":
        """Convert from mutable DTO to immutable domain model."""

        return cls(
            uid=dto.uid,
            user_uid=dto.user_uid,
            name=dto.name,
            version=dto.version,
            intelligence_confidence=dto.intelligence_confidence,
            total_conversations=dto.total_conversations,
            total_domain_integrations=dto.total_domain_integrations,
            integration_success_rate=dto.integration_success_rate,
            pattern_recognition_accuracy=dto.pattern_recognition_accuracy,
            proactive_guidance_success_rate=dto.proactive_guidance_success_rate,
            preferred_guidance_mode=(
                GuidanceMode(dto.preferred_guidance_mode)
                if isinstance(dto.preferred_guidance_mode, str)
                else dto.preferred_guidance_mode
            ),
            preferred_complexity_level=(
                QueryComplexity(dto.preferred_complexity_level)
                if isinstance(dto.preferred_complexity_level, str)
                else dto.preferred_complexity_level
            ),
            response_preferences=tuple(dto.response_preferences.items())
            if dto.response_preferences
            else (),
            domain_expertise_levels=tuple(dto.domain_expertise_levels.items())
            if dto.domain_expertise_levels
            else (),
            domain_usage_patterns=tuple(dto.domain_usage_patterns.items())
            if dto.domain_usage_patterns
            else (),
            cross_domain_synergies=tuple(dto.cross_domain_synergies.items())
            if dto.cross_domain_synergies
            else (),
            active_learning_areas=tuple(dto.active_learning_areas)
            if dto.active_learning_areas
            else (),
            knowledge_gaps=tuple(dto.knowledge_gaps) if dto.knowledge_gaps else (),
            optimization_opportunities=tuple(dto.optimization_opportunities)
            if dto.optimization_opportunities
            else (),
            created_at=dto.created_at or datetime.now(UTC),
            last_interaction=dto.last_interaction,
            last_intelligence_update=dto.last_intelligence_update,
        )

    def to_dto(self) -> "AskesisDTO":
        """Convert from immutable domain model to mutable DTO."""
        from core.models.dto_helpers import domain_to_dto

        return domain_to_dto(self, AskesisDTO)
