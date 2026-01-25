"""
View Layer
==========

View transformation functions following the three-tier type system.
Views provide a clean separation between domain models and API responses.

Three-Tier Architecture:
- Tier 1 (External): Pydantic models for validation
- Tier 2 (Transfer): DTOs for data movement
- Tier 3 (Core): Pure domain models (frozen, immutable)

View Layer sits between Tier 3 (Pure) and API responses.
"""

from .journal_view import (
    journal_pure_to_view,
    journals_pure_to_summary_list,
    journals_pure_to_view_list,
)

__all__ = [
    "journal_pure_to_view",
    "journals_pure_to_summary_list",
    "journals_pure_to_view_list",
]
