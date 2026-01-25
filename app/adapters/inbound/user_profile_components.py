"""
User Profile UI Components - Fundamental Hub Design
===================================================

Reusable UI components for the user profile hub.
Follows the Facebook profile model - centralized view linking to domain pages.

Key Components:
- ProfileHeader: User identity and basic info
- ActivitySummary: High-level stats across all domains
- DomainCard: Reusable card for each domain (tasks, events, habits, etc.)
- LearningStatusCard: Knowledge/Learning Path progress
- RecentActivityFeed: Last 10 actions across domains
"""

__version__ = "1.0"

from datetime import datetime
from typing import Any

from fasthtml.common import H1, H2, H3, Li, P, Ul

from core.models.user.user import User
from core.ui.daisy_components import Button, Card, CardBody, Div, Progress, Span
from core.ui.enum_helpers import get_sel_icon
from core.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# DAISYUI BADGE COMPONENT
# ============================================================================


def Badge(text: str, style: str = "default") -> Span:
    """
    DaisyUI Badge component.

    Args:
        text: Badge text content
        style: Badge style (default, primary, secondary, destructive, success, warning)

    Returns:
        Span element with DaisyUI badge classes
    """
    # Map style to DaisyUI classes
    style_classes = {
        "default": "badge",
        "primary": "badge badge-primary",
        "secondary": "badge badge-secondary",
        "destructive": "badge badge-error",
        "success": "badge badge-success",
        "warning": "badge badge-warning",
    }

    badge_class = style_classes.get(style, "badge")

    return Span(cls=badge_class)(text)


# ============================================================================
# PROFILE HEADER
# ============================================================================


def ProfileHeader(user: User) -> Div:
    """
    User profile header with identity and status.

    Args:
        user: User domain model

    Returns:
        Profile header component
    """
    return Card(cls="p-6 mb-6 bg-gradient-to-r from-primary to-secondary text-primary-content")(
        Div(cls="flex items-center gap-6")(
            # Avatar placeholder
            Div(cls="w-24 h-24 rounded-full bg-base-100 flex items-center justify-center text-4xl")(
                "👤"
            ),
            # User info
            Div(cls="flex-1")(
                H1(cls="text-3xl font-bold mb-2")(user.display_name or user.title),
                P(cls="opacity-90 mb-2")(f"@{user.title} • {user.email}"),
                # Status badges
                Div(cls="flex gap-2")(
                    user.is_verified and Badge("✓ Verified", style="success"),
                    user.is_premium and Badge("⭐ Premium", style="warning"),
                    user.is_active and Badge("● Active", style="primary"),
                ),
            ),
            # Account metadata
            Div(cls="text-right text-sm opacity-90")(
                P(f"Member since {user.created_at.strftime('%B %Y')}"),
                user.last_active_at
                and P(f"Last active: {_format_relative_time(user.last_active_at)}"),
            ),
        )
    )


# ============================================================================
# ACTIVITY SUMMARY
# ============================================================================


def ActivitySummary(domain_stats: dict[str, dict[str, Any]]) -> Div:
    """
    High-level activity summary cards.

    Args:
        domain_stats: Statistics for each domain

    Returns:
        Activity summary grid
    """
    # Calculate totals across all domains
    total_active = sum(stats.get("active_count", 0) for stats in domain_stats.values())
    total_completed = sum(stats.get("completed_count", 0) for stats in domain_stats.values())
    total_items = sum(stats.get("total_count", 0) for stats in domain_stats.values())

    completion_rate = (total_completed / total_items * 100) if total_items > 0 else 0

    return Div(cls="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6")(
        # Total active items
        Card(cls="p-4 text-center border-l-4 border-primary")(
            H3(cls="text-3xl font-bold text-primary")(str(total_active)),
            P(cls="text-base-content/70 text-sm")("Active Items"),
        ),
        # Completed items
        Card(cls="p-4 text-center border-l-4 border-success")(
            H3(cls="text-3xl font-bold text-success")(str(total_completed)),
            P(cls="text-base-content/70 text-sm")("Completed"),
        ),
        # Total items
        Card(cls="p-4 text-center border-l-4 border-primary")(
            H3(cls="text-3xl font-bold text-primary")(str(total_items)),
            P(cls="text-base-content/70 text-sm")("Total Items"),
        ),
        # Completion rate
        Card(cls="p-4 text-center border-l-4 border-primary")(
            H3(cls="text-3xl font-bold text-primary")(f"{completion_rate:.0f}%"),
            P(cls="text-base-content/70 text-sm")("Completion Rate"),
        ),
    )


