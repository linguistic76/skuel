"""
Per-User Intelligence Tier Resolution
======================================

Pure function that resolves the effective intelligence tier for a user.
System tier is the ceiling; user role determines entitlement within that ceiling.

Not wired into routes yet — exists as a documented decision point for
future billing integration.

Usage:
    from core.services.intelligence_tier_service import get_user_intelligence_tier

    effective = get_user_intelligence_tier(system_tier, user_role)
    if effective.ai_enabled:
        ...

See: /docs/decisions/ADR-043-intelligence-tier-toggle.md
"""

from core.config.intelligence_tier import IntelligenceTier
from core.models.enums.user_enums import UserRole


def get_user_intelligence_tier(
    system_tier: IntelligenceTier,
    user_role: UserRole,
) -> IntelligenceTier:
    """Resolve the effective intelligence tier for a user.

    Rules:
        1. System tier is the ceiling — no user can exceed it.
        2. REGISTERED users always get CORE (free trial).
        3. MEMBER and above get the system tier.

    Args:
        system_tier: The system-wide IntelligenceTier (from env).
        user_role: The user's current role.

    Returns:
        The effective IntelligenceTier for this user.
    """
    # System ceiling: if system is CORE, everyone is CORE
    if not system_tier.ai_enabled:
        return IntelligenceTier.CORE

    # Free-tier users always get CORE
    if user_role == UserRole.REGISTERED:
        return IntelligenceTier.CORE

    # Paid users (MEMBER, TEACHER, ADMIN) get the system tier
    return system_tier
