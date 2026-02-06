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

NOTE: Journal views REMOVED (February 2026) - Journal merged into Reports.
Use Reports domain views for journal-type reports.
"""

__all__: list[str] = []
