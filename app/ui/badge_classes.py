"""
Centralized Badge & Color Class Mappings (MonsterUI/Tailwind)
==============================================================

Single source of truth for all status/priority/role/essentiality -> CSS class
mappings used across SKUEL's UI layer.

Migrated from DaisyUI badge-* classes to Tailwind utility classes.
Every UI component that needs a badge color, text color, or background class
should import from this module instead of defining inline dicts.

Domain-specific mappings that appear in only one file (principle categories,
invoice statuses, financial health tiers) stay in their domain view files.
Only DUPLICATED mappings are centralized here.
"""

from __future__ import annotations

# ============================================================================
# ACTIVITY STATUS -> BADGE CLASS
# ============================================================================
# Tailwind utility classes replacing DaisyUI badge-* classes.

STATUS_BADGE: dict[str, str] = {
    # Common activity statuses
    "active": "bg-green-100 text-green-800 border-green-200",
    "completed": "bg-green-100 text-green-800 border-green-200",
    "done": "bg-green-100 text-green-800 border-green-200",
    "in_progress": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "paused": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "pending": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "todo": "bg-blue-100 text-blue-800 border-blue-200",
    "scheduled": "bg-blue-100 text-blue-800 border-blue-200",
    "blocked": "bg-red-100 text-red-800 border-red-200",
    "cancelled": "bg-red-100 text-red-800 border-red-200",
    "failed": "bg-red-100 text-red-800 border-red-200",
    "inactive": "bg-gray-100 text-gray-600 border-gray-200",
    "archived": "bg-gray-100 text-gray-600 border-gray-200",
    "draft": "bg-gray-100 text-gray-600 border-gray-200",
    # Choice-specific
    "decided": "bg-green-100 text-green-800 border-green-200",
    "implemented": "bg-blue-100 text-blue-800 border-blue-200",
    "evaluated": "bg-primary/10 text-primary border-primary/20",
}


def status_badge_class(status: str) -> str:
    """Get Tailwind badge class for any activity status string."""
    return STATUS_BADGE.get(status.lower().strip(), "bg-gray-100 text-gray-600 border-gray-200")


# ============================================================================
# ACTIVITY STATUS -> TEXT COLOR
# ============================================================================

STATUS_TEXT: dict[str, str] = {
    "completed": "text-green-600",
    "in_progress": "text-yellow-600",
    "pending": "text-muted-foreground",
    "overdue": "text-red-600",
    "at_risk": "text-red-600",
    "blocked": "text-red-600",
    "keystone": "text-green-600",
    "near_complete": "text-primary",
    "active": "text-green-600",
    "paused": "text-yellow-600",
}


def status_text_class(status: str) -> str:
    """Get Tailwind text color class for any activity status string."""
    return STATUS_TEXT.get(status.lower().strip(), "text-muted-foreground")


# ============================================================================
# PRIORITY -> BADGE CLASS
# ============================================================================

PRIORITY_BADGE: dict[str, str] = {
    "critical": "bg-red-100 text-red-800 border-red-200",
    "high": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "medium": "bg-blue-100 text-blue-800 border-blue-200",
    "low": "bg-green-100 text-green-800 border-green-200",
}


def priority_badge_class(priority: str) -> str:
    """Get Tailwind badge class for a priority level."""
    return PRIORITY_BADGE.get(
        priority.lower().strip(), "bg-muted text-muted-foreground border-border"
    )


# ============================================================================
# PRIORITY -> TEXT COLOR
# ============================================================================

PRIORITY_TEXT: dict[str, str] = {
    "critical": "text-red-600",
    "high": "text-yellow-600",
    "medium": "text-blue-600",
    "low": "text-muted-foreground",
}


def priority_text_class(priority: str) -> str:
    """Get Tailwind text color class for a priority level."""
    return PRIORITY_TEXT.get(priority.lower().strip(), "text-muted-foreground")


# ============================================================================
# PRIORITY / IMPACT -> BORDER & DOT CLASSES
# ============================================================================

PRIORITY_BORDER: dict[str, str] = {
    "critical": "border-l-red-500",
    "high": "border-l-red-500",
    "medium": "border-l-yellow-500",
    "low": "border-l-green-500",
}


