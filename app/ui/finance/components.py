"""Finance UI component definitions using FormGenerator and CardGenerator."""

from typing import Any

from fasthtml.common import Div, Span

from core.models.finance.finance_request import BudgetCreateRequest, ExpenseCreateRequest
from ui.buttons import ButtonLink, ButtonT
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.patterns.form_generator import FormGenerator


class FinanceUIComponents:
    """
    Finance UI component definitions using FormGenerator and CardGenerator.

    These are reusable components for forms and cards.
    """

    @staticmethod
    def render_create_expense_form() -> Any:
        """Create expense form using FormGenerator."""
        return FormGenerator.from_model(
            ExpenseCreateRequest,
            action="/api/expenses",
            method="POST",
            include_fields=[
                "amount",
                "description",
                "expense_date",
                "category",
                "subcategory",
                "payment_method",
                "vendor",
                "tax_deductible",
            ],
            form_attrs={"id": "expense-create-form", "cls": "space-y-4"},
            submit_label="Add Expense",
        )

    @staticmethod
    def render_create_budget_form() -> Any:
        """Create budget form using FormGenerator."""
        return FormGenerator.from_model(
            BudgetCreateRequest,
            action="/api/budgets",
            method="POST",
            include_fields=[
                "name",
                "period",
                "amount_limit",
                "start_date",
                "categories",
                "alert_threshold",
            ],
            form_attrs={"id": "budget-create-form", "cls": "space-y-4"},
            submit_label="Create Budget",
        )

    @staticmethod
    def render_expense_card(expense, compact=False) -> Any:
        """Individual expense card using CardGenerator."""
        uid = expense.get("uid", "") if isinstance(expense, dict) else expense.uid

        def render_amount(value) -> Any:
            return Span(f"${value:,.2f}", cls="text-2xl font-bold text-green-600")

        display_fields = (
            ["amount", "description", "category"]
            if compact
            else [
                "amount",
                "description",
                "expense_date",
                "category",
                "subcategory",
                "payment_method",
                "vendor",
                "status",
            ]
        )

        action_buttons = Div(
            ButtonLink(
                "View",
                href=f"/finance/expenses/{uid}",
                variant=ButtonT.outline,
                size=Size.sm,
            ),
            ButtonLink(
                "Edit",
                href=f"/finance/expenses/{uid}/edit",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            cls="flex gap-2",
        )

        return CardGenerator.from_dataclass(
            expense,
            display_fields=display_fields,
            field_renderers={"amount": render_amount},
            actions=action_buttons,
            card_attrs={"id": f"expense-{uid}", "cls": "border border-border p-4"},
        )

    @staticmethod
    def render_budget_card(budget, compact=False) -> Any:
        """Individual budget card using CardGenerator."""
        uid = budget.get("uid", "") if isinstance(budget, dict) else budget.uid

        def render_amount_limit(value) -> Any:
            return Span(f"${value:,.2f} limit", cls="text-xl font-semibold text-blue-600")

        display_fields = (
            ["name", "amount_limit", "period"]
            if compact
            else [
                "name",
                "amount_limit",
                "period",
                "start_date",
                "end_date",
                "categories",
                "alert_threshold",
            ]
        )

        action_buttons = Div(
            ButtonLink(
                "View",
                href=f"/finance/budgets/{uid}",
                variant=ButtonT.outline,
                size=Size.sm,
            ),
            ButtonLink(
                "Edit",
                href=f"/finance/budgets/{uid}/edit",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            cls="flex gap-2",
        )

        return CardGenerator.from_dataclass(
            budget,
            display_fields=display_fields,
            field_renderers={"amount_limit": render_amount_limit},
            actions=action_buttons,
            card_attrs={"id": f"budget-{uid}", "cls": "border border-border p-4"},
        )
