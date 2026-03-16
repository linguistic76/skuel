"""Curriculum UI components — domain card grid and sidebar."""

from ui.curriculum.landing import CurriculumLandingView
from ui.curriculum.layout import create_curriculum_page
from ui.curriculum.sidebar import CURRICULUM_SIDEBAR_ITEMS

__all__ = [
    "CURRICULUM_SIDEBAR_ITEMS",
    "CurriculumLandingView",
    "create_curriculum_page",
]
