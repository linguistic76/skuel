"""Insights filter parsing, application, and query string building."""

from dataclasses import dataclass
from typing import Any

from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories import parse_int_query_param


@dataclass
class InsightsFilters:
    """Typed filters for insights list queries."""

    domain: str | None
    impact: str | None
    search: str
    insight_type: str | None
    action_status: str | None
    offset: int


def parse_insights_filters(request: Request) -> InsightsFilters:
    """
    Extract insights filter parameters from request query params.

    Args:
        request: Starlette request object

    Returns:
        Typed InsightsFilters with defaults applied
    """
    offset = parse_int_query_param(request.query_params, "offset", 0, minimum=0)

    return InsightsFilters(
        domain=request.query_params.get("domain"),
        impact=request.query_params.get("impact"),
        search=request.query_params.get("search", ""),
        insight_type=request.query_params.get("type"),
        action_status=request.query_params.get("status"),
        offset=offset,
    )


def filter_insights(insights: list[Any], filters: InsightsFilters) -> list[Any]:
    """Apply client-side filters to a list of insights.

    Delegates to InsightStore.filter_insights for the actual filtering logic.
    Used by both the main dashboard and load-more HTMX endpoint.
    """
    from core.services.insight import InsightStore

    return InsightStore.filter_insights(
        insights,
        impact=filters.impact,
        insight_type=filters.insight_type,
        action_status=filters.action_status,
        search=filters.search or None,
    )


def build_filter_query_string(filters: InsightsFilters) -> str:
    """Build URL query string from insight filters."""
    params = []
    if filters.domain:
        params.append(f"domain={filters.domain}")
    if filters.impact:
        params.append(f"impact={filters.impact}")
    if filters.search:
        params.append(f"search={filters.search}")
    if filters.insight_type:
        params.append(f"type={filters.insight_type}")
    if filters.action_status:
        params.append(f"status={filters.action_status}")
    return "&".join(params)
