# mypy: ignore-errors
"""
Vulture whitelist — false positives that should not be reported.

Vulture treats this as regular Python: any name mentioned here is considered "used".
See: https://github.com/jendrikseipp/vulture#whitelisting
"""

# TYPE_CHECKING imports — used in string annotations, vulture can't track them
AnalyticsService  # noqa: F821, B018

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

# Intentional: Alpine.js expanded state placeholder (tree_view.py)
is_expanded  # noqa: F821, B018

# TYPE_CHECKING imports — used in string annotations, vulture can't track them
EmbeddingClientOperations  # noqa: F821, B018
EmbeddingsBackendOperations  # noqa: F821, B018
IngestionBackendOperations  # noqa: F821, B018
JupyterSyncBackendOperations  # noqa: F821, B018
LateralRelationshipBackendOperations  # noqa: F821, B018
LateralRelationshipOperations  # noqa: F821, B018
VectorSearchBackendOperations  # noqa: F821, B018
ActivityReportGeneratorBackendOperations  # noqa: F821, B018
ReviewQueueBackendOperations  # noqa: F821, B018
UserProgressBackendOperations  # noqa: F821, B018
SupportsRichComparison  # noqa: F821, B018

# Protocol method parameters — names define keyword-callable contracts
new_instructions  # noqa: F821, B018

# Called from scripts/vault_bridge_sync.py (scripts/ not in FIRST_PARTY_ROOTS) —
# the ADR-074 script-mode subscribe-then-drain freshness step
drain  # noqa: F821, B018