def priority_border_class(priority: str) -> str:
    """Get border-left class for a priority/impact level."""
    return PRIORITY_BORDER.get(priority.lower().strip(), "border-l-border")


PRIORITY_DOT: dict[str, str] = {
    "critical": "bg-red-500",
    "high": "bg-red-500",
    "medium": "bg-yellow-500",
    "low": "bg-green-500",
}


def priority_dot_class(priority: str) -> str:
    """Get background dot class for a priority/impact level."""
    return PRIORITY_DOT.get(priority.lower().strip(), "bg-muted")


# ============================================================================
# ESSENTIALITY -> BADGE CLASS
# ============================================================================

ESSENTIALITY_BADGE: dict[str, str] = {
    "essential": "bg-red-100 text-red-800 border-red-200",
    "critical": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "supporting": "bg-blue-100 text-blue-800 border-blue-200",
    "optional": "bg-gray-100 text-gray-600 border-gray-200",
}


def essentiality_badge_class(essentiality: str) -> str:
    """Get Tailwind badge class for a habit essentiality level."""
    return ESSENTIALITY_BADGE.get(
        essentiality.lower().strip(), "bg-gray-100 text-gray-600 border-gray-200"
    )


# ============================================================================
# ESSENTIALITY -> STYLED (emoji, border, background)
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
        ("\u26aa", "border-border", "bg-muted"),
    )


# ============================================================================
# SUBMISSION / REPORT STATUS -> BADGE CLASS
# ============================================================================

SUBMISSION_STATUS_BADGE: dict[str, str] = {
    "submitted": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "queued": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "processing": "bg-blue-100 text-blue-800 border-blue-200",
    "completed": "bg-green-100 text-green-800 border-green-200",
    "failed": "bg-red-100 text-red-800 border-red-200",
    "manual_review": "bg-gray-100 text-gray-600 border-gray-200",
    "revision_requested": "bg-yellow-100 text-yellow-800 border-yellow-200",
}


def submission_status_badge_class(status: str) -> str:
    """Get Tailwind badge class for a submission/report status."""
    return SUBMISSION_STATUS_BADGE.get(
        status.lower().strip(), "bg-gray-100 text-gray-600 border-gray-200"
    )


# ============================================================================
# HEALTH STATUS -> CSS CLASSES
# ============================================================================

HEALTH_BG: dict[str, str] = {
    "healthy": "bg-green-50 border-green-500",
    "warning": "bg-yellow-50 border-yellow-500",
    "critical": "bg-red-50 border-red-500",
}


def health_bg_class(status: str) -> str:
    """Get background/border classes for a domain health status."""
    return HEALTH_BG.get(status.lower().strip(), "bg-background border-border shadow-sm")


HEALTH_DOT: dict[str, str] = {
    "healthy": "bg-green-500",
    "warning": "bg-yellow-500",
    "critical": "bg-red-500",
}


def health_dot_class(status: str) -> str:
    """Get dot background class for a domain health status."""
    return HEALTH_DOT.get(status.lower().strip(), "bg-muted-foreground")


# ============================================================================
# USER ROLE -> BADGE CLASS
# ============================================================================

ROLE_BADGE: dict[str, str] = {
    "admin": "bg-red-100 text-red-800 border-red-200",
    "teacher": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "member": "bg-green-100 text-green-800 border-green-200",
    "registered": "bg-blue-100 text-blue-800 border-blue-200",
}


def role_badge_class(role: str) -> str:
    """Get Tailwind badge class for a user role."""
    return ROLE_BADGE.get(
        role.lower().strip(), "bg-muted text-muted-foreground border-border"
    )


# ============================================================================
# REFLECTION QUALITY -> BADGE CLASS
# ============================================================================

QUALITY_BADGE: dict[str, str] = {
    "deep": "bg-green-100 text-green-800 border-green-200",
    "moderate": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "shallow": "bg-gray-100 text-gray-600 border-gray-200",
}


def quality_badge_class(quality: str) -> str:
    """Get Tailwind badge class for reflection quality level."""
    return QUALITY_BADGE.get(
        quality.lower().strip(), "bg-gray-100 text-gray-600 border-gray-200"
    )
