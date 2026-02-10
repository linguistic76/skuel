"""
KU Adaptive Curriculum Components
=================================

DaisyUI/Tailwind components for adaptive KU curriculum delivery.
Absorbed from SEL components — these display KU content organized by SEL categories.

Components:
- SELCategoryCard: Progress card for one SEL category
- AdaptiveKUCard: Card for one KU in personalized curriculum
- SELJourneyOverview: Complete journey across all 5 categories
"""

from typing import Any

from fasthtml.common import H1, H2, P

from core.models.enums import SELCategory
from core.models.ku.ku import Ku
from core.models.ku.ku_progress import KuCategoryProgress, KuLearningJourney
from core.ui.daisy_components import Div, Progress
from core.ui.enum_helpers import get_sel_icon
from ui.patterns.entity_card import CardConfig, EntityCard
from ui.primitives.badge import Badge
from ui.primitives.button import ButtonLink


def SELCategoryCard(category: SELCategory, progress: KuCategoryProgress) -> Any:
    """Card showing progress in one SEL category."""
    category_title = f"{get_sel_icon(category.value)} {category.value.replace('_', ' ').title()}"

    metadata = [
        f"{progress.kus_mastered} mastered",
        f"{progress.kus_in_progress} in progress",
        f"{progress.kus_available} available",
    ]

    card = EntityCard(
        title=category_title,
        description=category.get_description(),
        status=None,
        priority=None,
        metadata=metadata,
        actions=ButtonLink(
            "Continue Learning →",
            href=f"/ku?sel={category.value}",
            variant="primary",
            full_width=True,
        ),
        config=CardConfig.default(),
    )

    progress_section = Div(
        Progress(
            value=progress.kus_mastered,
            max_val=progress.total_kus,
            cls="progress progress-primary w-full",
        ),
        P(
            f"{progress.completion_percentage:.0f}% complete",
            cls="text-sm text-base-content/70 mt-1 text-center",
        ),
        cls="mt-3",
    )

    return Div(card, progress_section, cls="mb-4")


def AdaptiveKUCard(ku: Ku, prerequisites_met: bool = True) -> Any:
    """Card for one KU in personalized curriculum."""
    metadata = []

    estimated_time = getattr(ku, "estimated_time_minutes", None)
    if estimated_time:
        metadata.append(f"⏱ {estimated_time} min")

    difficulty = getattr(ku, "difficulty_rating", None)
    if difficulty is not None:
        metadata.append(f"🎯 {difficulty:.1f}/1.0 difficulty")

    learning_level = getattr(ku, "learning_level", None)
    if learning_level:
        metadata.append(Badge(learning_level.value.title(), variant="default"))

    if prerequisites_met:
        metadata.append(Badge("✓ Prerequisites met", variant="success"))
    else:
        metadata.append(Badge("Prerequisites needed", variant="warning"))

    description = ku.summary[:150] + "..." if len(ku.summary) > 150 else ku.summary

    return EntityCard(
        title=ku.title,
        description=description,
        status=None,
        priority=None,
        metadata=metadata,
        actions=ButtonLink(
            "Start Learning →",
            href=f"/ku/{ku.uid}",
            variant="primary",
            full_width=True,
        ),
        config=CardConfig.default(),
    )


def SELJourneyOverview(journey: KuLearningJourney) -> Div:
    """Complete SEL journey overview showing progress across all 5 categories."""
    next_category = journey.get_next_recommended_category()

    return Div(
        Div(
            H1("Your Learning Journey", cls="text-2xl font-bold"),
            P(
                "Social Emotional Learning: Build competencies across 5 core areas",
                cls="text-lg text-base-content/70",
            ),
            Div(
                P(
                    f"Overall Completion: {journey.overall_completion:.0f}%",
                    cls="text-sm text-base-content/70 mb-2",
                ),
                Progress(
                    value=int(journey.overall_completion),
                    max_val=100,
                    cls="progress progress-primary",
                ),
                cls="mt-4",
            ),
            cls="mb-8",
        ),
        Div(
            P(
                f"Recommended Focus: {next_category.value.replace('_', ' ').title()} "
                f"{get_sel_icon(next_category.value)}",
                cls="m-0",
            ),
            cls="alert alert-info mb-4",
        ),
        H2("Your Progress by Category", cls="text-xl font-semibold mb-4"),
        Div(
            *[
                Div(SELCategoryCard(category, progress))
                for category, progress in journey.category_progress.items()
            ],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
    )


__all__ = ["SELCategoryCard", "AdaptiveKUCard", "SELJourneyOverview"]
