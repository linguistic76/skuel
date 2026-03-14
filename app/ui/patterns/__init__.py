"""UI Patterns - Composed components built from primitives."""

from ui.patterns.empty_state import EmptyState
from ui.patterns.entity_card import EntityCard
from ui.patterns.form_generator import FormGenerator
from ui.patterns.page_header import PageHeader
from ui.patterns.progress_metric import ProgressMetric
from ui.patterns.recommendation_card import RecommendationCard
from ui.patterns.section_header import SectionHeader
from ui.patterns.setting_toggle import SettingToggle
from ui.patterns.stats_grid import StatCard, StatsGrid

__all__ = [
    "EmptyState",
    "EntityCard",
    "FormGenerator",
    "PageHeader",
    "ProgressMetric",
    "RecommendationCard",
    "SectionHeader",
    "SettingToggle",
    "StatCard",
    "StatsGrid",
]
