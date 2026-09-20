"""
Curriculum Adaptive Components
===============================

Tailwind components for adaptive curriculum delivery — the HTMX fragments
served by ``/api/path-steps/journey-html`` and ``/api/path-steps/curriculum-html/{category}``.
Staged: no page loads them yet (docs/roadmap/sel-journey-fragments-staged.md).
A host page supplies a ``#curriculum-list`` target; a category card's button
loads that category's curriculum fragment into it.

Components:
- SELCategoryCard: Progress card for one SEL category
- AdaptiveKUCard: Card for one PathStep in the personalized curriculum
- SELJourneyOverview: Complete journey across all 5 categories
"""

from fasthtml.common import FT, Div, P

from core.models.enums import SELCategory
from core.models.pathways.learning_progress import CurriculumProgress, LearningJourney
from core.models.pathways.path_step import PathStep
from ui.components import ButtonT
from ui.enum_helpers import get_sel_icon
from ui.feedback import Alert, AlertT, Badge, BadgeT, Progress
from ui.patterns.card_generator import CardGenerator
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.primitives import ButtonLink


def SELCategoryCard(category: SELCategory, progress: CurriculumProgress) -> FT:
    """Card showing progress in one SEL category."""
    category_title = f"{get_sel_icon(category.value)} {category.value.replace('_', ' ').title()}"

    metadata = [
        f"{progress.steps_mastered} mastered",
        f"{progress.steps_available} available",
    ]

    card = CardGenerator.from_dataclass(
        {"title": category_title, "description": category.get_description()},
        display_fields=["description"],
        show_labels=False,
        metadata=metadata,
        actions=ButtonLink(
            "Continue Learning →",
            href=f"/api/path-steps/curriculum-html/{category.value}",
            hx_get=f"/api/path-steps/curriculum-html/{category.value}",
            hx_target="#curriculum-list",
            hx_swap="innerHTML",
            cls=(ButtonT.primary, "w-full"),
        ),
    )

    # An empty category has nothing to divide by: the bar reads 0 of 1.
    progress_section = Div(
        Progress(
            value=progress.steps_mastered,
            max_val=max(progress.total_steps, 1),
            cls="w-full",
        ),
        P(
            f"{progress.completion_percentage:.0f}% complete",
            cls="text-sm text-muted-foreground mt-1 text-center",
        ),
        cls="mt-3",
    )

    return Div(card, progress_section, cls="mb-4")


def AdaptiveKUCard(step: PathStep, prerequisites_met: bool = True) -> FT:
    """Card for one PathStep in the personalized curriculum."""
    metadata: list[str | FT] = [
        f"⏱ {step.estimated_time_minutes} min",
        f"🎯 {step.difficulty_rating:.1f}/1.0 difficulty",
        Badge(step.learning_level.value.title(), variant=BadgeT.neutral),
    ]

    if prerequisites_met:
        metadata.append(Badge("✓ Prerequisites met", variant=BadgeT.success))
    else:
        metadata.append(Badge("Prerequisites needed", variant=BadgeT.warning))

    return CardGenerator.from_dataclass(
        {"title": step.title, "description": step.get_summary()},
        display_fields=["description"],
        show_labels=False,
        metadata=metadata,
        actions=ButtonLink(
            "Start Learning →",
            href=f"/explore/ps/{step.uid}",
            cls=(ButtonT.primary, "w-full"),
        ),
    )


def SELJourneyOverview(journey: LearningJourney) -> Div:
    """Complete SEL journey overview showing progress across all 5 categories."""
    next_category = journey.get_next_recommended_category()

    return Div(
        PageHeader(
            "Your Learning Journey",
            subtitle="Social Emotional Learning: Build competencies across 5 core areas",
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
            cls="mb-4",
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
        SectionHeader("Your Progress by Category"),
        Div(
            *[
                Div(SELCategoryCard(category, progress))
                for category, progress in journey.category_progress.items()
            ],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
    )


__all__ = ["SELCategoryCard", "AdaptiveKUCard", "SELJourneyOverview"]
