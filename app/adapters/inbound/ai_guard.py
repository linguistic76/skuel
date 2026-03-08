"""
AI Guard — Intelligence tier route protection.

Reusable helpers for routes that require AI services (FULL tier).

Usage:
    from adapters.inbound.ai_guard import is_ai_available, ai_unavailable_result

    if not is_ai_available(services):
        return ai_unavailable_result("feedback generation")

See: /docs/decisions/ADR-043-intelligence-tier-toggle.md
"""

from __future__ import annotations

from typing import Any

from core.utils.result_simplified import Errors, Result


def is_ai_available(services: Any) -> bool:
    """Check whether AI services are enabled on the current Services container."""
    tier = getattr(services, "intelligence_tier", None)
    if tier is None:
        return False
    return bool(tier.ai_enabled)


def ai_unavailable_result(feature: str) -> Result[Any]:
    """Return a 503 Result for routes that require AI but tier is CORE."""
    return Result.fail(
        Errors.system(
            message=f"{feature} requires FULL intelligence tier (INTELLIGENCE_TIER=full)",
            operation=feature,
        )
    )
