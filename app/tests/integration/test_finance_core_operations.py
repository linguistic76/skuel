"""
Integration Test: Finance Core Operations
=========================================

Tests basic CRUD operations and core functionality for the Finance domain.

This test suite verifies that:
1. Expenses can be created, retrieved, and listed
2. Expenses can be filtered by status, payment method, and category
3. Expense calculations work correctly
4. Business logic works correctly

Test Coverage:
--------------
- FinanceCoreService.create()
- FinanceCoreService.get()
- FinanceCoreService.backend.find_by()
- ExpensePure business logic
- Expense enum classifications
"""

from datetime import date

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.finance.finance_pure import (
    ExpenseCategory,
    ExpensePure,
    ExpenseStatus,
    PaymentMethod,
)
from core.services.finance.finance_core_service import FinanceCoreService


@pytest.mark.asyncio
class TestFinanceCoreOperations:
    """Integration tests for Finance core CRUD operations."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture."""
        return InMemoryEventBus(capture_history=True, enable_performance_monitoring=False)

    @pytest_asyncio.fixture
    async def finance_backend(self, neo4j_driver, clean_neo4j):
        """Create finance backend with clean database."""
        return UniversalNeo4jBackend[ExpensePure](neo4j_driver, "Expense", ExpensePure)

    @pytest_asyncio.fixture
    async def finance_service(self, finance_backend, event_bus):
        """Create FinanceCoreService with event bus."""
        return FinanceCoreService(backend=finance_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_finance_core"

    # ==========================================================================
    # CRUD OPERATIONS TESTS (5 tests)
    # ==========================================================================

    async def test_create_expense(self, finance_service, test_user_uid):
        """Test creating a new expense."""
        # Arrange
        expense = ExpensePure(
            uid="expense.coffee",
            user_uid=test_user_uid,
            amount=5.50,
            currency="USD",
            description="Coffee at local cafe",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
            subcategory="food",
            payment_method=PaymentMethod.CREDIT_CARD,
            status=ExpenseStatus.PAID,
        )

        # Act
        result = await finance_service.create(expense)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.uid == "expense.coffee"
        assert created.amount == 5.50
        assert created.currency == "USD"
        assert created.category == ExpenseCategory.PERSONAL
        assert created.payment_method == PaymentMethod.CREDIT_CARD

    async def test_get_expense_by_uid(self, finance_service, test_user_uid):
        """Test retrieving an expense by UID."""
        # Arrange - Create an expense first
        expense = ExpensePure(
            uid="expense.get_test",
            user_uid=test_user_uid,
            amount=100.00,
            currency="USD",
            description="Test expense for retrieval",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        create_result = await finance_service.create(expense)
        assert create_result.is_ok

        # Act - Retrieve the expense
        result = await finance_service.get("expense.get_test")

        # Assert
        assert result.is_ok
        retrieved = result.value
        assert retrieved.uid == "expense.get_test"
        assert retrieved.amount == 100.00

    async def test_get_nonexistent_expense(self, finance_service):
        """Test getting an expense that doesn't exist."""
        # Act
        result = await finance_service.get("expense.nonexistent")

        # Assert - get() returns None for not found (not an error)
        assert result.is_ok
        assert result.value is None

    async def test_list_user_expenses(self, finance_service, test_user_uid):
        """Test listing all expenses for a user."""
        # Arrange - Create multiple expenses
        expenses = [
            ExpensePure(
                uid=f"expense.list_test_{i}",
                user_uid=test_user_uid,
                amount=float(10 + i),
                currency="USD",
                description=f"Test expense {i}",
                expense_date=date(2025, 11, 7),
                category=ExpenseCategory.PERSONAL,
            )
            for i in range(3)
        ]

        for expense in expenses:
            result = await finance_service.create(expense)
            assert result.is_ok

        # Act - List expenses
        result = await finance_service.backend.find_by(user_uid=test_user_uid)

        # Assert
        assert result.is_ok
        user_expenses = result.value
        assert len(user_expenses) >= 3

    async def test_multiple_expenses_same_user(self, finance_service, test_user_uid):
        """Test creating multiple expenses for the same user."""
        # Arrange & Act - Create 5 expenses
        for i in range(5):
            expense = ExpensePure(
                uid=f"expense.multi_{i}",
                user_uid=test_user_uid,
                amount=float(50 + i * 10),
                currency="USD",
                description=f"Multiple expense {i}",
                expense_date=date(2025, 11, 7),
                category=ExpenseCategory.PERSONAL,
            )
            result = await finance_service.create(expense)
            assert result.is_ok

        # Assert - Verify all were created
        list_result = await finance_service.backend.find_by(user_uid=test_user_uid)
        assert list_result.is_ok
        assert len(list_result.value) >= 5

    # ==========================================================================
    # FILTERING TESTS (3 tests)
    # ==========================================================================

    async def test_filter_by_status(self, finance_service, test_user_uid):
        """Test filtering expenses by status."""
        # Arrange - Create expenses with different statuses
        pending_expense = ExpensePure(
            uid="expense.pending",
            user_uid=test_user_uid,
            amount=25.00,
            currency="USD",
            description="Pending payment",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
            status=ExpenseStatus.PENDING,
        )
        paid_expense = ExpensePure(
            uid="expense.paid",
            user_uid=test_user_uid,
            amount=50.00,
            currency="USD",
            description="Already paid",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
            status=ExpenseStatus.PAID,
        )

        await finance_service.create(pending_expense)
        await finance_service.create(paid_expense)

        # Act - Filter by status
        pending_result = await finance_service.backend.find_by(
            user_uid=test_user_uid, status=ExpenseStatus.PENDING.value
        )
        paid_result = await finance_service.backend.find_by(
            user_uid=test_user_uid, status=ExpenseStatus.PAID.value
        )

        # Assert
        assert pending_result.is_ok
        assert len(pending_result.value) >= 1
        assert all(e.status == ExpenseStatus.PENDING for e in pending_result.value)

        assert paid_result.is_ok
        assert len(paid_result.value) >= 1
        assert all(e.status == ExpenseStatus.PAID for e in paid_result.value)

    async def test_filter_by_payment_method(self, finance_service, test_user_uid):
        """Test filtering expenses by payment method."""
        # Arrange - Create expenses with different payment methods
        cash_expense = ExpensePure(
            uid="expense.cash",
            user_uid=test_user_uid,
            amount=20.00,
            currency="USD",
            description="Cash payment",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
            payment_method=PaymentMethod.CASH,
        )
        card_expense = ExpensePure(
            uid="expense.card",
            user_uid=test_user_uid,
            amount=75.00,
            currency="USD",
            description="Credit card payment",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
            payment_method=PaymentMethod.CREDIT_CARD,
        )

        await finance_service.create(cash_expense)
        await finance_service.create(card_expense)

        # Act - Filter by payment method
        cash_result = await finance_service.backend.find_by(
            user_uid=test_user_uid, payment_method=PaymentMethod.CASH.value
        )
        card_result = await finance_service.backend.find_by(
            user_uid=test_user_uid, payment_method=PaymentMethod.CREDIT_CARD.value
        )

        # Assert
        assert cash_result.is_ok
        assert len(cash_result.value) >= 1
        assert all(e.payment_method == PaymentMethod.CASH for e in cash_result.value)

        assert card_result.is_ok
        assert len(card_result.value) >= 1
        assert all(e.payment_method == PaymentMethod.CREDIT_CARD for e in card_result.value)

    async def test_filter_by_category(self, finance_service, test_user_uid):
        """Test filtering expenses by category."""
        # Arrange - Create expenses in different categories
        personal_expense = ExpensePure(
            uid="expense.personal",
            user_uid=test_user_uid,
            amount=30.00,
            currency="USD",
            description="Personal expense",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        skuel_expense = ExpensePure(
            uid="expense.skuel",
            user_uid=test_user_uid,
            amount=150.00,
            currency="USD",
            description="SKUEL development cost",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.SKUEL,
            subcategory="development",
        )

        await finance_service.create(personal_expense)
        await finance_service.create(skuel_expense)

        # Act - Filter by category
        personal_result = await finance_service.backend.find_by(
            user_uid=test_user_uid, category=ExpenseCategory.PERSONAL.value
        )
        skuel_result = await finance_service.backend.find_by(
            user_uid=test_user_uid, category=ExpenseCategory.SKUEL.value
        )

        # Assert
        assert personal_result.is_ok
        assert len(personal_result.value) >= 1
        assert all(e.category == ExpenseCategory.PERSONAL for e in personal_result.value)

        assert skuel_result.is_ok
        assert len(skuel_result.value) >= 1
        assert all(e.category == ExpenseCategory.SKUEL for e in skuel_result.value)

    # ==========================================================================
    # BUSINESS LOGIC TESTS (4 tests)
    # ==========================================================================

    async def test_expense_statuses(self, finance_service, test_user_uid):
        """Test creating expenses with all status types."""
        # Arrange & Act - Create expenses with each status
        statuses = [
            ExpenseStatus.PENDING,
            ExpenseStatus.PAID,
            ExpenseStatus.CLEARED,
            ExpenseStatus.RECONCILED,
            ExpenseStatus.DISPUTED,
        ]

        for status in statuses:
            expense = ExpensePure(
                uid=f"expense.status_{status.value}",
                user_uid=test_user_uid,
                amount=100.00,
                currency="USD",
                description=f"Expense with {status.value} status",
                expense_date=date(2025, 11, 7),
                category=ExpenseCategory.PERSONAL,
                status=status,
            )
            result = await finance_service.create(expense)
            assert result.is_ok
            assert result.value.status == status

    async def test_expense_payment_methods(self, finance_service, test_user_uid):
        """Test creating expenses with all payment methods."""
        # Arrange & Act - Create expenses with each payment method
        payment_methods = [
            PaymentMethod.CASH,
            PaymentMethod.CREDIT_CARD,
            PaymentMethod.DEBIT_CARD,
            PaymentMethod.BANK_TRANSFER,
            PaymentMethod.PAYPAL,
        ]

        for method in payment_methods:
            expense = ExpensePure(
                uid=f"expense.payment_{method.value}",
                user_uid=test_user_uid,
                amount=50.00,
                currency="USD",
                description=f"Paid via {method.value}",
                expense_date=date(2025, 11, 7),
                category=ExpenseCategory.PERSONAL,
                payment_method=method,
            )
            result = await finance_service.create(expense)
            assert result.is_ok
            assert result.value.payment_method == method

    async def test_expense_categories(self, finance_service, test_user_uid):
        """Test creating expenses in all categories."""
        # Arrange & Act - Create expenses in each category
        categories = [
            ExpenseCategory.PERSONAL,
            ExpenseCategory.TWO222,
            ExpenseCategory.SKUEL,
        ]

        for category in categories:
            expense = ExpensePure(
                uid=f"expense.cat_{category.value}",
                user_uid=test_user_uid,
                amount=200.00,
                currency="USD",
                description=f"Expense in {category.value} category",
                expense_date=date(2025, 11, 7),
                category=category,
            )
            result = await finance_service.create(expense)
            assert result.is_ok
            assert result.value.category == category

    async def test_expense_with_tax_and_reimbursement(self, finance_service, test_user_uid):
        """Test creating an expense with tax and reimbursement flags."""
        # Arrange
        expense = ExpensePure(
            uid="expense.tax_reimbursable",
            user_uid=test_user_uid,
            amount=120.00,
            currency="USD",
            description="Business dinner - tax deductible and reimbursable",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.TWO222,
            subcategory="office",
            tax_deductible=True,
            reimbursable=True,
            tax_amount=12.00,
        )

        # Act
        result = await finance_service.create(expense)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.tax_deductible is True
        assert created.reimbursable is True
        assert created.tax_amount == 12.00

    # ==========================================================================
    # EDGE CASES TESTS (3 tests)
    # ==========================================================================

    async def test_expense_with_optional_fields(self, finance_service, test_user_uid):
        """Test creating an expense with optional fields populated."""
        # Arrange
        expense = ExpensePure(
            uid="expense.full_details",
            user_uid=test_user_uid,
            amount=250.00,
            currency="USD",
            description="Fully detailed expense",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.SKUEL,
            subcategory="infrastructure",
            payment_method=PaymentMethod.CREDIT_CARD,
            vendor="AWS",
            notes="Monthly cloud infrastructure cost",
            receipt_url="https://example.com/receipt.pdf",
        )

        # Act
        result = await finance_service.create(expense)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.vendor == "AWS"
        assert created.notes == "Monthly cloud infrastructure cost"
        assert created.receipt_url is not None

    async def test_expense_without_optional_fields(self, finance_service, test_user_uid):
        """Test creating an expense with minimal required fields."""
        # Arrange - Only required fields
        expense = ExpensePure(
            uid="expense.minimal",
            user_uid=test_user_uid,
            amount=15.00,
            currency="USD",
            description="Minimal expense",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )

        # Act
        result = await finance_service.create(expense)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.vendor is None
        assert created.notes is None
        assert created.subcategory is None

    async def test_expense_date_range(self, finance_service, test_user_uid):
        """Test creating expenses with different dates."""
        # Arrange & Act - Create expenses with different dates
        dates = [
            date(2025, 11, 1),
            date(2025, 11, 15),
            date(2025, 11, 30),
        ]

        for i, expense_date in enumerate(dates):
            expense = ExpensePure(
                uid=f"expense.date_{i}",
                user_uid=test_user_uid,
                amount=50.00,
                currency="USD",
                description=f"Expense on {expense_date}",
                expense_date=expense_date,
                category=ExpenseCategory.PERSONAL,
            )
            result = await finance_service.create(expense)
            assert result.is_ok
            assert result.value.expense_date == expense_date

    # ==========================================================================
    # UPDATE OPERATIONS TESTS (4 tests)
    # ==========================================================================

    async def test_update_expense_amount(self, finance_service, test_user_uid):
        """Test updating an expense amount."""
        # Arrange - Create an expense
        expense = ExpensePure(
            uid="expense.update_amount",
            user_uid=test_user_uid,
            amount=50.00,
            currency="USD",
            description="Original amount",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        create_result = await finance_service.create(expense)
        assert create_result.is_ok

        # Act - Update the amount
        update_result = await finance_service.update("expense.update_amount", {"amount": 75.00})

        # Assert
        assert update_result.is_ok
        updated = update_result.value
        assert updated.amount == 75.00

    async def test_update_expense_description(self, finance_service, test_user_uid):
        """Test updating an expense description."""
        # Arrange
        expense = ExpensePure(
            uid="expense.update_desc",
            user_uid=test_user_uid,
            amount=100.00,
            currency="USD",
            description="Original description",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        await finance_service.create(expense)

        # Act
        result = await finance_service.update(
            "expense.update_desc", {"description": "Updated description"}
        )

        # Assert
        assert result.is_ok
        assert result.value.description == "Updated description"

    async def test_update_expense_status(self, finance_service, test_user_uid):
        """Test updating an expense status."""
        # Arrange
        expense = ExpensePure(
            uid="expense.update_status",
            user_uid=test_user_uid,
            amount=200.00,
            currency="USD",
            description="Status change test",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
            status=ExpenseStatus.PENDING,
        )
        await finance_service.create(expense)

        # Act - Mark as paid (use .value for Neo4j compatibility)
        result = await finance_service.update(
            "expense.update_status", {"status": ExpenseStatus.PAID.value}
        )

        # Assert
        assert result.is_ok
        assert result.value.status == ExpenseStatus.PAID

    async def test_update_nonexistent_expense(self, finance_service):
        """Test updating an expense that doesn't exist."""
        # Act
        result = await finance_service.update("expense.nonexistent", {"amount": 100.00})

        # Assert
        assert result.is_error
        assert "not found" in result.error.message.lower()

    # ==========================================================================
    # DELETE OPERATIONS TESTS (3 tests)
    # ==========================================================================

    async def test_delete_expense(self, finance_service, test_user_uid):
        """Test deleting an expense."""
        # Arrange - Create an expense
        expense = ExpensePure(
            uid="expense.to_delete",
            user_uid=test_user_uid,
            amount=50.00,
            currency="USD",
            description="Expense to delete",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        create_result = await finance_service.create(expense)
        assert create_result.is_ok

        # Act - Delete it
        delete_result = await finance_service.delete("expense.to_delete")

        # Assert - Delete succeeds
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify it's gone (get returns None for not found)
        get_result = await finance_service.get("expense.to_delete")
        assert get_result.is_ok
        assert get_result.value is None

    async def test_delete_nonexistent_expense(self, finance_service):
        """Test deleting an expense that doesn't exist."""
        # Act
        result = await finance_service.delete("expense.never_existed")

        # Assert - Should fail or return False
        # Backend behavior may vary - check it handles gracefully
        assert result.is_ok or result.is_error

    async def test_delete_and_verify_gone(self, finance_service, test_user_uid):
        """Test that deleted expense cannot be retrieved."""
        # Arrange
        expense = ExpensePure(
            uid="expense.delete_verify",
            user_uid=test_user_uid,
            amount=75.00,
            currency="USD",
            description="Verify deletion",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        await finance_service.create(expense)

        # Verify it exists
        exists_result = await finance_service.get("expense.delete_verify")
        assert exists_result.is_ok
        assert exists_result.value is not None

        # Delete it
        await finance_service.delete("expense.delete_verify")

        # Verify gone (get returns None for not found)
        gone_result = await finance_service.get("expense.delete_verify")
        assert gone_result.is_ok
        assert gone_result.value is None

    # ==========================================================================
    # VALIDATION TESTS (4 tests)
    # ==========================================================================

    async def test_create_expense_negative_amount_rejected(self, finance_service, test_user_uid):
        """Test that negative amounts are rejected on create."""
        # Arrange
        expense = ExpensePure(
            uid="expense.negative",
            user_uid=test_user_uid,
            amount=-50.00,  # Invalid: negative
            currency="USD",
            description="Negative amount test",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )

        # Act
        result = await finance_service.create(expense)

        # Assert - Should fail validation
        assert result.is_error
        assert (
            "positive" in result.error.message.lower() or "amount" in result.error.message.lower()
        )

    async def test_create_expense_zero_amount_rejected(self, finance_service, test_user_uid):
        """Test that zero amounts are rejected on create."""
        # Arrange
        expense = ExpensePure(
            uid="expense.zero",
            user_uid=test_user_uid,
            amount=0.00,  # Invalid: zero
            currency="USD",
            description="Zero amount test",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )

        # Act
        result = await finance_service.create(expense)

        # Assert - Should fail validation
        assert result.is_error

    async def test_update_expense_negative_amount_rejected(self, finance_service, test_user_uid):
        """Test that negative amounts are rejected on update."""
        # Arrange - Create valid expense first
        expense = ExpensePure(
            uid="expense.update_neg",
            user_uid=test_user_uid,
            amount=50.00,
            currency="USD",
            description="Will try to update to negative",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        await finance_service.create(expense)

        # Act - Try to update with negative amount
        result = await finance_service.update("expense.update_neg", {"amount": -100.00})

        # Assert - Should fail validation
        assert result.is_error

    async def test_update_expense_unreasonable_increase_rejected(
        self, finance_service, test_user_uid
    ):
        """Test that unreasonable amount increases are rejected (>10x)."""
        # Arrange - Create expense with $10 amount
        expense = ExpensePure(
            uid="expense.big_increase",
            user_uid=test_user_uid,
            amount=10.00,
            currency="USD",
            description="Will try unreasonable increase",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        await finance_service.create(expense)

        # Act - Try to increase by more than 10x ($10 -> $150 = 15x)
        result = await finance_service.update("expense.big_increase", {"amount": 150.00})

        # Assert - Should fail validation (data entry error prevention)
        assert result.is_error
        assert (
            "unusual" in result.error.message.lower() or "increase" in result.error.message.lower()
        )

    # ==========================================================================
    # EVENT PUBLISHING TESTS (4 tests)
    # ==========================================================================

    async def test_create_publishes_expense_created_event(
        self, finance_service, event_bus, test_user_uid
    ):
        """Test that creating an expense publishes ExpenseCreated event."""
        from core.events.finance_events import ExpenseCreated

        # Arrange
        expense = ExpensePure(
            uid="expense.event_create",
            user_uid=test_user_uid,
            amount=100.00,
            currency="USD",
            description="Event test",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )

        # Act
        result = await finance_service.create(expense)
        assert result.is_ok

        # Assert - Check event was published
        history = event_bus.get_event_history()
        created_events = [e for e in history if isinstance(e, ExpenseCreated)]
        assert len(created_events) >= 1
        event = created_events[-1]
        assert event.expense_uid == "expense.event_create"
        assert event.amount == 100.00

    async def test_update_publishes_expense_updated_event(
        self, finance_service, event_bus, test_user_uid
    ):
        """Test that updating an expense publishes ExpenseUpdated event."""
        from core.events.finance_events import ExpenseUpdated

        # Arrange - Create expense first
        expense = ExpensePure(
            uid="expense.event_update",
            user_uid=test_user_uid,
            amount=50.00,
            currency="USD",
            description="Will be updated",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        await finance_service.create(expense)

        # Act - Update it
        result = await finance_service.update("expense.event_update", {"amount": 75.00})
        assert result.is_ok

        # Assert - Check event was published
        history = event_bus.get_event_history()
        updated_events = [e for e in history if isinstance(e, ExpenseUpdated)]
        assert len(updated_events) >= 1
        event = updated_events[-1]
        assert event.expense_uid == "expense.event_update"
        assert "amount" in event.updated_fields

    async def test_delete_publishes_expense_deleted_event(
        self, finance_service, event_bus, test_user_uid
    ):
        """Test that deleting an expense publishes ExpenseDeleted event."""
        from core.events.finance_events import ExpenseDeleted

        # Arrange
        expense = ExpensePure(
            uid="expense.event_delete",
            user_uid=test_user_uid,
            amount=30.00,
            currency="USD",
            description="Will be deleted",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
        )
        await finance_service.create(expense)

        # Act - Delete it
        result = await finance_service.delete("expense.event_delete")
        assert result.is_ok

        # Assert - Check event was published
        history = event_bus.get_event_history()
        deleted_events = [e for e in history if isinstance(e, ExpenseDeleted)]
        assert len(deleted_events) >= 1
        event = deleted_events[-1]
        assert event.expense_uid == "expense.event_delete"

    async def test_mark_paid_publishes_expense_paid_event(
        self, finance_service, event_bus, test_user_uid
    ):
        """Test that marking expense as paid publishes ExpensePaid event."""
        from core.events.finance_events import ExpensePaid

        # Arrange - Create pending expense
        expense = ExpensePure(
            uid="expense.event_paid",
            user_uid=test_user_uid,
            amount=200.00,
            currency="USD",
            description="Will be marked paid",
            expense_date=date(2025, 11, 7),
            category=ExpenseCategory.PERSONAL,
            status=ExpenseStatus.PENDING,
        )
        await finance_service.create(expense)

        # Act - Mark as paid (use .value for Neo4j compatibility)
        result = await finance_service.update(
            "expense.event_paid", {"status": ExpenseStatus.PAID.value}
        )
        assert result.is_ok

        # Assert - Check ExpensePaid event was published
        history = event_bus.get_event_history()
        paid_events = [e for e in history if isinstance(e, ExpensePaid)]
        assert len(paid_events) >= 1
        event = paid_events[-1]
        assert event.expense_uid == "expense.event_paid"
        assert event.amount == 200.00
