"""Config-driven filter bar for Activity Domain list views.

Eliminates 6 near-identical XyzFilterBar() functions with a single
data-driven component. Each domain provides filter/sort configs;
the component handles rendering and HTMX wiring.

Usage:
    from ui.activities.filter_bar import ActivityFilterBar, FilterBarConfig, FilterSelect

    TASKS_FILTER_CONFIG = FilterBarConfig(
        fragment_url="/tasks/list-fragment",
        list_target_id="task-list",
        filters=[
            FilterSelect(
                name="status", label="Status",
                options=[("Active", "active"), ("Completed", "completed"), ("All", "all")],
                default="active",
            ),
        ],
        sort_options=[("Priority", "priority"), ("Title", "title")],
        sort_default="priority",
    )

    ActivityFilterBar(TASKS_FILTER_CONFIG, current_values={"status": "active", "sort_by": "priority"})
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fasthtml.common import Div, Form, Option

from ui.forms.components import LabelSelect

if TYPE_CHECKING:
    from fasthtml.common import FT


@dataclass(frozen=True)
class FilterSelect:
    """Configuration for a single filter dropdown.

    Attributes:
        name: Query parameter name (e.g. "status", "priority", "category").
        label: Display label for the dropdown.
        options: List of (display_text, value) tuples.
        default: Default selected value.
    """

    name: str
    label: str
    options: list[tuple[str, str]]
    default: str = "all"


@dataclass(frozen=True)
class FilterBarConfig:
    """Full configuration for a domain's filter bar.

    Attributes:
        fragment_url: HTMX GET url for list fragment (e.g. "/tasks/list-fragment").
        list_target_id: HTML id of the list container (e.g. "task-list").
        filters: Ordered list of filter dropdowns to render.
        sort_options: List of (display_text, value) tuples for the Sort dropdown.
        sort_default: Default sort value.
        columns: Responsive grid columns for sm+ breakpoint. Defaults to
            total number of dropdowns (filters + sort).
    """

    fragment_url: str
    list_target_id: str
    filters: list[FilterSelect] = field(default_factory=list)
    sort_options: list[tuple[str, str]] = field(default_factory=list)
    sort_default: str = "title"
    columns: int | None = None


def ActivityFilterBar(
    config: FilterBarConfig,
    current_values: dict[str, str] | None = None,
) -> "FT":
    """Render a config-driven filter bar for any Activity Domain.

    Args:
        config: Domain filter bar configuration.
        current_values: Current filter values from query params. Keys are
            filter names + "sort_by". Missing keys use defaults from config.
    """
    values = current_values or {}

    selects: list[FT] = []

    for f in config.filters:
        selected = values.get(f.name, f.default)
        selects.append(
            LabelSelect(
                *[Option(text, value=val, selected=selected == val) for text, val in f.options],
                label=f.label,
                name=f.name,
            )
        )

    if config.sort_options:
        sort_selected = values.get("sort_by", config.sort_default)
        selects.append(
            LabelSelect(
                *[
                    Option(text, value=val, selected=sort_selected == val)
                    for text, val in config.sort_options
                ],
                label="Sort",
                name="sort_by",
            )
        )

    sm_cols = config.columns if config.columns is not None else len(selects)

    return Form(
        Div(
            *selects,
            cls=f"grid grid-cols-1 sm:grid-cols-{sm_cols} gap-2",
        ),
        hx_get=config.fragment_url,
        hx_target=f"#{config.list_target_id}",
        hx_trigger="change",
        hx_include="[name]",
        cls="mb-4",
    )
