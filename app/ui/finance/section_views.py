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
    H2,
    H3,
    A,
    Button,
    Div,
    Form,
    Input,
    Option,
    P,
    Select,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)


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
        stats_section = Div(
            Div(
                Div(f"${total_spent:,.2f}", cls="text-2xl font-bold text-info"),
                Div("Spent This Month", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-info/10 rounded-lg p-4 text-center",
            ),
            Div(
                Div(f"${total_budget:,.2f}", cls="text-2xl font-bold text-success"),
                Div("Total Budget", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-success/10 rounded-lg p-4 text-center",
            ),
            Div(
                Div(f"{budget_utilization:.0f}%", cls="text-2xl font-bold text-warning"),
                Div("Budget Used", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-warning/10 rounded-lg p-4 text-center",
            ),
            Div(
                Div(health_status, cls="text-2xl font-bold text-primary"),
                Div("Health Status", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-primary/10 rounded-lg p-4 text-center",
            ),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8",
        )

        # Quick actions
        quick_actions = Div(
            H3("Quick Actions", cls="text-lg font-semibold mb-3"),
            Div(
                A(
                    "+ Add Expense",
                    href="/finance/expenses",
                    cls="inline-flex items-center px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition",
                ),
                A(
                    "+ Create Budget",
                    href="/finance/budgets",
                    cls="inline-flex items-center px-4 py-2 bg-success text-white rounded-lg hover:bg-success/90 transition",
                ),
                A(
                    "View Reports",
                    href="/finance/reports",
                    cls="inline-flex items-center px-4 py-2 bg-base-100 border border-base-300 rounded-lg hover:bg-base-200 transition",
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
                        Span(f" - ${exp.get('amount', 0):.2f}", cls="text-base-content/60"),
                        cls="flex-1",
                    ),
                    Div(
                        Span(
                            exp.get("category", ""),
                            cls="text-xs px-2 py-0.5 bg-base-200 rounded",
                        ),
                        cls="ml-2",
                    ),
                    cls="flex items-center justify-between py-2 border-b border-base-300 last:border-0",
                )
                for exp in recent_expenses[:5]
            ]
            recent_section = Div(
                H3("Recent Expenses", cls="text-lg font-semibold mb-3"),
                Div(*expense_items, cls="bg-base-100 border border-base-300 rounded-lg p-4"),
                A(
                    "View all expenses →",
                    href="/finance/expenses",
                    cls="text-primary text-sm mt-2 inline-block",
                ),
                cls="mb-8",
            )
        else:
            recent_section = Div(
                H3("Recent Expenses", cls="text-lg font-semibold mb-3"),
                Div(
                    P("No expenses recorded yet.", cls="text-base-content/60"),
                    A(
                        "Add your first expense →",
                        href="/finance/expenses",
                        cls="text-primary text-sm",
                    ),
                    cls="bg-base-100 border border-base-300 rounded-lg p-4",
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
            H2("Finance Dashboard", cls="text-2xl font-bold mb-6"),
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
                            cls="px-3 py-2 border border-base-300 rounded-lg w-full",
                        ),
                        cls="flex-1",
                    ),
                    Span("to", cls="px-2 self-center text-base-content/60"),
                    Div(
                        Input(
                            type="date",
                            name="end_date",
                            cls="px-3 py-2 border border-base-300 rounded-lg w-full",
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
                        cls="px-3 py-2 border border-base-300 rounded-lg",
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
            cls="bg-base-100 border border-base-300 rounded-lg p-4 mb-6",
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
                            cls="px-3 py-2 border border-base-300 rounded-lg w-full",
                        ),
                        cls="w-32",
                    ),
                    Div(
                        Input(
                            type="text",
                            name="description",
                            placeholder="Description",
                            required=True,
                            cls="px-3 py-2 border border-base-300 rounded-lg w-full",
                        ),
                        cls="flex-1",
                    ),
                    Div(
                        Input(
                            type="date",
                            name="expense_date",
                            value=str(date.today()),
                            required=True,
                            cls="px-3 py-2 border border-base-300 rounded-lg w-full",
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
                        cls="px-3 py-2 border border-base-300 rounded-lg",
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
            expense_rows = [
                Tr(
                    Td(exp.get("description", ""), cls="py-3 px-4"),
                    Td(f"${exp.get('amount', 0):.2f}", cls="py-3 px-4 font-medium"),
                    Td(exp.get("category", ""), cls="py-3 px-4"),
                    Td(str(exp.get("expense_date", "")), cls="py-3 px-4 text-base-content/60"),
                    Td(
                        Span(
                            exp.get("status", "PENDING"),
                            cls=f"px-2 py-0.5 text-xs rounded {'bg-success/20 text-success' if exp.get('status') == 'PAID' else 'bg-warning/20 text-warning'}",
                        ),
                        cls="py-3 px-4",
                    ),
                    cls="border-b border-base-300 hover:bg-base-200",
                )
                for exp in expenses
            ]
            expense_table = Table(
                Thead(
                    Tr(
                        Th("Description", cls="py-3 px-4 text-left font-semibold"),
                        Th("Amount", cls="py-3 px-4 text-left font-semibold"),
                        Th("Category", cls="py-3 px-4 text-left font-semibold"),
                        Th("Date", cls="py-3 px-4 text-left font-semibold"),
                        Th("Status", cls="py-3 px-4 text-left font-semibold"),
                        cls="bg-base-200",
                    )
                ),
                Tbody(*expense_rows, id="expense-list"),
                cls="w-full",
            )
            list_section = Div(
                Div(
                    H3("Expenses", cls="text-lg font-semibold"),
                    Span(f"{total_count} total", cls="text-base-content/60 text-sm"),
                    cls="flex items-center justify-between mb-3",
                ),
                Div(
                    expense_table,
                    cls="bg-base-100 border border-base-300 rounded-lg overflow-hidden",
                ),
            )
        else:
            list_section = Div(
                H3("Expenses", cls="text-lg font-semibold mb-3"),
                Div(
                    P("No expenses found.", cls="text-base-content/60"),
                    cls="bg-base-100 border border-base-300 rounded-lg p-8 text-center",
                ),
                id="expense-list",
            )

        return Div(
            H2("Expense Tracker", cls="text-2xl font-bold mb-6"),
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
        summary = Div(
            Div(
                Div(f"${total_budgeted:,.2f}", cls="text-2xl font-bold text-success"),
                Div("Total Budgeted", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-success/10 rounded-lg p-4 text-center",
            ),
            Div(
                Div(f"${total_spent:,.2f}", cls="text-2xl font-bold text-info"),
                Div("Total Spent", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-info/10 rounded-lg p-4 text-center",
            ),
            Div(
                Div(
                    f"${total_budgeted - total_spent:,.2f}",
                    cls="text-2xl font-bold text-primary",
                ),
                Div("Remaining", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-primary/10 rounded-lg p-4 text-center",
            ),
            Div(
                Div(f"{utilization:.0f}%", cls="text-2xl font-bold text-warning"),
                Div("Overall Utilization", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-warning/10 rounded-lg p-4 text-center",
            ),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8",
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
                            cls="px-3 py-2 border border-base-300 rounded-lg w-full",
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
                            cls="px-3 py-2 border border-base-300 rounded-lg w-full",
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
                        cls="px-3 py-2 border border-base-300 rounded-lg",
                    ),
                    Select(
                        Option("Category...", value="", disabled=True, selected=True),
                        Option("Personal", value="PERSONAL"),
                        Option("House (2222)", value="2222"),
                        Option("SKUEL", value="SKUEL"),
                        name="category",
                        required=True,
                        cls="px-3 py-2 border border-base-300 rounded-lg",
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
                                cls="text-xs px-2 py-0.5 bg-base-200 rounded",
                            ),
                            cls="flex items-center justify-between mb-2",
                        ),
                        Div(
                            Span(f"${spent:,.2f}", cls="font-medium"),
                            Span(" / ", cls="text-base-content/60"),
                            Span(f"${limit:,.2f}", cls="text-base-content/60"),
                            cls="text-sm mb-2",
                        ),
                        # Progress bar
                        Div(
                            Div(
                                style=f"width: {min(util_pct, 100)}%",
                                cls=f"h-full {bar_color} rounded-full transition-all",
                            ),
                            cls="h-2 bg-base-200 rounded-full overflow-hidden mb-2",
                        ),
                        Div(
                            Span(f"{util_pct:.0f}% used", cls=f"text-sm {status_color}"),
                            Span(
                                f"${remaining:,.2f} remaining", cls="text-sm text-base-content/60"
                            ),
                            cls="flex justify-between",
                        ),
                        cls="bg-base-100 border border-base-300 rounded-lg p-4",
                    )
                )
            list_section = Div(
                H3("Active Budgets", cls="text-lg font-semibold mb-3"),
                Div(*budget_cards, cls="grid gap-4 md:grid-cols-2", id="budget-list"),
            )
        else:
            list_section = Div(
                H3("Active Budgets", cls="text-lg font-semibold mb-3"),
                Div(
                    P("No budgets created yet.", cls="text-base-content/60"),
                    P(
                        "Create your first budget to start tracking spending.",
                        cls="text-sm text-base-content/60 mt-1",
                    ),
                    cls="bg-base-100 border border-base-300 rounded-lg p-8 text-center",
                ),
                id="budget-list",
            )

        return Div(
            H2("Budget Management", cls="text-2xl font-bold mb-6"),
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
            Div(
                Div(
                    Div(f"${month_total:,.2f}", cls="text-2xl font-bold text-info"),
                    Div("Total Spent", cls="text-sm text-base-content/60 mt-1"),
                    cls="text-center",
                ),
                Div(
                    Div(str(expense_count), cls="text-2xl font-bold text-primary"),
                    Div("Expenses", cls="text-sm text-base-content/60 mt-1"),
                    cls="text-center",
                ),
                Div(
                    Div(f"${avg_expense:,.2f}", cls="text-2xl font-bold text-success"),
                    Div("Average", cls="text-sm text-base-content/60 mt-1"),
                    cls="text-center",
                ),
                cls="grid grid-cols-3 gap-4 bg-base-100 border border-base-300 rounded-lg p-6",
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
                            cls="text-base-content/60 text-sm",
                        ),
                    ),
                    cls="flex items-center justify-between py-3 border-b border-base-300 last:border-0",
                )
                for cat in category_breakdown
            ]
            category_section = Div(
                H3("Spending by Category", cls="text-lg font-semibold mb-3"),
                Div(*category_rows, cls="bg-base-100 border border-base-300 rounded-lg p-4"),
                cls="mb-8",
            )
        else:
            category_section = Div(
                H3("Spending by Category", cls="text-lg font-semibold mb-3"),
                Div(
                    P("No spending data available yet.", cls="text-base-content/60"),
                    cls="bg-base-100 border border-base-300 rounded-lg p-4",
                ),
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
                            cls="text-sm text-base-content/60",
                        ),
                    ),
                    cls="flex items-center",
                ),
                A(
                    "View tax report →",
                    href="/finance/reports?type=tax",
                    cls="text-primary text-sm mt-3 inline-block",
                ),
                cls="bg-success/10 border border-success/20 rounded-lg p-4",
            ),
            cls="mb-8",
        )

        return Div(
            H2("Financial Reports", cls="text-2xl font-bold mb-6"),
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
        health_color = {
            "Excellent": "text-success bg-success/10",
            "Good": "text-info bg-info/10",
            "Fair": "text-warning bg-warning/10",
            "Poor": "text-warning bg-warning/10",
            "Critical": "text-error bg-error/10",
        }.get(health_tier, "text-base-content/70 bg-base-200")

        health_section = Div(
            H3("Financial Health Score", cls="text-lg font-semibold mb-3"),
            Div(
                Div(
                    Div(f"{health_score * 100:.0f}", cls="text-4xl font-bold"),
                    Div("out of 100", cls="text-sm text-base-content/60"),
                    cls="text-center",
                ),
                Div(
                    Span(health_tier, cls=f"px-4 py-2 rounded-full font-semibold {health_color}"),
                    cls="text-center mt-4",
                ),
                cls="bg-base-100 border border-base-300 rounded-lg p-6",
            ),
            cls="mb-8",
        )

        # Metrics grid
        metrics_section = Div(
            Div(
                Div(spending_pattern, cls="text-xl font-bold text-primary"),
                Div("Spending Pattern", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-primary/10 rounded-lg p-4 text-center",
            ),
            Div(
                Div(f"{budget_adherence:.0f}%", cls="text-xl font-bold text-success"),
                Div("Budget Adherence", cls="text-sm text-base-content/60 mt-1"),
                cls="bg-success/10 rounded-lg p-4 text-center",
            ),
            cls="grid grid-cols-2 gap-4 mb-8",
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
                        Div(pattern_desc, cls="text-sm text-base-content/60"),
                    ),
                    cls="flex items-center",
                ),
                cls="bg-base-100 border border-base-300 rounded-lg p-4",
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
                cls="bg-base-100 border border-base-300 rounded-lg p-4 divide-y divide-border",
            ),
        )

        return Div(
            H2("Spending Analytics", cls="text-2xl font-bold mb-6"),
            health_section,
            metrics_section,
            pattern_section,
            recommendations,
        )


__all__ = ["FinanceSectionViews"]