# ============================================================================
# DOMAIN CARD
# ============================================================================


def DomainCard(
    domain_name: str,
    icon: str,
    stats: dict[str, Any],
    preview_items: list[dict[str, Any]],
    route: str,
) -> Card:
    """
    Reusable domain card component.

    Args:
        domain_name: Display name (e.g., "Tasks", "Events"),
        icon: Emoji icon,
        stats: Domain statistics (active_count, completed_count, etc.),
        preview_items: List of recent items (max 3 shown),
        route: Link to domain page (e.g., "/tasks"),
        color: Theme color

    Returns:
        Domain card component
    """
    active_count = stats.get("active_count", 0)
    completed_count = stats.get("completed_count", 0)
    total_count = stats.get("total_count", 0)

    return Card(cls="p-4 hover:shadow-lg transition-shadow border-l-4 border-primary")(
        # Header
        Div(cls="flex items-center justify-between mb-3")(
            Div(cls="flex items-center")(
                Span(cls="text-3xl mr-2")(icon), H3(cls="text-lg font-semibold")(domain_name)
            ),
            Badge(str(active_count), style="primary"),
        ),
        # Stats
        Div(cls="mb-3")(
            P(cls="text-sm text-base-content/70")(
                f"{active_count} active • {completed_count} completed"
            ),
            total_count > 0
            and Progress(value=completed_count, max=total_count, cls="w-full h-2 mt-2"),
        ),
        # Preview items
        preview_items
        and Ul(cls="space-y-1 mb-3")(*[PreviewItem(item) for item in preview_items[:3]]),
        # View all button
        Button(
            cls="w-full btn btn-primary",
            hx_get=route,
            hx_push_url="true",
            hx_target="#main-content",
        )(f"View All {domain_name} →"),
    )


def PreviewItem(item: dict[str, Any]) -> Li:
    """
    Preview item for domain card.

    Args:
        item: Item data (title, status, etc.)

    Returns:
        List item component
    """
    return Li(cls="text-sm text-base-content/70 truncate")(f"• {item.get('title', 'Untitled')}")


# ============================================================================
# LEARNING STATUS CARD
# ============================================================================


def LearningStatusCard(learning_stats: dict[str, Any]) -> Card:
    """
    Knowledge/Learning Path progress card.

    Args:
        learning_stats: Learning-related statistics
            - ku_working: KU count in progress
            - ku_mastered: KU count mastered
            - ls_current: Current learning steps
            - ls_completed: Completed learning steps
            - lp_active: Active learning paths
            - lp_finished: Finished learning paths

    Returns:
        Learning status card (spans 2 columns)
    """
    return Card(cls="col-span-1 md:col-span-2 p-6 border-l-4 border-primary")(
        H3(cls="text-xl font-semibold mb-4 flex items-center")(
            Span(cls="text-2xl mr-2")("🎓"), "Learning Progress"
        ),
        Div(cls="grid grid-cols-1 md:grid-cols-3 gap-6")(
            # Knowledge Units
            Div(cls="text-center")(
                Div(cls="text-3xl mb-2")("📚"),
                P(cls="text-sm text-base-content/70 mb-1")("Knowledge Units"),
                P(cls="text-2xl font-bold text-primary")(str(learning_stats.get("ku_working", 0))),
                P(cls="text-xs text-base-content/50")("working on"),
                P(cls="text-sm text-success font-semibold mt-1")(
                    f"{learning_stats.get('ku_mastered', 0)} mastered"
                ),
                Button(
                    cls="mt-3 btn btn-sm btn-indigo w-full",
                    hx_get="/knowledge",
                    hx_push_url="true",
                    hx_target="#main-content",
                )("View KUs"),
            ),
            # Learning Steps
            Div(cls="text-center")(
                Div(cls="text-3xl mb-2")("📝"),
                P(cls="text-sm text-base-content/70 mb-1")("Learning Steps"),
                P(cls="text-2xl font-bold text-primary")(str(learning_stats.get("ls_current", 0))),
                P(cls="text-xs text-base-content/50")("current"),
                P(cls="text-sm text-success font-semibold mt-1")(
                    f"{learning_stats.get('ls_completed', 0)} completed"
                ),
                Button(
                    cls="mt-3 btn btn-sm btn-indigo w-full",
                    hx_get="/learning/steps",
                    hx_push_url="true",
                    hx_target="#main-content",
                )("View Steps"),
            ),
            # Learning Paths
            Div(cls="text-center")(
                Div(cls="text-3xl mb-2")("🗺️"),
                P(cls="text-sm text-base-content/70 mb-1")("Learning Paths"),
                P(cls="text-2xl font-bold text-primary")(str(learning_stats.get("lp_active", 0))),
                P(cls="text-xs text-base-content/50")("active"),
                P(cls="text-sm text-success font-semibold mt-1")(
                    f"{learning_stats.get('lp_finished', 0)} finished"
                ),
                Button(
                    cls="mt-3 btn btn-sm btn-indigo w-full",
                    hx_get="/learning/paths",
                    hx_push_url="true",
                    hx_target="#main-content",
                )("View Paths"),
            ),
        ),
    )


