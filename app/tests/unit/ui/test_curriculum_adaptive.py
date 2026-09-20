"""The staged SEL journey fragments (`ui/patterns/curriculum_adaptive.py`).

No page loads these yet (docs/roadmap/sel-journey-fragments-staged.md); the pins
keep the staged code correct against the models it renders, so wiring a surface
does not start by rediscovering what a first render would have thrown.
"""

from fasthtml.common import to_xml

from core.models.enums import SELCategory
from core.models.pathways.learning_progress import CurriculumProgress, LearningJourney
from core.models.pathways.path_step import PathStep
from core.models.type_hints import UserUID
from ui.patterns.curriculum_adaptive import AdaptiveKUCard, SELCategoryCard, SELJourneyOverview

USER = UserUID("user.test")


def _progress(category: SELCategory, *, mastered: int = 0, total: int = 0) -> CurriculumProgress:
    return CurriculumProgress(
        user_uid=USER, sel_category=category, steps_mastered=mastered, total_steps=total
    )


def test_empty_category_renders_a_zero_bar_not_a_division_error() -> None:
    """A category with no steps has `total_steps == 0`; the bar must still render."""
    html = to_xml(
        SELCategoryCard(SELCategory.SELF_AWARENESS, _progress(SELCategory.SELF_AWARENESS))
    )
    assert "width:0%" in html


def test_category_card_loads_its_curriculum_fragment_into_the_host_target() -> None:
    """The continue button is the sibling fragment, HTMX-loaded into `#curriculum-list`."""
    html = to_xml(
        SELCategoryCard(
            SELCategory.SELF_MANAGEMENT,
            _progress(SELCategory.SELF_MANAGEMENT, mastered=1, total=4),
        )
    )
    assert 'hx-get="/api/path-steps/curriculum-html/self_management"' in html
    assert 'hx-target="#curriculum-list"' in html
    assert "width:25%" in html


def test_recommendation_card_links_to_the_path_step_detail_page() -> None:
    """A recommendation is a PathStep; its door is `/explore/ps/{uid}`, never the Ku route."""
    step = PathStep(uid="ps.sel.knowing-yourself", title="Knowing yourself", summary="s")
    html = to_xml(AdaptiveKUCard(step))
    assert 'href="/explore/ps/ps.sel.knowing-yourself"' in html
    assert "/explore/ku/" not in html


def test_journey_overview_renders_every_category_including_empty_ones() -> None:
    journey = LearningJourney(
        user_uid=USER,
        category_progress={c: _progress(c) for c in SELCategory},
        overall_completion=0.0,
    )
    html = to_xml(SELJourneyOverview(journey))
    for category in SELCategory:
        assert f"/api/path-steps/curriculum-html/{category.value}" in html
