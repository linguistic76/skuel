"""
SEL (Social Emotional Learning) UI Components
==============================================

DaisyUI/Tailwind-based components for the adaptive SEL curriculum.

Key Components:
- SELCategoryCard: Card showing progress in one SEL category
- AdaptiveCurriculumPage: Full page with personalized KU recommendations
- AdaptiveKUCard: Card for one Knowledge Unit in curriculum
- SELJourneyOverview: Complete SEL journey across all 5 categories
"""

__version__ = "1.0"


from fasthtml.common import H1, H2, H3, A, P

from core.models.ku.ku import Ku
from core.models.sel import SELCategoryProgress, SELJourney
from core.models.shared_enums import SELCategory
from core.ui.daisy_components import Card, CardBody, Div, Progress, Span
from core.ui.enum_helpers import get_sel_icon
from core.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# DAISYUI BADGE COMPONENT (Reused from user_profile_components)
# ============================================================================


def Badge(text: str, style: str = "default") -> Span:
    """
    DaisyUI Badge component.

    Args:
        text: Badge text content
        style: Badge style (default, primary, secondary, success, warning)

    Returns:
        Span element with DaisyUI badge classes
    """
    style_classes = {
        "default": "badge",
        "primary": "badge badge-primary",
        "secondary": "badge badge-secondary",
        "success": "badge badge-success",
        "warning": "badge badge-warning",
        "destructive": "badge badge-error",
    }
    badge_class = style_classes.get(style, "badge")
    return Span(cls=badge_class)(text)


# ============================================================================
# SEL CATEGORY CARD
# ============================================================================


def SELCategoryCard(category: SELCategory, progress: SELCategoryProgress) -> Card:
    """
    DaisyUI Card for one SEL category showing progress.

    Args:
        category: SEL category
        progress: User's progress in this category

    Returns:
        Card component with progress and action button

    Uses get_sel_icon() helper
    """
    return Card(
        CardBody(
            # Card header with icon and title
            Div(
                Div(
                    # Use enum helper for icon
                    Span(get_sel_icon(category.value), cls="text-lg mr-2"),
                    Div(
                        H3(category.value.replace("_", " ").title(), cls="card-title m-0"),
                        P(category.get_description(), cls="text-sm text-gray-500 m-0"),
                    ),
                    cls="flex items-center",
                ),
                Badge(f"{progress.completion_percentage:.0f}%", style="primary"),
                cls="flex justify-between items-center mb-2",
            ),
            # Progress bar using DaisyUI
            Progress(
                value=progress.kus_mastered,
                max=progress.total_kus,
                cls="progress progress-primary mb-2",
            ),
            # Stats row
            Div(
                P(f"{progress.kus_mastered} mastered", cls="m-0"),
                P(f"{progress.kus_in_progress} in progress", cls="m-0"),
                P(f"{progress.kus_available} available", cls="m-0"),
                cls="flex justify-between text-sm text-gray-500 mb-2",
            ),
            # Action button using DaisyUI button classes - simple link instead of HTMX
            A(
                "Continue Learning →",
                href=f"/sel/{category.value.replace('_', '-')}",
                cls="btn btn-primary w-full",
            ),
        ),
        cls="card bg-base-100 shadow-sm hover:shadow-md transition-shadow",
    )


# ============================================================================
# ADAPTIVE CURRICULUM PAGE
# ============================================================================


