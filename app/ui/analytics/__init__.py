"""SKUEL Analytics UI Components."""

from ui.analytics.dashboard import (
    render_analytics_dashboard,
    render_analytics_result,
    render_period_fields,
)
from ui.analytics.domain_metrics import render_metrics_cards
from ui.analytics.life_path import render_life_path_alignment_dashboard
from ui.analytics.life_summary import render_weekly_life_summary

__all__ = [
    "render_analytics_dashboard",
    "render_analytics_result",
    "render_life_path_alignment_dashboard",
    "render_metrics_cards",
    "render_period_fields",
    "render_weekly_life_summary",
]
