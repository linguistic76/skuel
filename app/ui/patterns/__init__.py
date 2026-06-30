"""UI Patterns - Composed components built from primitives."""

from ui.patterns.activity_form_helper import render_activity_form
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_empty_state_with_error, render_error_banner
from ui.patterns.form_generator import FormGenerator
from ui.patterns.hub import HubCard, HubCardData, HubSection
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.patterns.setting_toggle import SettingToggle
from ui.patterns.stats_grid import IconStat, StatCard, StatsGrid

__all__ = [
    "CardGenerator",
    "EmptyState",
    "FormGenerator",
    "HubCard",
    "HubCardData",
    "HubSection",
    "IconStat",
    "PageHeader",
    "SectionHeader",
    "SettingToggle",
    "StatCard",
    "StatsGrid",
    "content_loading_placeholder",
    "render_activity_form",
    "render_empty_state_with_error",
    "render_error_banner",
]
