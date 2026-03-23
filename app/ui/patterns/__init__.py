"""UI Patterns - Composed components built from primitives."""

from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_empty_state_with_error, render_error_banner
from ui.patterns.form_generator import FormGenerator
from ui.patterns.page_header import PageHeader
from ui.patterns.progress_metric import ProgressMetric
from ui.patterns.section_header import SectionHeader
from ui.patterns.setting_toggle import SettingToggle
from ui.patterns.stats_grid import StatCard, StatsGrid

__all__ = [
    "CardGenerator",
    "EmptyState",
    "FormGenerator",
    "PageHeader",
    "ProgressMetric",
    "SectionHeader",
    "SettingToggle",
    "StatCard",
    "StatsGrid",
    "render_empty_state_with_error",
    "render_error_banner",
]
