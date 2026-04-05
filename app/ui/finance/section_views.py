"""Finance Hub section views.

View components for each section of the Finance Hub:
- Dashboard (overview)
- Expenses (expense tracking)
- Budgets (budget management)
- Reports (financial reports)
- Analytics (spending patterns, health)
"""

from datetime import date

from fasthtml.common import (
    H3,
    Button,
    Div,
    Form,
    Input,
    Option,
    P,
    Select,
    Span,
    Td,
)

from ui.buttons import ButtonLink, ButtonT
from ui.data import TableFromDicts, TableT
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.stats_grid import StatItem, StatsGrid


class FinanceSectionViews:
    """View components for Finance Hub sections."""

    # =========================================================================
    # DASHBOARD VIEW
    # =========================================================================

    @staticmethod
    def render_dashboard(
        total_spent: float = 0.0,
        total_budget: float = 0.0,
        budget_utilization: float = 0.0,
        health_status: str = "Good",
        recent_expenses: list[dict] | None = None,
        budget_alerts: list[dict] | None = None,
    ) -> Div:
        """Dashboard overview with stats cards and quick actions.

        Args:
            total_spent: Total spent this month
            total_budget: Total budget for the month
            budget_utilization: Percentage of budget used (0-100)
            health_status: Financial health status string
            recent_expenses: List of recent expense dicts
            budget_alerts: List of budget alert dicts
        """
        recent_expenses = recent_expenses or []
        budget_alerts = budget_alerts or []

        # Stats cards
        stats_section = StatsGrid(
            [
                StatItem(label="Spent This Month", value=f"${total_spent:,.2f}", color="info"),
                StatItem(label="Total Budget", value=f"${total_budget:,.2f}", color="success"),
                StatItem(label="Budget Used", value=f"{budget_utilization:.0f}%", color="warning"),
                StatItem(label="Health Status", value=health_status, color="primary"),
            ],
            cls="mb-8",
        )

        # Quick actions
        quick_actions = Div(
            H3("Quick Actions", cls="text-lg font-semibold mb-3"),
            Div(
                ButtonLink(
                    "+ Add Expense",
                    href="/finance/expenses",
                    variant=ButtonT.primary,
                    size=Size.sm,
                ),
                ButtonLink(
                    "+ Create Budget",
                    href="/finance/budgets",
                    variant=ButtonT.success,
                    size=Size.sm,
                ),
                ButtonLink(
                    "View Reports",
                    href="/finance/reports",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                ),
                cls="flex flex-wrap gap-3",
            ),
            cls="mb-8",
        )

        # Recent expenses
        if recent_expenses:
            expense_items = [
                Div(
                    Div(
                        Span(exp.get("description", "Unknown"), cls="font-medium"),
                        Span(f" - ${exp.get('amount', 0):.2f}", cls="text-muted-foreground"),
                        cls="flex-1",
                    ),
                    Div(
                        Span(
                            exp.get("category", ""),
                            cls="text-xs px-2 py-0.5 bg-muted rounded",
                        ),
                        cls="ml-2",
                    ),
                    cls="flex items-center justify-between py-2 border-b border-border last:border-0",
                )
                for exp in recent_expenses[:5]
            ]
            recent_section = Div(
                H3("Recent Expenses", cls="text-lg font-semibold mb-3"),
                Div(*expense_items, cls="bg-background border border-border rounded-lg p-4"),
                ButtonLink(
                    "View all expenses →",
                    href="/finance/expenses",
                    variant=ButtonT.ghost,
                    size=Size.xs,
                    cls="mt-2",
                ),
                cls="mb-8",
            )
        else:
            recent_section = Div(
                H3("Recent Expenses", cls="text-lg font-semibold mb-3"),
                EmptyState(
                    title="No expenses recorded yet",
                    action_text="Add your first expense",
                    action_href="/finance/expenses",
                ),
                cls="mb-8",
            )

        # Budget alerts
        if budget_alerts:
            alert_items = [
                Div(
                    Span("⚠️" if alert.get("type") == "warning" else "🔴", cls="mr-2"),
                    Span(alert.get("message", ""), cls="text-sm"),
                    cls="py-2",
                )
                for alert in budget_alerts
            ]
            alerts_section = Div(
                H3("Budget Alerts", cls="text-lg font-semibold mb-3"),
                Div(*alert_items, cls="bg-warning/10 border border-warning/20 rounded-lg p-4"),
                cls="mb-8",
            )
        else:
            alerts_section = Div(
                H3("Budget Alerts", cls="text-lg font-semibold mb-3"),
                Div(
                    P("✓ All budgets on track", cls="text-success"),
                    cls="bg-success/10 border border-success/20 rounded-lg p-4",
                ),
                cls="mb-8",
            )

        return Div(
            PageHeader("Finance Dashboard"),
            stats_section,
            quick_actions,
            recent_section,
            alerts_section,
        )

    # =========================================================================
    # EXPENSES VIEW
    # =========================================================================

    @staticmethod
    def render_expenses_list(
        expenses: list[dict] | None = None,
        categories: list[dict] | None = None,
        total_count: int = 0,
    ) -> Div:
        """Expense list with filters and create form.

        Args:
            expenses: List of expense dicts
            categories: Available categories for filtering
            total_count: Total number of expenses
        """
        expenses = expenses or []
        categories = categories or []

        # Filter bar
        filter_bar = Div(
            H3("Filter Expenses", cls="text-lg font-semibold mb-3"),
            Form(
                Div(
                    Div(
                        Input(
                            type="date",
                            name="start_date",
                            cls="px-3 py-2 border border-border rounded-lg w-full",
                        ),
                        cls="flex-1",
                    ),
                    Span("to", cls="px-2 self-center text-muted-foreground"),
                    Div(
                        Input(
                            type="date",
                            name="end_date",
                            cls="px-3 py-2 border border-border rounded-lg w-full",
                        ),
                        cls="flex-1",
                    ),
                    Select(
                        Option("All Categories", value=""),
                        *[
                            Option(cat.get("name", ""), value=cat.get("code", ""))
                            for cat in categories
                        ],
                        name="category",
                        cls="px-3 py-2 border border-border rounded-lg",
                    ),
                    Button(
                        "Filter",
                        type="submit",
                        cls="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90",
                    ),
                    cls="flex flex-wrap gap-3 items-center",
                ),
                hx_get="/finance/expenses",
                hx_target="#expense-list",
                hx_swap="innerHTML",
            ),
            cls="bg-background border border-border rounded-lg p-4 mb-6",
        )

        # Add expense form
        add_form = Div(
            H3("Add New Expense", cls="text-lg font-semibold mb-3"),
            Form(
                Div(
                    Div(
                        Input(
                            type="number",
                            name="amount",
                            placeholder="Amount",
                            step="0.01",
                            min="0.01",
                            required=True,
                            cls="px-3 py-2 border border-border rounded-lg w-full",
                        ),
                        cls="w-32",
                    ),
                    Div(
                        Input(
                            type="text",
                            name="description",
                            placeholder="Description",
                            required=True,
                            cls="px-3 py-2 border border-border rounded-lg w-full",
                        ),
                        cls="flex-1",
                    ),
                    Div(
                        Input(
                            type="date",
                            name="expense_date",
                            value=str(date.today()),
                            required=True,
                            cls="px-3 py-2 border border-border rounded-lg w-full",
                        ),
                        cls="w-40",
                    ),
                    Select(
                        Option("Category...", value="", disabled=True, selected=True),
                        Option("Personal", value="PERSONAL"),
                        Option("House (2222)", value="2222"),
                        Option("SKUEL", value="SKUEL"),
                        name="category",
                        required=True,
                        cls="px-3 py-2 border border-border rounded-lg",
                    ),
                    Button(
                        "Add Expense",
                        type="submit",
                        cls="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90",
                    ),
                    cls="flex flex-wrap gap-3 items-center",
                ),
                hx_post="/api/expenses",
                hx_target="#expense-list",
                hx_swap="afterbegin",
            ),
            cls="bg-success/10 border border-success/20 rounded-lg p-4 mb-6",
        )

        # Expense list
        if expenses:

            def _expense_cell_render(k: str, v: object) -> Td:
                if k == "Amount":
                    return Td(v, cls="py-3 px-4 font-medium")
                if k == "Date":
                    return Td(v, cls="py-3 px-4 text-muted-foreground")
                return Td(v, cls="py-3 px-4")

            expense_body = [
                {
                    "Description": exp.get("description", ""),
                    "Amount": f"${exp.get('amount', 0):.2f}",
                    "Category": exp.get("category", ""),
                    "Date": str(exp.get("expense_date", "")),
                    "Status": Span(
                        exp.get("status", "PENDING"),
                        cls=f"px-2 py-0.5 text-xs rounded {'bg-success/20 text-success' if exp.get('status') == 'PAID' else 'bg-warning/20 text-warning'}",
                    ),
                }
                for exp in expenses
            ]
            expense_table = TableFromDicts(
                header_data=["Description", "Amount", "Category", "Date", "Status"],
                body_data=expense_body,
                body_cell_render=_expense_cell_render,
                cls=(TableT.hover, TableT.divider),
            )
            list_section = Div(
                Div(
                    H3("Expenses", cls="text-lg font-semibold"),
                    Span(f"{total_count} total", cls="text-muted-foreground text-sm"),
                    cls="flex items-center justify-between mb-3",
                ),
                Div(
                    expense_table,
                    cls="bg-background border border-border rounded-lg overflow-hidden",
                ),
            )
        else:
            list_section = Div(
                H3("Expenses", cls="text-lg font-semibold mb-3"),
                EmptyState(title="No expenses found"),
                id="expense-list",
            )

        return Div(
            PageHeader("Expense Tracker"),
            add_form,
            filter_bar,
            list_section,
        )

    # =========================================================================
    # BUDGETS VIEW
    # =========================================================================

    @staticmethod
    def render_budgets_list(
        budgets: list[dict] | None = None,
        total_budgeted: float = 0.0,
        total_spent: float = 0.0,
    ) -> Div:
        """Budget management view.

        Args:
            budgets: List of budget dicts with utilization info
            total_budgeted: Total amount budgeted
            total_spent: Total amount spent across budgets
        """
        budgets = budgets or []

        # Summary stats
        utilization = (total_spent / total_budgeted * 100) if total_budgeted > 0 else 0
        summary = StatsGrid(
            [
                StatItem(label="Total Budgeted", value=f"${total_budgeted:,.2f}", color="success"),
                StatItem(label="Total Spent", value=f"${total_spent:,.2f}", color="info"),
                StatItem(
                    label="Remaining",
                    value=f"${total_budgeted - total_spent:,.2f}",
                    color="primary",
                ),
                StatItem(label="Overall Utilization", value=f"{utilization:.0f}%", color="warning"),
            ],
            cls="mb-8",
        )

        # Create budget form
        create_form = Div(
            H3("Create New Budget", cls="text-lg font-semibold mb-3"),
            Form(
                Div(
                    Div(
                        Input(
                            type="text",
                            name="name",
                            placeholder="Budget Name",
                            required=True,
                            cls="px-3 py-2 border border-border rounded-lg w-full",
                        ),
                        cls="flex-1",
                    ),
                    Div(
                        Input(
                            type="number",
                            name="amount_limit",
                            placeholder="Amount",
                            step="0.01",
                            min="0.01",
                            required=True,
                            cls="px-3 py-2 border border-border rounded-lg w-full",
                        ),
                        cls="w-32",
                    ),
                    Select(
                        Option("Period...", value="", disabled=True, selected=True),
                        Option("Weekly", value="WEEKLY"),
                        Option("Monthly", value="MONTHLY"),
                        Option("Quarterly", value="QUARTERLY"),
                        Option("Yearly", value="YEARLY"),
                        name="period",
                        required=True,
                        cls="px-3 py-2 border border-border rounded-lg",
                    ),
                    Select(
                        Option("Category...", value="", disabled=True, selected=True),
                        Option("Personal", value="PERSONAL"),
                        Option("House (2222)", value="2222"),
                        Option("SKUEL", value="SKUEL"),
                        name="category",
                        required=True,
                        cls="px-3 py-2 border border-border rounded-lg",
                    ),
                    Button(
                        "Create Budget",
                        type="submit",
                        cls="px-4 py-2 bg-success text-white rounded-lg hover:bg-success/90",
                    ),
                    cls="flex flex-wrap gap-3 items-center",
                ),
                hx_post="/api/budgets",
                hx_target="#budget-list",
                hx_swap="afterbegin",
            ),
            cls="bg-success/10 border border-success/20 rounded-lg p-4 mb-6",
        )

        # Budget cards
        if budgets:
            budget_cards = []
            for budget in budgets:
                spent = budget.get("amount_spent", 0)
                limit = budget.get("amount_limit", 1)
                util_pct = (spent / limit * 100) if limit > 0 else 0
                remaining = limit - spent

                # Color based on utilization
                if util_pct >= 100:
                    bar_color = "bg-error"
                    status_color = "text-error"
                elif util_pct >= 80:
                    bar_color = "bg-warning/100"
                    status_color = "text-warning"
                else:
                    bar_color = "bg-success/100"
                    status_color = "text-success"

                budget_cards.append(
                    Div(
                        Div(
                            H3(budget.get("name", "Budget"), cls="font-semibold"),
                            Span(
                                budget.get("period", "Monthly"),
                                cls="text-xs px-2 py-0.5 bg-muted rounded",
                            ),
                            cls="flex items-center justify-between mb-2",
                        ),
                        Div(
                            Span(f"${spent:,.2f}", cls="font-medium"),
                            Span(" / ", cls="text-muted-foreground"),
                            Span(f"${limit:,.2f}", cls="text-muted-foreground"),
                            cls="text-sm mb-2",
                        ),
                        # Progress bar
                        Div(
                            Div(
                                style=f"width: {min(util_pct, 100)}%",
                                cls=f"h-full {bar_color} rounded-full transition-all",
                            ),
                            cls="h-2 bg-muted rounded-full overflow-hidden mb-2",
                        ),
                        Div(
                            Span(f"{util_pct:.0f}% used", cls=f"text-sm {status_color}"),
                            Span(
                                f"${remaining:,.2f} remaining", cls="text-sm text-muted-foreground"
                            ),
                            cls="flex justify-between",
                        ),
                        cls="bg-background border border-border rounded-lg p-4",
                    )
                )
            list_section = Div(
                H3("Active Budgets", cls="text-lg font-semibold mb-3"),
                Div(*budget_cards, cls="grid gap-4 md:grid-cols-2", id="budget-list"),
            )
        else:
            list_section = Div(
                H3("Active Budgets", cls="text-lg font-semibold mb-3"),
                EmptyState(
                    title="No budgets created yet",
                    description="Create your first budget to start tracking spending.",
                ),
                id="budget-list",
            )

        return Div(
            PageHeader("Budget Management"),
            summary,
            create_form,
            list_section,
        )

    # =========================================================================
    # REPORTS VIEW
    # =========================================================================

    @staticmethod
    def render_reports(
        monthly_summary: dict | None = None,
        category_breakdown: list[dict] | None = None,
        tax_summary: dict | None = None,
    ) -> Div:
        """Financial reports view.

        Args:
            monthly_summary: Monthly summary stats
            category_breakdown: Spending by category
            tax_summary: Tax-deductible expense summary
        """
        monthly_summary = monthly_summary or {}
        category_breakdown = category_breakdown or []
        tax_summary = tax_summary or {}

        # Monthly summary
        month_total = monthly_summary.get("total", 0)
        expense_count = monthly_summary.get("count", 0)
        avg_expense = monthly_summary.get("average", 0)

        monthly_section = Div(
            H3("This Month's Summary", cls="text-lg font-semibold mb-3"),
            StatsGrid(
                [
                    StatItem(label="Total Spent", value=f"${month_total:,.2f}", color="info"),
                    StatItem(label="Expenses", value=expense_count, color="primary"),
                    StatItem(label="Average", value=f"${avg_expense:,.2f}", color="success"),
                ],
                cols=3,
            ),
            cls="mb-8",
        )

        # Category breakdown
        if category_breakdown:
            category_rows = [
                Div(
                    Div(
                        Span(cat.get("icon", "📁"), cls="mr-2"),
                        Span(cat.get("name", ""), cls="font-medium"),
                        cls="flex items-center",
                    ),
                    Div(
                        Span(f"${cat.get('amount', 0):,.2f}", cls="font-semibold"),
                        Span(
                            f" ({cat.get('percentage', 0):.0f}%)",
                            cls="text-muted-foreground text-sm",
                        ),
                    ),
                    cls="flex items-center justify-between py-3 border-b border-border last:border-0",
                )
                for cat in category_breakdown
            ]
            category_section = Div(
                H3("Spending by Category", cls="text-lg font-semibold mb-3"),
                Div(*category_rows, cls="bg-background border border-border rounded-lg p-4"),
                cls="mb-8",
            )
        else:
            category_section = Div(
                H3("Spending by Category", cls="text-lg font-semibold mb-3"),
                EmptyState(title="No spending data available yet"),
                cls="mb-8",
            )

        # Tax summary
        tax_total = tax_summary.get("total", 0)
        tax_count = tax_summary.get("count", 0)

        tax_section = Div(
            H3("Tax-Deductible Expenses", cls="text-lg font-semibold mb-3"),
            Div(
                Div(
                    Span("📋", cls="text-2xl mr-3"),
                    Div(
                        Div(f"${tax_total:,.2f}", cls="text-xl font-bold text-success"),
                        Div(
                            f"{tax_count} deductible expenses this year",
                            cls="text-sm text-muted-foreground",
                        ),
                    ),
                    cls="flex items-center",
                ),
                ButtonLink(
                    "View tax report →",
                    href="/finance/reports?type=tax",
                    variant=ButtonT.ghost,
                    size=Size.xs,
                    cls="mt-3",
                ),
                cls="bg-success/10 border border-success/20 rounded-lg p-4",
            ),
            cls="mb-8",
        )

        return Div(
            PageHeader("Financial Reports"),
            monthly_section,
            category_section,
            tax_section,
        )

    # =========================================================================
    # ANALYTICS VIEW
    # =========================================================================

    @staticmethod
    def render_analytics(
        health_score: float = 0.0,
        health_tier: str = "Good",
        spending_pattern: str = "Balanced",
        budget_adherence: float = 0.0,
        trends: list[dict] | None = None,
    ) -> Div:
        """Spending analytics view.

        Args:
            health_score: Financial health score (0-1)
            health_tier: Health tier name
            spending_pattern: Spending pattern classification
            budget_adherence: Budget adherence rate (0-100)
            trends: Category trend data
        """
        trends = trends or []

        # Health score display
        health_variant = {
            "Excellent": BadgeT.success,
            "Good": BadgeT.info,
            "Fair": BadgeT.warning,
            "Poor": BadgeT.warning,
            "Critical": BadgeT.error,
        }.get(health_tier, BadgeT.neutral)

        health_section = Div(
            H3("Financial Health Score", cls="text-lg font-semibold mb-3"),
            Div(
                Div(
                    Div(f"{health_score * 100:.0f}", cls="text-4xl font-bold"),
                    Div("out of 100", cls="text-sm text-muted-foreground"),
                    cls="text-center",
                ),
                Div(
                    Badge(health_tier, variant=health_variant, size=Size.lg),
                    cls="text-center mt-4",
                ),
                cls="bg-background border border-border rounded-lg p-6",
            ),
            cls="mb-8",
        )

        # Metrics grid
        metrics_section = StatsGrid(
            [
                StatItem(label="Spending Pattern", value=spending_pattern, color="primary"),
                StatItem(
                    label="Budget Adherence", value=f"{budget_adherence:.0f}%", color="success"
                ),
            ],
            cols=2,
            cls="mb-8",
        )

        # Spending patterns explanation
        pattern_info = {
            "IMPULSE_BUYER": ("⚡", "Tends to make quick purchasing decisions"),
            "DEAL_SEEKER": ("🏷️", "Looks for discounts and value"),
            "LUXURY_ORIENTED": ("✨", "Prefers premium products and services"),
            "VALUE_FOCUSED": ("💎", "Balances quality with cost"),
            "MINIMALIST": ("🎯", "Spends only on essentials"),
            "SOCIAL_SPENDER": ("👥", "Spending often tied to social activities"),
            "STRESS_SPENDER": ("😰", "Spending may increase during stress"),
            "HABITUAL": ("🔄", "Consistent, predictable spending habits"),
        }

        pattern_icon, pattern_desc = pattern_info.get(
            spending_pattern.upper().replace(" ", "_"),
            ("📊", "Your unique spending style"),
        )

        pattern_section = Div(
            H3("Your Spending Style", cls="text-lg font-semibold mb-3"),
            Div(
                Div(
                    Span(pattern_icon, cls="text-3xl mr-3"),
                    Div(
                        Div(spending_pattern, cls="font-semibold"),
                        Div(pattern_desc, cls="text-sm text-muted-foreground"),
                    ),
                    cls="flex items-center",
                ),
                cls="bg-background border border-border rounded-lg p-4",
            ),
            cls="mb-8",
        )

        # Recommendations
        recommendations = Div(
            H3("Recommendations", cls="text-lg font-semibold mb-3"),
            Div(
                Div(
                    Span("💡", cls="mr-2"),
                    Span("Review your largest expense categories for optimization opportunities"),
                    cls="py-2",
                ),
                Div(
                    Span("📈", cls="mr-2"),
                    Span("Set up budgets for categories without spending limits"),
                    cls="py-2",
                ),
                Div(
                    Span("🎯", cls="mr-2"),
                    Span("Track recurring expenses to identify potential savings"),
                    cls="py-2",
                ),
                cls="bg-background border border-border rounded-lg p-4 divide-y divide-border",
            ),
        )

        return Div(
            PageHeader("Spending Analytics"),
            health_section,
            metrics_section,
            pattern_section,
            recommendations,
        )


__all__ = ["FinanceSectionViews"]