def AdaptiveCurriculumPage(
    category: SELCategory, curriculum: list[Ku], progress: SELCategoryProgress
) -> Div:
    """
    Full page showing adaptive curriculum for one SEL category.

    Args:
        category: SEL category,
        curriculum: Personalized list of KUs for this user,
        progress: User's progress in this category

    Returns:
        Div containing the complete adaptive curriculum page
    """
    return Div(
        # Page header with icon and title
        Div(
            Div(
                # Use enum helper for icon
                Span(get_sel_icon(category.value), cls="text-lg mr-2"),
                H1(category.value.replace("_", " ").title(), cls="text-2xl font-bold m-0"),
                cls="flex items-center mb-4",
            ),
            P(category.get_description(), cls="text-lg text-gray-500"),
            # Progress indicator
            Div(
                P(
                    f"Your Progress: {progress.completion_percentage:.0f}% • "
                    f"Level: {progress.current_level.value.title()}",
                    cls="text-sm text-gray-500 mb-2",
                ),
                Progress(
                    value=progress.kus_mastered,
                    max=progress.total_kus,
                    cls="progress progress-primary",
                ),
                cls="mt-4",
            ),
            cls="mb-8",
        ),
        # Section header
        H2("Your Personalized Learning Path", cls="text-xl font-semibold mb-4"),
        P(
            "These knowledge units are selected specifically for you based on "
            "your current level, mastered prerequisites, and learning pace.",
            cls="text-gray-500 mb-4",
        ),
        # KU Cards grid using Tailwind grid
        Div(
            *[AdaptiveKUCard(ku) for ku in curriculum],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        )
        if curriculum
        else Div(
            P(
                "You've completed all available content in this category! Check back soon for more.",
                cls="text-gray-500 text-lg",
            ),
            cls="text-center p-8",
        ),
        cls="container mx-auto max-w-6xl p-4",
    )


# ============================================================================
# ADAPTIVE KU CARD
# ============================================================================


def AdaptiveKUCard(ku: Ku) -> Div:
    """
    DaisyUI Card for one Knowledge Unit in adaptive curriculum.

    Args:
        ku: Knowledge unit to display

    Returns:
        Div containing a DaisyUI card
    """
    return Div(
        Card(
            CardBody(
                # Title and level badge
                Div(
                    H3(ku.title, cls="card-title m-0"),
                    Badge(ku.learning_level.value.title(), style="secondary"),
                    cls="flex justify-between items-start mb-2",
                ),
                # Description
                P(
                    ku.content[:150] + "..." if len(ku.content) > 150 else ku.content,
                    cls="text-sm text-gray-500 mb-2",
                ),
                # Metadata badges
                Div(
                    Span(f"⏱ {ku.estimated_time_minutes} min", cls="badge badge-ghost"),
                    Span(f"🎯 {ku.difficulty_rating:.1f}/1.0 difficulty", cls="badge badge-ghost"),
                    Span("✓ Prerequisites met", cls="badge badge-success")
                    if getattr(ku, "prerequisites_met", False)
                    else None,
                    cls="flex flex-wrap gap-2 mb-2",
                ),
                # Action button - simple link instead of HTMX
                A(
                    "Start Learning →",
                    href=f"/knowledge/{ku.uid}",
                    cls="btn btn-primary w-full mt-2",
                ),
            ),
            cls="card bg-base-100 shadow-sm hover:shadow-md transition-shadow",
        )
    )


# ============================================================================
# SEL JOURNEY OVERVIEW
# ============================================================================


def SELJourneyOverview(journey: SELJourney) -> Div:
    """
    Complete SEL journey overview showing progress across all 5 categories.

    Args:
        journey: User's complete SEL journey

    Returns:
        Div containing journey overview with all category cards
    """
    # Get recommended next category
    next_category = journey.get_next_recommended_category()

    return Div(
        # Header
        Div(
            H1("Your SEL Journey", cls="text-2xl font-bold"),
            P(
                "Social Emotional Learning: Build competencies across 5 core areas",
                cls="text-lg text-gray-500",
            ),
            # Overall progress
            Div(
                P(
                    f"Overall Completion: {journey.overall_completion:.0f}%",
                    cls="text-sm text-gray-500 mb-2",
                ),
                Progress(
                    value=int(journey.overall_completion), max=100, cls="progress progress-primary"
                ),
                cls="mt-4",
            ),
            cls="mb-8",
        ),
        # Recommended next category callout
        Div(
            P(
                f"Recommended Focus: {next_category.value.replace('_', ' ').title()} "
                # Use enum helper for icon
                f"{get_sel_icon(next_category.value)}",
                cls="m-0",
            ),
            cls="alert alert-info mb-4",
        ),
        # Category cards grid
        H2("Your Progress by Category", cls="text-xl font-semibold mb-4"),
        Div(
            *[
                Div(SELCategoryCard(category, progress))
                for category, progress in journey.category_progress.items()
            ],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
        cls="container mx-auto max-w-6xl p-4",
    )
