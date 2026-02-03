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

__version__ = "2.0"

from typing import Any

from fasthtml.common import H1, H2, P

from core.models.ku.ku import Ku
from core.models.sel import SELCategoryProgress, SELJourney
from core.models.shared_enums import SELCategory
from core.ui.daisy_components import Div, Progress, Span
from core.ui.enum_helpers import get_sel_icon
from core.utils.logging import get_logger
from ui.patterns.entity_card import CardConfig, EntityCard
from ui.primitives.badge import Badge
from ui.primitives.button import ButtonLink

logger = get_logger(__name__)


# ============================================================================
# SEL CATEGORY CARD
# ============================================================================


def SELCategoryCard(category: SELCategory, progress: SELCategoryProgress) -> Any:
    """
    DaisyUI Card for one SEL category showing progress.

    Migrated to use EntityCard pattern with custom progress bar.

    Args:
        category: SEL category
        progress: User's progress in this category

    Returns:
        Div containing EntityCard with progress visualization
    """
    # Build category title with icon
    category_title = f"{get_sel_icon(category.value)} {category.value.replace('_', ' ').title()}"

    # Metadata for the card
    metadata = [
        f"{progress.kus_mastered} mastered",
        f"{progress.kus_in_progress} in progress",
        f"{progress.kus_available} available",
    ]

    # Create entity card
    card = EntityCard(
        title=category_title,
        description=category.get_description(),
        status=None,
        priority=None,
        metadata=metadata,
        actions=ButtonLink(
            "Continue Learning →",
            href=f"/sel/{category.value.replace('_', '-')}",
            variant="primary",
            full_width=True,
        ),
        config=CardConfig.default(),
    )

    # Add custom progress bar below the card
    progress_section = Div(
        Progress(
            value=progress.kus_mastered,
            max=progress.total_kus,
            cls="progress progress-primary w-full",
        ),
        P(
            f"{progress.completion_percentage:.0f}% complete",
            cls="text-sm text-base-content/70 mt-1 text-center",
        ),
        cls="mt-3",
    )

    return Div(card, progress_section, cls="mb-4")


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


def AdaptiveKUCard(ku: Ku, prerequisites_met: bool = True) -> Any:
    """
    Card for one Knowledge Unit in adaptive curriculum.

    Migrated to use EntityCard pattern.

    Args:
        ku: Knowledge unit to display
        prerequisites_met: Whether prerequisites are met (default True)

    Returns:
        EntityCard component
    """
    # Build metadata list
    metadata = []

    # Time estimate
    if hasattr(ku, "estimated_time_minutes") and ku.estimated_time_minutes:
        metadata.append(f"⏱ {ku.estimated_time_minutes} min")

    # Difficulty rating
    if hasattr(ku, "difficulty_rating") and ku.difficulty_rating is not None:
        metadata.append(f"🎯 {ku.difficulty_rating:.1f}/1.0 difficulty")

    # Learning level badge
    if hasattr(ku, "learning_level") and ku.learning_level:
        metadata.append(Badge(ku.learning_level.value.title(), variant="default"))

    # Prerequisites status badge
    if prerequisites_met:
        metadata.append(Badge("✓ Prerequisites met", variant="success"))
    else:
        metadata.append(Badge("Prerequisites needed", variant="warning"))

    # Truncate description
    description = ku.content[:150] + "..." if len(ku.content) > 150 else ku.content

    return EntityCard(
        title=ku.title,
        description=description,
        status=None,
        priority=None,
        metadata=metadata,
        actions=ButtonLink(
            "Start Learning →",
            href=f"/knowledge/{ku.uid}",
            variant="primary",
            full_width=True,
        ),
        config=CardConfig.default(),
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
