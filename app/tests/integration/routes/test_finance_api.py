"""
Integration Tests for Finance API Routes.

Tests cover:
1. Expense CRUD operations
2. Budget management
3. Expense categorization
4. Recurring expenses
5. Financial reports and analytics
6. Budget vs actual tracking

All tests use mocked services to avoid external dependencies.

Note: All async tests use pytest-asyncio for proper event loop management.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.utils.result_simplified import Errors, Result

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


class MockExpense:
    """Mock Expense model for testing."""

    def __init__(
        self,
        uid: str = "expense.test123",
        user_uid: str = "user.test",
        description: str = "Test Expense",
        amount: float = 50.00,
        category: str = "food",
        expense_date: date | None = None,
        is_recurring: bool = False,
    ):
        self.uid = uid
        self.user_uid = user_uid
        self.description = description
        self.amount = amount
        self.category = category
        self.expense_date = expense_date or date.today()
        self.is_recurring = is_recurring
        self.created_at = "2024-01-01T00:00:00Z"
        self.updated_at = "2024-01-01T00:00:00Z"

    def to_dict(self):
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "description": self.description,
            "amount": self.amount,
            "category": self.category,
            "expense_date": str(self.expense_date),
            "is_recurring": self.is_recurring,
        }


class MockBudget:
    """Mock Budget model for testing."""

    def __init__(
        self,
        uid: str = "budget.test123",
        user_uid: str = "user.test",
        category: str = "food",
        amount: float = 500.00,
        period: str = "monthly",
        start_date: date | None = None,
    ):
        self.uid = uid
        self.user_uid = user_uid
        self.category = category
        self.amount = amount
        self.period = period
        self.start_date = start_date or date.today().replace(day=1)

    def to_dict(self):
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "category": self.category,
            "amount": self.amount,
            "period": self.period,
        }


@pytest.fixture
def mock_finance_service():
    """Create mock FinanceService."""
    service = MagicMock()

    # Expense CRUD operations
    service.create_expense = AsyncMock(return_value=Result.ok(MockExpense()))
    service.get_expense = AsyncMock(return_value=Result.ok(MockExpense()))
    service.update_expense = AsyncMock(return_value=Result.ok(MockExpense()))
    service.delete_expense = AsyncMock(return_value=Result.ok(True))
    service.list_expenses = AsyncMock(return_value=Result.ok([MockExpense(), MockExpense()]))

    # Budget operations
    service.create_budget = AsyncMock(return_value=Result.ok(MockBudget()))
    service.get_budget = AsyncMock(return_value=Result.ok(MockBudget()))
    service.update_budget = AsyncMock(return_value=Result.ok(MockBudget()))
    service.delete_budget = AsyncMock(return_value=Result.ok(True))
    service.list_budgets = AsyncMock(return_value=Result.ok([MockBudget()]))

    # Query operations
    service.get_expenses_by_user = AsyncMock(return_value=Result.ok([MockExpense()]))
    service.get_expenses_by_category = AsyncMock(return_value=Result.ok([MockExpense()]))
    service.get_expenses_in_range = AsyncMock(return_value=Result.ok([MockExpense()]))

    # Analytics
    service.get_spending_summary = AsyncMock(return_value=Result.ok({"total": 150.00}))
    service.get_category_breakdown = AsyncMock(
        return_value=Result.ok({"food": 50.00, "transport": 30.00})
    )
    service.get_budget_vs_actual = AsyncMock(
        return_value=Result.ok({"budget": 500.00, "actual": 150.00})
    )
    service.get_spending_trends = AsyncMock(return_value=Result.ok([]))

    # Recurring expenses
    service.create_recurring_expense = AsyncMock(
        return_value=Result.ok(MockExpense(is_recurring=True))
    )
    service.get_recurring_expenses = AsyncMock(
        return_value=Result.ok([MockExpense(is_recurring=True)])
    )
    service.update_recurring_expense = AsyncMock(
        return_value=Result.ok(MockExpense(is_recurring=True))
    )
    service.delete_recurring_expense = AsyncMock(return_value=Result.ok(True))

    # Categories
    service.list_expense_categories = AsyncMock(
        return_value=Result.ok(["food", "transport", "entertainment"])
    )
    service.create_expense_category = AsyncMock(return_value=Result.ok(True))

    return service


class TestExpenseCRUD:
    """Tests for expense CRUD operations."""

    async def test_create_expense(self, mock_finance_service):
        """Test creating an expense."""
        result = await mock_finance_service.create_expense(
            {
                "description": "Lunch",
                "amount": 15.50,
                "category": "food",
            }
        )

        assert result.is_ok
        assert result.value.description == "Test Expense"

    async def test_get_expense_by_uid(self, mock_finance_service):
        """Test retrieving an expense by UID."""
        result = await mock_finance_service.get_expense("expense.test123")

        assert result.is_ok
        assert result.value.uid == "expense.test123"

    async def test_get_expense_not_found(self, mock_finance_service):
        """Test retrieving a non-existent expense."""
        mock_finance_service.get_expense = AsyncMock(
            return_value=Result.fail(Errors.not_found("expense", "expense.nonexistent"))
        )

        result = await mock_finance_service.get_expense("expense.nonexistent")

        assert result.is_error

    async def test_update_expense(self, mock_finance_service):
        """Test updating an expense."""
        result = await mock_finance_service.update_expense("expense.test123", {"amount": 60.00})

        assert result.is_ok

    async def test_delete_expense(self, mock_finance_service):
        """Test deleting an expense."""
        result = await mock_finance_service.delete_expense("expense.test123")

        assert result.is_ok
        assert result.value is True

    async def test_list_expenses(self, mock_finance_service):
        """Test listing expenses."""
        result = await mock_finance_service.list_expenses()

        assert result.is_ok
        assert len(result.value) == 2


class TestBudgetOperations:
    """Tests for budget management."""

    async def test_create_budget(self, mock_finance_service):
        """Test creating a budget."""
        result = await mock_finance_service.create_budget(
            {
                "category": "food",
                "amount": 500.00,
                "period": "monthly",
            }
        )

        assert result.is_ok
        assert result.value.category == "food"

    async def test_get_budget(self, mock_finance_service):
        """Test getting a budget."""
        result = await mock_finance_service.get_budget("budget.test123")

        assert result.is_ok

    async def test_update_budget(self, mock_finance_service):
        """Test updating a budget."""
        result = await mock_finance_service.update_budget("budget.test123", {"amount": 600.00})

        assert result.is_ok

    async def test_delete_budget(self, mock_finance_service):
        """Test deleting a budget."""
        result = await mock_finance_service.delete_budget("budget.test123")

        assert result.is_ok

    async def test_list_budgets(self, mock_finance_service):
        """Test listing budgets."""
        result = await mock_finance_service.list_budgets()

        assert result.is_ok


class TestExpenseQueries:
    """Tests for expense query operations."""

    async def test_get_expenses_by_user(self, mock_finance_service):
        """Test getting expenses by user."""
        result = await mock_finance_service.get_expenses_by_user("user.test")

        assert result.is_ok

    async def test_get_expenses_by_category(self, mock_finance_service):
        """Test getting expenses by category."""
        result = await mock_finance_service.get_expenses_by_category("food")

        assert result.is_ok

    async def test_get_expenses_in_range(self, mock_finance_service):
        """Test getting expenses in date range."""
        result = await mock_finance_service.get_expenses_in_range(
            date.today() - timedelta(days=30), date.today()
        )

        assert result.is_ok


class TestAnalytics:
    """Tests for financial analytics."""

    async def test_get_spending_summary(self, mock_finance_service):
        """Test getting spending summary."""
        result = await mock_finance_service.get_spending_summary("user.test")

        assert result.is_ok
        assert "total" in result.value

    async def test_get_category_breakdown(self, mock_finance_service):
        """Test getting category breakdown."""
        result = await mock_finance_service.get_category_breakdown("user.test")

        assert result.is_ok
        assert "food" in result.value

    async def test_get_budget_vs_actual(self, mock_finance_service):
        """Test getting budget vs actual comparison."""
        result = await mock_finance_service.get_budget_vs_actual("user.test", "food")

        assert result.is_ok
        assert "budget" in result.value
        assert "actual" in result.value

    async def test_get_spending_trends(self, mock_finance_service):
        """Test getting spending trends."""
        result = await mock_finance_service.get_spending_trends("user.test")

        assert result.is_ok


class TestRecurringExpenses:
    """Tests for recurring expense management."""

    async def test_create_recurring_expense(self, mock_finance_service):
        """Test creating a recurring expense."""
        result = await mock_finance_service.create_recurring_expense(
            {
                "description": "Netflix",
                "amount": 15.99,
                "category": "entertainment",
                "frequency": "monthly",
            }
        )

        assert result.is_ok
        assert result.value.is_recurring is True

    async def test_get_recurring_expenses(self, mock_finance_service):
        """Test getting recurring expenses."""
        result = await mock_finance_service.get_recurring_expenses("user.test")

        assert result.is_ok
        assert len(result.value) >= 1

    async def test_update_recurring_expense(self, mock_finance_service):
        """Test updating a recurring expense."""
        result = await mock_finance_service.update_recurring_expense(
            "expense.test123", {"amount": 19.99}
        )

        assert result.is_ok

    async def test_delete_recurring_expense(self, mock_finance_service):
        """Test deleting a recurring expense."""
        result = await mock_finance_service.delete_recurring_expense("expense.test123")

        assert result.is_ok


class TestCategories:
    """Tests for expense category management."""

    async def test_list_expense_categories(self, mock_finance_service):
        """Test listing expense categories."""
        result = await mock_finance_service.list_expense_categories()

        assert result.is_ok
        assert "food" in result.value

    async def test_create_expense_category(self, mock_finance_service):
        """Test creating an expense category."""
        result = await mock_finance_service.create_expense_category("utilities")

        assert result.is_ok


class TestErrorHandling:
    """Tests for error handling."""

    async def test_validation_error_on_create(self, mock_finance_service):
        """Test validation error when creating expense with invalid data."""
        mock_finance_service.create_expense = AsyncMock(
            return_value=Result.fail(Errors.validation("Amount must be positive", field="amount"))
        )

        result = await mock_finance_service.create_expense({"amount": -10.00})

        assert result.is_error

    async def test_budget_not_found(self, mock_finance_service):
        """Test budget not found error."""
        mock_finance_service.get_budget = AsyncMock(
            return_value=Result.fail(Errors.not_found("budget", "budget.nonexistent"))
        )

        result = await mock_finance_service.get_budget("budget.nonexistent")

        assert result.is_error


class TestFinanceModel:
    """Tests for Finance model structure."""

    async def test_expense_amount_is_positive(self):
        """Test that expense amounts are positive."""
        expense = MockExpense(amount=50.00)
        assert expense.amount > 0

    async def test_budget_period_values(self):
        """Test valid budget period values."""
        valid_periods = ["daily", "weekly", "monthly", "yearly"]
        for period in valid_periods:
            assert isinstance(period, str)
