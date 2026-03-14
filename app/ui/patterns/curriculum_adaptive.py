"""
Curriculum Adaptive Components
===============================

MonsterUI/Tailwind components for adaptive curriculum delivery.
Display curriculum content organized by SEL categories.

Components:
- SELCategoryCard: Progress card for one SEL category
- AdaptiveKUCard: Card for one KU in personalized curriculum
- SELJourneyOverview: Complete journey across all 5 categories
"""

from typing import Any

from fasthtml.common import H1, H2, Div, P

from core.models.entity_types import CurriculumEntity
from core.models.enums import SELCategory
from core.models.pathways.learning_progress import CurriculumProgress, LearningJourney
from ui.buttons import ButtonLink, ButtonT
from ui.enum_helpers import get_sel_icon
from ui.feedback import Alert, AlertT, Badge, BadgeT, Progress
from ui.patterns.entity_card import CardConfig, EntityCard


def SELCategoryCard(category: SELCategory, progress: CurriculumProgress) -> Any:
    """Card showing progress in one SEL category."""
    category_title = f"{get_sel_icon(category.value)} {category.value.replace('_', ' ').title()}"

    metadata = [
        f"{progress.lessons_mastered} mastered",
        f"{progress.lessons_in_progress} in progress",
        f"{progress.lessons_available} available",
    ]

    card = EntityCard(
        title=category_title,
        description=category.get_description(),
        status=None,
        priority=None,
        metadata=metadata,
        actions=ButtonLink(
            "Continue Learning →",
            href=f"/lessons?sel={category.value}",
            variant=ButtonT.primary,
            cls="w-full",
        ),
        config=CardConfig.default(),
    )

    progress_section = Div(
        Progress(
            value=progress.lessons_mastered,
            max_val=progress.total_lessons,
            cls="w-full",
        ),
        P(
            f"{progress.completion_percentage:.0f}% complete",
            cls="text-sm text-muted-foreground mt-1 text-center",
        ),
        cls="mt-3",
    )

    return Div(card, progress_section, cls="mb-4")


def AdaptiveKUCard(ku: CurriculumEntity, prerequisites_met: bool = True) -> Any:
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
        metadata.append(Badge(learning_level.value.title(), variant=BadgeT.neutral))

    if prerequisites_met:
        metadata.append(Badge("✓ Prerequisites met", variant=BadgeT.success))
    else:
        metadata.append(Badge("Prerequisites needed", variant=BadgeT.warning))

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
            variant=ButtonT.primary,
            cls="w-full",
        ),
        config=CardConfig.default(),
    )


def SELJourneyOverview(journey: LearningJourney) -> Div:
    """Complete SEL journey overview showing progress across all 5 categories."""
    next_category = journey.get_next_recommended_category()

    return Div(
        Div(
            H1("Your Learning Journey", cls="text-2xl font-bold"),
            P(
                "Social Emotional Learning: Build competencies across 5 core areas",
                cls="text-lg text-muted-foreground",
            ),
            Div(
                P(
                    f"Overall Completion: {journey.overall_completion:.0f}%",
                    cls="text-sm text-muted-foreground mb-2",
                ),
                Progress(
                    value=int(journey.overall_completion),
                    max_val=100,
                    cls="",
                ),
                cls="mt-4",
            ),
            cls="mb-8",
        ),
        Alert(
            P(
                f"Recommended Focus: {next_category.value.replace('_', ' ').title()} "
                f"{get_sel_icon(next_category.value)}",
                cls="m-0",
            ),
            variant=AlertT.info,
            cls="mb-4",
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
