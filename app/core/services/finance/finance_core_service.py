"""
Finance Core Service
===================

*Last updated: 2026-01-17*

Core CRUD service for financial operations (expenses).

This service handles ONLY basic CRUD operations for expenses:
- get_expense(uid)
- get_user_expenses(user_uid)
- create_expense(...)
- update_expense(...)
- delete_expense(...)
- Publishes domain events (ExpenseCreated, ExpenseUpdated, ExpensePaid, ExpenseDeleted)

Business logic, budgets, and reporting are handled by specialized
sub-services orchestrated through FinanceService facade.

Architecture Pattern:
--------------------
Finance is a standalone bookkeeping domain.
Simple, focused on tracking expenses and budgets.

FinanceCoreService (standalone)
    ↓
FinanceService (Facade, delegates to 4 sub-services)
    - FinanceCoreService (CRUD)
    - FinanceBudgetService (Budget management)
    - FinanceReportingService (Reports & summaries)
    - FinanceInvoiceService (Invoice management)

Security:
---------
Finance is admin-only. Route-level security is enforced via @require_admin.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.finance_events import (
    ExpenseCreated,
    ExpenseDeleted,
    ExpensePaid,
    ExpenseUpdated,
)
from core.models.finance.finance_pure import ExpensePure, ExpenseStatus
from core.ports.domain_protocols import FinancesOperations
from core.ports.query_types import FinanceUpdatePayload
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins


class FinanceCoreService:
    """
    Core CRUD service for expenses.

    Standalone service for pure bookkeeping operations.
    Finance is admin-only with no ownership verification.

    This is the "Core" in the Core + Facade pattern.
    The FinanceService facade delegates to this for basic CRUD,
    plus 3 other specialized sub-services (Budget, Reporting, Invoice).

    Event-Driven Architecture:
    - Publishes ExpenseCreated on creation
    - Publishes ExpensePaid when status changed to PAID
    - Publishes ExpenseUpdated for other updates
    - Publishes ExpenseDeleted on deletion

    SKUEL Architecture:
    - Standalone service (no BaseService inheritance)
    """

    def __init__(self, backend: FinancesOperations, event_bus: Any = None) -> None:
        """
        Initialize finance core service.

        Args:
            backend: Protocol-based backend for finance operations
            event_bus: Optional event bus for domain events
        """
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.finance.core")

    @property
    def entity_label(self) -> str:
        """Return the graph label for Expense entities."""
        return "Expense"

    # ========================================================================
    # BASE CRUD OPERATIONS
    # ========================================================================

    async def get(self, uid: str) -> Result[ExpensePure | None]:
        """
        Get an expense by UID.

        Args:
            uid: Expense UID

        Returns:
            Result containing ExpensePure or None if not found
        """
        return await self.backend.get(uid)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict | None = None,
    ) -> Result[tuple[builtins.list[ExpensePure], int]]:
        """
        List expenses with optional filters.

        Args:
            limit: Maximum number of results
            offset: Pagination offset
            filters: Optional filter dictionary

        Returns:
            Result containing (list of expenses, total count)
        """
        return await self.backend.list(limit=limit, offset=offset, filters=filters)

    # ========================================================================
    # VALIDATION
    # ========================================================================

    def _validate_create(self, expense: ExpensePure) -> Result[None] | None:
        """
        Validate expense creation with business rules.

        Business Rules:
        1. Amount must be positive (> 0)

        Args:
            expense: ExpensePure domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        # Business Rule: Amount must be positive
        if expense.amount <= 0:
            return Result.fail(
                Errors.validation(
                    message="Expense amount must be positive",
                    field="amount",
                    value=expense.amount,
                )
            )

        return None  # All validations passed

    def _validate_update(
        self, current: ExpensePure, updates: dict[str, Any]
    ) -> Result[None] | None:
        """
        Validate expense updates with business rules.

        Business Rules:
        1. If updating amount, must be positive (> 0)
        2. If updating amount, cannot increase by more than 1000% (data entry error prevention)
        3. Cannot change category for expenses older than 30 days (accounting period locked)

        Args:
            current: Current expense state
            updates: Dictionary of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        # Business Rule 1: Amount must be positive (if being updated)
        if "amount" in updates:
            amount = updates["amount"]
            if amount <= 0:
                return Result.fail(
                    Errors.validation(
                        message="Expense amount must be positive",
                        field="amount",
                        value=amount,
                    )
                )

            # Business Rule 2: Prevent unreasonable amount increases (data entry errors)
            if current.amount and current.amount > 0:
                increase_ratio = amount / current.amount
                if increase_ratio > 10.0:
                    return Result.fail(
                        Errors.validation(
                            message=f"Amount increase of {increase_ratio:.1f}x seems unusual. "
                            f"Current: ${current.amount:.2f}, New: ${amount:.2f}. "
                            f"Please verify this is not a data entry error.",
                            field="amount",
                            value=amount,
                        )
                    )

        # Business Rule 3: Category changes locked after 30 days (accounting period)
        if "category" in updates and updates["category"] != current.category:
            days_old = (datetime.now() - current.created_at).days
            if days_old > 30:
                return Result.fail(
                    Errors.validation(
                        message=f"Cannot change category for expenses older than 30 days "
                        f"(accounting period locked). This expense is {days_old} days old.",
                        field="category",
                        value=updates["category"],
                    )
                )

        return None  # All validations passed

    # ========================================================================
    # EVENT-DRIVEN CRUD OPERATIONS
    # ========================================================================

    async def create(self, entity: ExpensePure) -> Result[ExpensePure]:
        """
        Create an expense and publish ExpenseCreated event.

        Args:
            entity: Expense to create

        Returns:
            Result containing created ExpensePure

        Events Published:
            - ExpenseCreated: When expense is successfully created
        """
        # Validate before creation
        validation = self._validate_create(entity)
        if validation is not None:
            return Result.fail(validation)

        # Create via backend
        result = await self.backend.create(entity)

        # Publish ExpenseCreated event
        if result.is_ok:
            expense = result.value
            event = ExpenseCreated(
                expense_uid=expense.uid,
                user_uid=expense.user_uid,
                description=expense.description,
                amount=expense.amount,
                category=expense.category.value,
                expense_date=expense.expense_date,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[ExpensePure]:
        """
        Update an expense and publish appropriate events.

        Publishes ExpensePaid if status changed to PAID,
        otherwise publishes ExpenseUpdated.

        Args:
            uid: Expense UID
            updates: Dictionary of field updates

        Returns:
            Result containing updated ExpensePure

        Events Published:
            - ExpensePaid: If status changed to PAID
            - ExpenseUpdated: For other updates
        """
        # Get current expense for validation and event tracking
        current_result = await self.get(uid)
        if current_result.is_error:
            return Result.fail(current_result.expect_error())

        current = current_result.value
        if not current:
            return Result.fail(Errors.not_found(resource="Expense", identifier=uid))

        # Validate update
        validation = self._validate_update(current, updates)
        if validation is not None:
            return Result.fail(validation)

        # Track status for event publishing
        old_status = current.status if "status" in updates else None

        # Update via backend
        result = await self.backend.update(uid, updates)

        # Publish appropriate event based on what changed
        if result.is_ok:
            expense = result.value

            # Priority: Status changed to PAID
            new_status = updates.get("status")
            is_paid_status = (
                new_status == ExpenseStatus.PAID or new_status == ExpenseStatus.PAID.value
            )
            if "status" in updates and is_paid_status and old_status != ExpenseStatus.PAID:
                paid_event = ExpensePaid(
                    expense_uid=expense.uid,
                    user_uid=expense.user_uid,
                    amount=expense.amount,
                    payment_date=updates.get("paid_at", expense.expense_date),
                    occurred_at=datetime.now(),
                )
                await publish_event(self.event_bus, paid_event, self.logger)

            # Default: Generic update
            else:
                updated_event = ExpenseUpdated(
                    expense_uid=expense.uid,
                    user_uid=expense.user_uid,
                    updated_fields=updates,
                    occurred_at=datetime.now(),
                )
                await publish_event(self.event_bus, updated_event, self.logger)

        return result

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        DETACH DELETE an expense and publish ExpenseDeleted event.

        Args:
            uid: Expense UID
            cascade: Whether to cascade delete (default False)

        Returns:
            Result indicating success

        Events Published:
            - ExpenseDeleted: When expense is successfully deleted
        """
        # Get expense details before deletion for event publishing
        expense_result = await self.get(uid)
        if expense_result.is_error:
            return Result.fail(expense_result.expect_error())

        # Delete via backend
        result = await self.backend.delete(uid, cascade=cascade)

        # Publish ExpenseDeleted event
        if result.is_ok and expense_result.value:
            expense = expense_result.value
            event = ExpenseDeleted(
                expense_uid=uid,
                user_uid=expense.user_uid,
                amount=expense.amount,
                description=expense.description,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # CONVENIENCE METHODS - Domain-Specific Naming
    # ========================================================================

    async def get_expense(self, expense_uid: str) -> Result[ExpensePure]:
        """
        Get a specific expense by UID.

        Args:
            expense_uid: Expense UID

        Returns:
            Result[ExpensePure] - success contains ExpensePure, not found is an error
        """
        result = await self.get(expense_uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found("Expense", expense_uid))
        return Result.ok(result.value)

    async def get_user_expenses(
        self, user_uid: str, limit: int = 100, offset: int = 0
    ) -> Result[tuple[builtins.list[ExpensePure], int]]:
        """
        Get all expenses for a user.

        Args:
            user_uid: User UID
            limit: Maximum number of expenses to return (default: 100)
            offset: Number of expenses to skip (default: 0)

        Returns:
            Result containing (list of expenses, total count)
        """
        filters = {"user_uid": user_uid}
        return await self.list(limit=limit, offset=offset, filters=filters)

    async def create_expense(self, expense: ExpensePure) -> Result[ExpensePure]:
        """
        Create a new expense.

        Args:
            expense: Expense to create

        Returns:
            Result containing created ExpensePure
        """
        return await self.create(expense)

    async def update_expense(self, expense_uid: str, updates: dict) -> Result[ExpensePure]:
        """
        Update an expense.

        Args:
            expense_uid: Expense UID
            updates: Dictionary of fields to update

        Returns:
            Result containing updated ExpensePure
        """
        return await self.update(expense_uid, updates)

    async def delete_expense(self, expense_uid: str) -> Result[bool]:
        """
        Delete an expense.

        Args:
            expense_uid: Expense UID

        Returns:
            Result containing True if successful
        """
        return await self.delete(expense_uid)

    async def list_expenses(
        self, limit: int = 100, offset: int = 0, filters: dict | None = None
    ) -> Result[tuple[builtins.list[ExpensePure], int]]:
        """
        List expenses with optional filters.

        Args:
            limit: Maximum number of expenses to return (default: 100)
            offset: Number of expenses to skip (default: 0)
            filters: Optional filters dictionary

        Returns:
            Result containing (list of expenses, total count)
        """
        return await self.list(limit=limit, offset=offset, filters=filters)

    # ========================================================================
    # SIMPLE EXPENSE OPERATIONS
    # ========================================================================

    async def mark_expense_paid(
        self, expense_uid: str, payment_date: date | None = None
    ) -> Result[ExpensePure]:
        """
        Mark an expense as paid.

        Args:
            expense_uid: Expense UID
            payment_date: Payment date (defaults to today)

        Returns:
            Result containing updated ExpensePure
        """
        updates: FinanceUpdatePayload = {
            "status": ExpenseStatus.PAID.value,
            "paid_at": payment_date or date.today(),
        }
        return await self.update(expense_uid, updates)

    async def attach_receipt(self, expense_uid: str, receipt_link: str) -> Result[ExpensePure]:
        """
        Attach a receipt to an expense.

        Args:
            expense_uid: Expense UID
            receipt_link: URL or path to receipt

        Returns:
            Result containing updated ExpensePure
        """
        if not receipt_link:
            return Result.fail(
                Errors.validation(message="Receipt link required", field="receipt_link")
            )

        updates: FinanceUpdatePayload = {"receipt_link": receipt_link, "has_receipt": True}
        return await self.update(expense_uid, updates)
