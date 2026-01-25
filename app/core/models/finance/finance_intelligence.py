"""
Finance Intelligence Entities
==============================

Persistent entities that bring learning intelligence to the Finance domain.
These entities transform Finance from simple transaction tracking to adaptive,
learning-aware intelligence that optimizes spending, budgeting, and financial health.

Following the Knowledge domain pattern:
- Persistent entities that learn from spending behavior
- Rich analytics that improve financial recommendations
- Temporal tracking and pattern detection
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SpendingVelocity(str, Enum):
    """Spending rate patterns."""

    VERY_CONSERVATIVE = "very_conservative"
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    LIBERAL = "liberal"
    VERY_LIBERAL = "very_liberal"


class FinancialHealthTier(str, Enum):
    """Overall financial health assessment."""

    CRITICAL = "critical"
    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"


class SpendingPattern(str, Enum):
    """Common spending behavior patterns."""

    IMPULSE_BUYER = "impulse_buyer"
    DEAL_SEEKER = "deal_seeker"
    LUXURY_ORIENTED = "luxury_oriented"
    VALUE_FOCUSED = "value_focused"
    MINIMALIST = "minimalist"
    SOCIAL_SPENDER = "social_spender"
    STRESS_SPENDER = "stress_spender"
    HABITUAL = "habitual"


@dataclass(frozen=True)
class FinancialHealthScore:
    """
    Persistent Financial Health Intelligence.

    Tracks financial health with sophisticated analytics that improve
    budgeting, spending recommendations, and financial planning.
    """

    uid: str
    user_uid: str
    overall_health: FinancialHealthTier
    health_score: float
    budget_adherence_rate: float
    savings_rate: float
    emergency_fund_months: float
    spending_pattern: SpendingPattern
    created_at: datetime
    updated_at: datetime

    def is_healthy(self) -> bool:
        return self.overall_health in [FinancialHealthTier.GOOD, FinancialHealthTier.EXCELLENT]


def create_financial_health_score(user_uid: str) -> FinancialHealthScore:
    """Create initial financial health score."""
    return FinancialHealthScore(
        uid=f"fin_health_{user_uid}",
        user_uid=user_uid,
        overall_health=FinancialHealthTier.FAIR,
        health_score=0.5,
        budget_adherence_rate=0.7,
        savings_rate=0.1,
        emergency_fund_months=0.0,
        spending_pattern=SpendingPattern.HABITUAL,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
