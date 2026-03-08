"""
Centralized Badge & Color Class Mappings
==========================================

Single source of truth for all status/priority/role/essentiality → CSS class
mappings used across SKUEL's UI layer.

Every UI component that needs a badge color, text color, or background class
should import from this module instead of defining inline dicts.

Domain-specific mappings that appear in only one file (principle categories,
invoice statuses, financial health tiers) stay in their domain view files.
Only DUPLICATED mappings are centralized here.
"""

from __future__ import annotations

# ============================================================================
# ACTIVITY STATUS → BADGE CLASS
# ============================================================================
# Superset covering all activity domain statuses (tasks, goals, habits,
# choices, principles, events) and card_generator generic statuses.

STATUS_BADGE: dict[str, str] = {
    # Common activity statuses
    "active": "badge-success",
    "completed": "badge-success",
    "done": "badge-success",
    "in_progress": "badge-warning",
    "paused": "badge-warning",
    "pending": "badge-warning",
    "todo": "badge-info",
    "scheduled": "badge-info",
    "blocked": "badge-error",
    "cancelled": "badge-error",
    "failed": "badge-error",
    "inactive": "badge-ghost",
    "archived": "badge-ghost",
    "draft": "badge-ghost",
    # Choice-specific
    "decided": "badge-success",
    "implemented": "badge-info",
    "evaluated": "badge-primary",
}


def status_badge_class(status: str) -> str:
    """Get DaisyUI badge class for any activity status string."""
    return STATUS_BADGE.get(status.lower().strip(), "badge-ghost")


# ============================================================================
# ACTIVITY STATUS → TEXT COLOR
# ============================================================================

STATUS_TEXT: dict[str, str] = {
    "completed": "text-success",
    "in_progress": "text-warning",
    "pending": "text-base-content/60",
    "overdue": "text-error",
    "at_risk": "text-error",
    "blocked": "text-error",
    "keystone": "text-success",
    "near_complete": "text-primary",
    "active": "text-success",
    "paused": "text-warning",
}


def status_text_class(status: str) -> str:
    """Get Tailwind text color class for any activity status string."""
    return STATUS_TEXT.get(status.lower().strip(), "text-base-content/60")


# ============================================================================
# PRIORITY → BADGE CLASS
# ============================================================================

PRIORITY_BADGE: dict[str, str] = {
    "critical": "badge-error",
    "high": "badge-warning",
    "medium": "badge-info",
    "low": "badge-success",
}


def priority_badge_class(priority: str) -> str:
    """Get DaisyUI badge class for a priority level."""
    return PRIORITY_BADGE.get(priority.lower().strip(), "badge-neutral")


# ============================================================================
# PRIORITY → TEXT COLOR
# ============================================================================

PRIORITY_TEXT: dict[str, str] = {
    "critical": "text-error",
    "high": "text-warning",
    "medium": "text-info",
    "low": "text-base-content/70",
}


def priority_text_class(priority: str) -> str:
    """Get Tailwind text color class for a priority level."""
    return PRIORITY_TEXT.get(priority.lower().strip(), "text-base-content/70")


# ============================================================================
# PRIORITY / IMPACT → BORDER & DOT CLASSES
# ============================================================================
# Used by entity cards (left border accent) and insight cards (impact dots).
# Same semantic scale as PRIORITY_BADGE: critical/high → error, medium → warning,
# low → success.

PRIORITY_BORDER: dict[str, str] = {
    "critical": "border-l-error",
    "high": "border-l-error",
    "medium": "border-l-warning",
    "low": "border-l-success",
}


def priority_border_class(priority: str) -> str:
    """Get DaisyUI border-left class for a priority/impact level."""
    return PRIORITY_BORDER.get(priority.lower().strip(), "border-l-base-300")


PRIORITY_DOT: dict[str, str] = {
    "critical": "bg-error",
    "high": "bg-error",
    "medium": "bg-warning",
    "low": "bg-success",
}


