"""
Askesis DTO Models (Tier 2 - Transfer)
=======================================

Mutable data transfer objects for Askesis domain.
Used for data movement between layers and API responses.
"""

from dataclasses import dataclass, field
from datetime import datetime

from core.models.enums import GuidanceMode
from core.models.enums.askesis_enums import QueryComplexity
from core.models.type_hints import UserUID


@dataclass
class AskesisDTO:
    """Mutable DTO for Askesis instances."""

    uid: str
    user_uid: UserUID
    name: str = "Askesis"
    version: str = "1.0"

    # Intelligence Metrics
    intelligence_confidence: float = 0.5  # 0.0 to 1.0,
    total_conversations: int = 0
    total_domain_integrations: int = 0

    integration_success_rate: float = 0.0
    pattern_recognition_accuracy: float = 0.0
    proactive_guidance_success_rate: float = 0.0

    # User Preferences (learned)
    preferred_guidance_mode: str = GuidanceMode.DIRECT.value
    preferred_complexity_level: str = QueryComplexity.MODERATE.value
    response_preferences: dict[str, float] = field(default_factory=dict)

    # Domain Knowledge
    domain_expertise_levels: dict[str, float] = field(default_factory=dict)
    domain_usage_patterns: dict[str, float] = field(default_factory=dict)
    cross_domain_synergies: dict[str, float] = field(default_factory=dict)

    # Learning State
    active_learning_areas: list[str] = field(default_factory=list)
    knowledge_gaps: list[str] = field(default_factory=list)
    optimization_opportunities: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime | None = None

    last_interaction: datetime | None = None

    last_intelligence_update: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class AskesisCreateDTO:
    """DTO for creating new Askesis instances."""

    user_uid: UserUID
    name: str = "Askesis"
    version: str = "1.0"
    preferred_guidance_mode: str = GuidanceMode.DIRECT.value
    preferred_complexity_level: str = QueryComplexity.MODERATE.value


@dataclass
class AskesisUpdateDTO:
    """DTO for updating Askesis instances."""

    uid: str

    # Optional updates
    name: str | None = None

    version: str | None = None
    intelligence_confidence: float | None = None

    preferred_guidance_mode: str | None = None
    preferred_complexity_level: str | None = None

    # Intelligence metrics updates
    total_conversations: int | None = None

    total_domain_integrations: int | None = None
    integration_success_rate: float | None = None

    pattern_recognition_accuracy: float | None = None
    proactive_guidance_success_rate: float | None = None

    # Learning state updates
    active_learning_areas: list[str] | None = None

    knowledge_gaps: list[str] | None = None

    optimization_opportunities: list[str] | None = None

    # Timestamp update
    last_interaction: datetime | None = None

    last_intelligence_update: datetime | None = None