# ============================================================================
# DOMAIN CARDS GRID
# ============================================================================


def DomainCardsGrid(domain_stats: dict[str, dict[str, Any]]) -> Div:
    """
    Grid of all domain cards.

    Args:
        domain_stats: Statistics for each domain with preview items

    Returns:
        Grid of domain cards
    """
    return Div(cls="mb-8")(
        H2(cls="text-2xl font-bold mb-4")("Your Domains"),
        Div(cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4")(
            # Tasks
            DomainCard(
                domain_name="Tasks",
                icon="📋",
                stats=domain_stats.get("tasks", {}),
                preview_items=domain_stats.get("tasks", {}).get("preview", []),
                route="/tasks",
            ),
            # Events
            DomainCard(
                domain_name="Events",
                icon="📅",
                stats=domain_stats.get("events", {}),
                preview_items=domain_stats.get("events", {}).get("preview", []),
                route="/events",
            ),
            # Habits
            DomainCard(
                domain_name="Habits",
                icon="🔄",
                stats=domain_stats.get("habits", {}),
                preview_items=domain_stats.get("habits", {}).get("preview", []),
                route="/habits",
            ),
            # Goals
            DomainCard(
                domain_name="Goals",
                icon="🎯",
                stats=domain_stats.get("goals", {}),
                preview_items=domain_stats.get("goals", {}).get("preview", []),
                route="/goals",
            ),
            # Choices
            DomainCard(
                domain_name="Choices",
                icon="🤔",
                stats=domain_stats.get("choices", {}),
                preview_items=domain_stats.get("choices", {}).get("preview", []),
                route="/choices",
            ),
            # Principles
            DomainCard(
                domain_name="Principles",
                icon="⚖️",
                stats=domain_stats.get("principles", {}),
                preview_items=domain_stats.get("principles", {}).get("preview", []),
                route="/principles",
            ),
            # Learning Status Card (spans 2 columns)
            LearningStatusCard(domain_stats.get("learning", {})),
        ),
    )


# ============================================================================
# RECENT ACTIVITY FEED
# ============================================================================


def RecentActivityFeed(recent_activities: list[dict[str, Any]]) -> Card:
    """
    Recent activity feed showing last 10 actions.

    Args:
        recent_activities: List of recent activity records
            - activity_type: Type (task, event, habit, etc.)
            - action: Action performed (created, completed, updated)
            - title: Item title
            - timestamp: When it happened

    Returns:
        Recent activity feed card
    """
    return Card(cls="p-6")(
        H2(cls="text-xl font-semibold mb-4 flex items-center")(
            Span(cls="text-2xl mr-2")("📊"), "Recent Activity"
        ),
        (
            recent_activities
            and Ul(cls="space-y-3")(
                *[ActivityItem(activity) for activity in recent_activities[:10]]
            )
        )
        or P(cls="text-base-content/50 text-center py-8")("No recent activity"),
    )


def ActivityItem(activity: dict[str, Any]) -> Li:
    """
    Single activity item in feed.

    Args:
        activity: Activity data

    Returns:
        Activity list item
    """
    activity_type = activity.get("activity_type", "unknown")
    action = activity.get("action", "updated")
    title = activity.get("title", "Untitled")
    timestamp = activity.get("timestamp") or datetime.now()

    # Get icon based on activity type
    icon_map = {
        "task": "📋",
        "event": "📅",
        "habit": "🔄",
        "goal": "🎯",
        "choice": "🤔",
        "principle": "⚖️",
        "knowledge": "📚",
        "learning": "🎓",
    }
    icon = icon_map.get(activity_type, "•")

    return Li(cls="flex items-start gap-3 pb-3 border-b border-base-300 last:border-0")(
        Span(cls="text-xl")(icon),
        Div(cls="flex-1")(
            P(cls="text-sm")(
                Span(cls="font-semibold")(action.replace("_", " ").title()),
                " ",
                Span(cls="text-base-content/70")(activity_type),
                ": ",
                Span(cls="text-primary")(title),
            ),
            P(cls="text-xs text-base-content/50")(_format_relative_time(timestamp)),
        ),
    )