def priority_dot_class(priority: str) -> str:
    """Get background dot class for a priority/impact level."""
    return PRIORITY_DOT.get(priority.lower().strip(), "bg-base-300")


# ============================================================================
# ESSENTIALITY → BADGE CLASS
# ============================================================================

ESSENTIALITY_BADGE: dict[str, str] = {
    "essential": "badge-error",
    "critical": "badge-warning",
    "supporting": "badge-info",
    "optional": "badge-ghost",
}


def essentiality_badge_class(essentiality: str) -> str:
    """Get DaisyUI badge class for a habit essentiality level."""
    return ESSENTIALITY_BADGE.get(essentiality.lower().strip(), "badge-ghost")


# ============================================================================
# ESSENTIALITY → STYLED (emoji, border, background)
# ============================================================================

ESSENTIALITY_STYLED: dict[str, tuple[str, str, str]] = {
    "essential": ("\U0001f534", "border-red-500", "bg-red-50"),
    "critical": ("\U0001f7e0", "border-orange-500", "bg-orange-50"),
    "supporting": ("\U0001f7e1", "border-yellow-500", "bg-yellow-50"),
    "optional": ("\U0001f7e2", "border-green-500", "bg-green-50"),
}


def essentiality_styled(essentiality: str) -> tuple[str, str, str]:
    """Get (emoji, border_class, bg_class) for a habit essentiality level."""
    return ESSENTIALITY_STYLED.get(
        essentiality.lower().strip(),
        ("\u26aa", "border-base-300", "bg-base-200"),
    )


# ============================================================================
# SUBMISSION / REPORT STATUS → BADGE CLASS
# ============================================================================

SUBMISSION_STATUS_BADGE: dict[str, str] = {
    "submitted": "badge-warning",
    "queued": "badge-warning",
    "processing": "badge-info",
    "completed": "badge-success",
    "failed": "badge-error",
    "manual_review": "badge-ghost",
    "revision_requested": "badge-warning",
}


def submission_status_badge_class(status: str) -> str:
    """Get DaisyUI badge class for a submission/report status."""
    return SUBMISSION_STATUS_BADGE.get(status.lower().strip(), "badge-ghost")


# ============================================================================
# HEALTH STATUS → CSS CLASSES
# ============================================================================

HEALTH_BG: dict[str, str] = {
    "healthy": "bg-success/10 border-success",
    "warning": "bg-warning/10 border-warning",
    "critical": "bg-error/10 border-error",
}


def health_bg_class(status: str) -> str:
    """Get background/border classes for a domain health status."""
    return HEALTH_BG.get(status.lower().strip(), "bg-base-100 border-base-300 shadow-sm")


HEALTH_DOT: dict[str, str] = {
    "healthy": "bg-success",
    "warning": "bg-warning",
    "critical": "bg-error",
}


def health_dot_class(status: str) -> str:
    """Get dot background class for a domain health status."""
    return HEALTH_DOT.get(status.lower().strip(), "bg-base-content/60")


# ============================================================================
# USER ROLE → BADGE CLASS
# ============================================================================

ROLE_BADGE: dict[str, str] = {
    "admin": "badge-error",
    "teacher": "badge-warning",
    "member": "badge-success",
    "registered": "badge-info",
}


def role_badge_class(role: str) -> str:
    """Get DaisyUI badge class for a user role."""
    return ROLE_BADGE.get(role.lower().strip(), "badge-neutral")


# ============================================================================
# REFLECTION QUALITY → BADGE CLASS
# ============================================================================

QUALITY_BADGE: dict[str, str] = {
    "deep": "badge-success",
    "moderate": "badge-warning",
    "shallow": "badge-ghost",
}


def quality_badge_class(quality: str) -> str:
    """Get DaisyUI badge class for reflection quality level."""
    return QUALITY_BADGE.get(quality.lower().strip(), "badge-ghost")
