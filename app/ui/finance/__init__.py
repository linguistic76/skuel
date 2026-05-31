"""Finance UI module.

Provides the finance hub layout and navigation. After the ADR-052 Phase 5
demolition only the invoice page survives. All finance routes require ADMIN role.
"""

from ui.finance.layout import (
    FINANCE_SIDEBAR_ITEMS,
    create_finance_page,
)

__all__ = [
    "FINANCE_SIDEBAR_ITEMS",
    "create_finance_page",
]
