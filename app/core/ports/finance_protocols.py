"""
Finance Service Protocols
=========================

Protocols for finance-related outbound adapters.

Firefly III (ADR-051) replaces SKUEL's expense, budget, and reporting module.
The invoice module remains local. `FireflyOperations` is the thin contract
services depend on so nothing outside `adapters/outbound/firefly_client.py`
knows about Firefly's REST shape.

See: /docs/patterns/protocol_architecture.md, /docs/decisions/ADR-051-firefly-iii-finance-integration.md
"""

from __future__ import annotations

from typing import Literal, Protocol, TypedDict, runtime_checkable

from core.utils.result_simplified import Result

# ============================================================================
# BOOKS
# ============================================================================

FireflyBook = Literal["personal", "skuel"]
"""Which Firefly user account to target. Each book has its own PAT."""


# ============================================================================
# DTOs (match Firefly III REST response shapes we actually use)
# ============================================================================


class FireflyTransaction(TypedDict, total=False):
    """A single Firefly III transaction (withdrawal, deposit, or transfer)."""

    transaction_id: str
    transaction_journal_id: str
    type: Literal["withdrawal", "deposit", "transfer"]
    date: str  # ISO 8601
    amount: str  # Firefly returns strings for exact decimal
    currency_code: str
    description: str
    category_name: str | None
    budget_name: str | None
    source_name: str
    destination_name: str
    tags: list[str]
    notes: str | None


class FireflyBudget(TypedDict, total=False):
    """A Firefly III budget entry (envelope + current-period spent/limit)."""

    budget_id: str
    name: str
    active: bool
    currency_code: str
    spent: str
    limit: str | None
    period_start: str | None
    period_end: str | None


class FireflyCategory(TypedDict, total=False):
    """A Firefly III category entry."""

    category_id: str
    name: str
    spent: str
    earned: str


class FireflyAccountBalance(TypedDict, total=False):
    """A Firefly III asset/revenue/expense account balance snapshot."""

    account_id: str
    name: str
    type: str
    currency_code: str
    current_balance: str


class FireflyInsightRow(TypedDict, total=False):
    """Row from Firefly III insight endpoints (category/budget spent by period)."""

    name: str
    difference: str
    currency_code: str


class FireflyTransactionCreate(TypedDict, total=False):
    """Payload for creating a Firefly III transaction.

    Minimum required: type, date, amount, description, source_name, destination_name.
    """

    type: Literal["withdrawal", "deposit", "transfer"]
    date: str  # ISO 8601
    amount: str
    description: str
    source_name: str
    destination_name: str
    category_name: str | None
    budget_name: str | None
    currency_code: str | None
    tags: list[str] | None
    notes: str | None
    external_id: str | None  # idempotency key (Stripe event id)


# ============================================================================
# PROTOCOL
# ============================================================================


@runtime_checkable
class FireflyOperations(Protocol):
    """Protocol for the Firefly III REST adapter.

    Implementations: FireflyClient (adapters/outbound/firefly_client.py)

    The `book` parameter selects which Firefly user account (and therefore
    which Personal Access Token) to use — `"personal"` for Mike's personal
    finances, `"skuel"` for SKUEL business. One Firefly instance, two users.
    """

    async def list_transactions(
        self,
        book: FireflyBook,
        *,
        start: str | None = None,
        end: str | None = None,
        transaction_type: Literal["withdrawal", "deposit", "transfer"] | None = None,
        limit: int = 100,
    ) -> Result[list[FireflyTransaction]]:
        """List transactions for a book within an optional date range."""
        ...

    async def create_transaction(
        self, book: FireflyBook, payload: FireflyTransactionCreate
    ) -> Result[FireflyTransaction]:
        """Create a new transaction. `external_id` makes this idempotent."""
        ...

    async def find_transaction_by_external_id(
        self, book: FireflyBook, external_id: str
    ) -> Result[FireflyTransaction | None]:
        """Look up an existing transaction by its Stripe-event external id."""
        ...

    async def list_budgets(self, book: FireflyBook) -> Result[list[FireflyBudget]]:
        """List all budgets for a book (includes current-period spent/limit)."""
        ...

    async def list_categories(self, book: FireflyBook) -> Result[list[FireflyCategory]]:
        """List all categories for a book with spent/earned totals."""
        ...

    async def list_accounts(
        self,
        book: FireflyBook,
        *,
        account_type: Literal["asset", "revenue", "expense"] | None = None,
    ) -> Result[list[FireflyAccountBalance]]:
        """List accounts with current balances for a book."""
        ...

    async def category_insight(
        self, book: FireflyBook, *, start: str, end: str
    ) -> Result[list[FireflyInsightRow]]:
        """Firefly insight — spent per category in a date range."""
        ...

    async def budget_insight(
        self, book: FireflyBook, *, start: str, end: str
    ) -> Result[list[FireflyInsightRow]]:
        """Firefly insight — spent per budget in a date range."""
        ...

    async def health_check(self, book: FireflyBook) -> Result[bool]:
        """Verify the Firefly instance + PAT are reachable."""
        ...


__all__ = [
    "FireflyAccountBalance",
    "FireflyBook",
    "FireflyBudget",
    "FireflyCategory",
    "FireflyInsightRow",
    "FireflyOperations",
    "FireflyTransaction",
    "FireflyTransactionCreate",
]
