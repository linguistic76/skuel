"""
Finance Enums - Single Source of Truth
======================================

Consolidated enums for the Finance domain (January 2026).
Previously duplicated in finance_dto.py and finance_pure.py.

Per One Path Forward: One definition, imported everywhere.
"""

from enum import Enum


class ExpenseStatus(Enum):
    """Status for expense tracking."""

    PENDING = "pending"
    PAID = "paid"
    CLEARED = "cleared"
    RECONCILED = "reconciled"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentMethod(Enum):
    """Payment method for expenses."""

    CASH = "cash"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    CHECK = "check"
    PAYPAL = "paypal"
    VENMO = "venmo"
    CRYPTO = "crypto"
    OTHER = "other"


class ExpenseCategory(Enum):
    """Main expense categories."""

    PERSONAL = "personal"
    TWO222 = "2222"
    SKUEL = "skuel"


class RecurrencePattern(Enum):
    """Patterns for recurring expenses."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"


class BudgetPeriod(Enum):
    """Budget period types."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