# ============================================================================
# SEL JOURNEY SECTION
# ============================================================================


def SELJourneySection(journey: Any) -> Div:
    """
    SEL Journey section for user profile.

    Shows overall SEL progress and recommended next category.

    Args:
        journey: SELJourney model with progress data

    Returns:
        Div with SEL journey summary
    """
    # Get recommended category
    try:
        next_category = journey.get_next_recommended_category()
        category_name = next_category.value.replace("_", " ").title()
        # ✅ Use enum helper for icon
        category_icon = get_sel_icon(next_category.value)
    except (AttributeError, TypeError):
        category_name = "Self Awareness"
        category_icon = "🧘"

    return Div(cls="mb-8")(
        # Section header
        Div(cls="flex justify-between items-center mb-4")(
            H2(cls="text-2xl font-bold m-0")("SEL - Your Learning Journey"),
            Button(
                cls="btn btn-ghost btn-sm",
                hx_get="/sel",
                hx_push_url="true",
                hx_target="body",
            )("View Full Journey →"),
        ),
        # Journey card
        Card(
            CardBody(
                # Overall progress
                Div(cls="mb-4")(
                    P(cls="text-sm text-base-content/50 mb-2")(
                        f"Overall Progress: {journey.overall_completion:.0f}%"
                    ),
                    Progress(
                        value=int(journey.overall_completion),
                        max=100,
                        cls="progress progress-primary mb-2",
                    ),
                ),
                # Recommended focus
                Div(cls="alert alert-info")(
                    P(cls="font-bold m-0")(f"📍 Recommended Focus: {category_name} {category_icon}")
                ),
                # Quick category cards (top 3)
                Div(cls="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-4")(
                    *[
                        _SELCategoryMiniCard(category, progress)
                        for category, progress in list(journey.category_progress.items())[:3]
                    ]
                ),
            ),
            cls="bg-base-100 shadow-sm",
        ),
    )


def _SELCategoryMiniCard(category: Any, progress: Any) -> Div:
    """
    Mini card for one SEL category in profile view.

    Args:
        category: SEL category enum
        progress: Progress data for this category

    Returns:
        Div with mini card
    """
    try:
        # ✅ Use enum helper for icon
        icon = get_sel_icon(category.value)
        name = category.value.replace("_", " ").title()
        percentage = progress.completion_percentage
    except (AttributeError, TypeError):
        icon = "📚"
        name = "Learning"
        percentage = 0.0

    return Div()(
        Card(
            CardBody(
                Span(cls="text-lg")(icon),
                P(cls="text-sm font-bold mt-2 mb-0")(name),
                P(cls="text-sm text-base-content/50 m-0")(f"{percentage:.0f}%"),
                cls="text-center p-3",
            ),
            cls="bg-base-100 shadow-sm",
        )
    )


# ============================================================================
# MAIN PROFILE HUB
# ============================================================================


def UserProfileHub(
    user: User,
    domain_stats: dict[str, dict[str, Any]],
    recent_activities: list[dict[str, Any]],
    sel_journey: Any | None = None,
    is_auth: bool = True,  # Default True since we have a User object
) -> Div:
    """
    Main user profile hub component.

    Args:
        user: User domain model,
        domain_stats: Statistics for all domains,
        recent_activities: Recent activity records,
        sel_journey: Optional SEL journey data for adaptive curriculum
        is_auth: Whether user is authenticated (default True since we have User)

    Returns:
        Complete profile hub page
    """
    from ui.layouts.navbar import create_navbar

    user_uid = user.uid
    navbar = create_navbar(current_user=user_uid, is_authenticated=is_auth)

    return Div(
        navbar,
        Div(cls="container mx-auto p-6 max-w-7xl")(
            ProfileHeader(user),
            ActivitySummary(domain_stats),
            # Add SEL Journey section if available
            SELJourneySection(sel_journey) if sel_journey else None,
            DomainCardsGrid(domain_stats),
            RecentActivityFeed(recent_activities),
        ),
    )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def _format_relative_time(timestamp: datetime | None) -> str:
    """Format timestamp as relative time (e.g., '2 hours ago')."""
    if timestamp is None:
        return "just now"
    now = datetime.now()
    delta = now - timestamp

    if delta.days > 0:
        return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
    elif delta.seconds >= 3600:
        hours = delta.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif delta.seconds >= 60:
        minutes = delta.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "just now"
