# mypy: ignore-errors
"""
Vulture whitelist — false positives that should not be reported.

Vulture treats this as regular Python: any name mentioned here is considered "used".
See: https://github.com/jendrikseipp/vulture#whitelisting
"""

# TYPE_CHECKING imports — used in string annotations, vulture can't track them
AnalyticsService  # noqa: F821, B018
EventsRelationshipOperations  # noqa: F821, B018
GoalsRelationshipOperations  # noqa: F821, B018
HabitsRelationshipOperations  # noqa: F821, B018

# __exit__ protocol — exc_tb is part of the Python context manager signature
exc_tb  # noqa: F821, B018

# Protocol / abstract method parameters — define the contract for implementers
current_week  # noqa: F821, B018
transaction_id  # noqa: F821, B018
learning_investment  # noqa: F821, B018
allocation_percentage  # noqa: F821, B018
reconciliation_data  # noqa: F821, B018
invoice_uid  # noqa: F821, B018
resolution  # noqa: F821, B018
entity_id  # noqa: F821, B018
journal_category  # noqa: F821, B018

# Intentional: **kwargs capture for extensible route signatures
related_services  # noqa: F821, B018

# Intentional: mutable dict passed by reference, modified by get_engine()
engines  # noqa: F821, B018

# Intentional: kept for API compatibility (navigation.py)
boxed  # noqa: F821, B018
lifted  # noqa: F821, B018

# Intentional: Alpine.js expanded state placeholder (tree_view.py)
is_expanded  # noqa: F821, B018

# Intentional: existing_dto kept for type contract clarity (lesson_core_service.py)
existing_dto  # noqa: F821, B018
