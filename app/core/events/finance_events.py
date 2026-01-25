"""
Finance Domain Events
=====================

Events published when finance/expense operations occur.

These events enable:
- User context invalidation when expenses change
- Budget tracking and alerts
- Spending pattern analysis
- Cross-domain financial impact tracking

Version: 1.0.0
Date: 2025-10-16
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class ExpenseCreated(BaseEvent):
    """
    Published when a new expense is created.

    Triggers:
    - User context invalidation (financial state changes)
    - Budget recalculation
    - Spending pattern updates
    - Goal impact analysis (for goal-aligned expenses)
    """

    expense_uid: str
    user_uid: str
    description: str
    amount: float
    category: str
    expense_date: date
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "expense.created"


@dataclass(frozen=True)
class ExpenseUpdated(BaseEvent):
    """
    Published when an expense is updated.

    Triggers:
    - User context invalidation (expense details changed)
    - Budget recalculation (if amount changed)
    - Category tracking updates
    """

    expense_uid: str
    user_uid: str
    updated_fields: dict[str, Any]
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "expense.updated"


@dataclass(frozen=True)
class ExpenseDeleted(BaseEvent):
    """
    Published when an expense is deleted.

    Triggers:
    - User context invalidation (financial history changes)
    - Budget recalculation
    - Spending pattern recalculation
    """

    expense_uid: str
    user_uid: str
    description: str
    amount: float
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "expense.deleted"


@dataclass(frozen=True)
class ExpensePaid(BaseEvent):
    """
    Published when an expense is marked as paid.

    Triggers:
    - User context invalidation (payment status changes)
    - Cash flow tracking
    - Budget status updates
    """

    expense_uid: str
    user_uid: str
    amount: float
    payment_date: date
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "expense.paid"
