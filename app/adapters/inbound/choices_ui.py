"""Choices UI routes.

Provides the read-focused choice list view at /choices and detail view at /choices/detail.
Choices enter via YAML upload; this UI shows them with status controls,
decision framework, options, cross-domain connections, and EntityRelationshipsSection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from core.utils.connection_fetcher import CHOICE_CONNECTION_CONFIG
from core.utils.entity_filters import filter_choices
from ui.activities.choices_views import ChoiceDetailView, ChoiceList, ChoiceStatsBar
from ui.activities.filter_bar import FILTER_CONFIGS

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.choices_service import ChoicesService


def create_choices_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    choices_service: ChoicesService,
) -> list[Any]:
    """Register Choices UI routes."""
    config = ActivityUIConfig(
        domain_name="choices",
        domain_singular="choice",
        page_title="Choices",
        filter_params=(("status", "pending"), ("sort_by", "deadline")),
        get_all=choices_service.get_user_choices,
        get_one=choices_service.get_choice,
        backend=choices_service.core.backend,
        filter_fn=filter_choices,
        connection_config=CHOICE_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["choices"],
        list_component=ChoiceList,
        stats_component=ChoiceStatsBar,
        detail_component=ChoiceDetailView,
    )
    return create_activity_ui_routes(app, rt, config)
