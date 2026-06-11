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

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from fasthtml.common import Div, Form, Label, Option, Select

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


def with_user_categories(
    config: FilterBarConfig,
    categories: list[str] | None,
) -> FilterBarConfig:
    """Rebuild the "category" dropdown from the user's live category values.

    Sourced from ``service.search.list_user_categories(user_uid)`` — distinct
    category values actually present on the user's entities, instead of a
    hardcoded enum list full of options that match nothing.

    Behavior:
        - ``categories is None`` (fetch failed): return ``config`` unchanged —
          conservative static fallback.
        - 0-1 distinct categories: drop the category dropdown entirely
          (a filter that cannot narrow anything is noise).
        - 2+ categories: replace the existing "category" dropdown in place
          (or insert one before Sort if the domain had none) with
          "All" + the live values.

    Args:
        config: The domain's static FilterBarConfig.
        categories: Live category values for this user, or None on fetch failure.

    Returns:
        A FilterBarConfig copy with the category dropdown rebuilt.
    """
    if categories is None:
        return config

    others = [f for f in config.filters if f.name != "category"]
    if len(categories) < 2:
        return replace(config, filters=others, columns=None)

    options = [("All", "all")] + [
        (value.replace("_", " ").title(), value) for value in sorted(categories)
    ]
    category_select = FilterSelect(name="category", label="Category", options=options)

    new_filters = list(config.filters)
    existing_idx = next((i for i, f in enumerate(new_filters) if f.name == "category"), None)
    if existing_idx is None:
        new_filters.append(category_select)
    else:
        new_filters[existing_idx] = category_select

    return replace(config, filters=new_filters, columns=None)


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
            Div(
                Label(f.label, cls="block text-sm font-medium text-muted-foreground mb-1"),
                Select(
                    *[Option(text, value=val, selected=selected == val) for text, val in f.options],
                    name=f.name,
                    cls="uk-select w-full",
                ),
            )
        )

    if config.sort_options:
        sort_selected = values.get("sort_by", config.sort_default)
        selects.append(
            Div(
                Label("Sort", cls="block text-sm font-medium text-muted-foreground mb-1"),
                Select(
                    *[
                        Option(text, value=val, selected=sort_selected == val)
                        for text, val in config.sort_options
                    ],
                    name="sort_by",
                    cls="uk-select w-full",
                ),
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


# All 6 Activity Domain filter bar configurations.
# Centralised here so any code that needs to enumerate or look up configs by domain
# slug can import this dict rather than reaching into individual view files.
FILTER_CONFIGS: dict[str, FilterBarConfig] = {
    "tasks": FilterBarConfig(
        fragment_url="/tasks/list-fragment",
        list_target_id="task-list",
        filters=[
            FilterSelect(
                name="status",
                label="Status",
                options=[
                    ("Active", "active"),
                    ("Completed", "completed"),
                    ("Overdue", "overdue"),
                    ("All", "all"),
                ],
                default="active",
            ),
            FilterSelect(
                name="priority",
                label="Priority",
                options=[
                    ("All", "all"),
                    ("Critical", "critical"),
                    ("High", "high"),
                    ("Medium", "medium"),
                    ("Low", "low"),
                ],
                default="all",
            ),
        ],
        sort_options=[
            ("Priority", "priority"),
            ("Due Date", "due_date"),
            ("Recently Updated", "updated"),
            ("Title", "title"),
        ],
        sort_default="priority",
    ),
    "goals": FilterBarConfig(
        fragment_url="/goals/list-fragment",
        list_target_id="goal-list",
        filters=[
            FilterSelect(
                name="status",
                label="Status",
                options=[
                    ("Active", "active"),
                    ("On Track", "on_track"),
                    ("Wobbly", "wobbly"),
                    ("Completed", "completed"),
                    ("All", "all"),
                ],
                default="active",
            ),
        ],
        sort_options=[
            ("Target Date", "target_date"),
            ("Priority", "priority"),
            ("Progress", "progress"),
            ("Title", "title"),
        ],
        sort_default="target_date",
    ),
    "habits": FilterBarConfig(
        fragment_url="/habits/list-fragment",
        list_target_id="habit-list",
        filters=[
            FilterSelect(
                name="status",
                label="Status",
                options=[
                    ("Active", "active"),
                    ("Paused", "paused"),
                    ("Completed", "completed"),
                    ("Keystone", "keystone"),
                    ("All", "all"),
                ],
                default="active",
            ),
            FilterSelect(
                name="category",
                label="Category",
                options=[
                    ("All", "all"),
                    ("Health", "health"),
                    ("Fitness", "fitness"),
                    ("Mindfulness", "mindfulness"),
                    ("Learning", "learning"),
                    ("Productivity", "productivity"),
                    ("Creative", "creative"),
                    ("Social", "social"),
                    ("Financial", "financial"),
                ],
                default="all",
            ),
        ],
        sort_options=[
            ("Streak", "streak"),
            ("Name", "name"),
            ("Recently Created", "created"),
        ],
        sort_default="streak",
    ),
    "events": FilterBarConfig(
        fragment_url="/events/list-fragment",
        list_target_id="event-list",
        filters=[
            FilterSelect(
                name="status",
                label="Status",
                options=[
                    ("Upcoming", "upcoming"),
                    ("Today", "today"),
                    ("Completed", "completed"),
                    ("All", "all"),
                ],
                default="upcoming",
            ),
        ],
        sort_options=[
            ("Date", "date"),
            ("Title", "title"),
            ("Recently Created", "created"),
        ],
        sort_default="date",
    ),
    "choices": FilterBarConfig(
        fragment_url="/choices/list-fragment",
        list_target_id="choice-list",
        filters=[
            FilterSelect(
                name="status",
                label="Status",
                options=[
                    ("Pending", "pending"),
                    ("Decided", "decided"),
                    ("All", "all"),
                ],
                default="pending",
            ),
        ],
        sort_options=[
            ("Deadline", "deadline"),
            ("Priority", "priority"),
            ("Recently Created", "created"),
            ("Title", "title"),
        ],
        sort_default="deadline",
    ),
    "principles": FilterBarConfig(
        fragment_url="/principles/list-fragment",
        list_target_id="principle-list",
        filters=[
            FilterSelect(
                name="status",
                label="Status",
                options=[("Active", "active"), ("All", "all")],
                default="active",
            ),
            FilterSelect(
                name="category",
                label="Category",
                options=[
                    ("All", "all"),
                    ("Spiritual", "spiritual"),
                    ("Ethical", "ethical"),
                    ("Relational", "relational"),
                    ("Personal", "personal"),
                    ("Professional", "professional"),
                    ("Intellectual", "intellectual"),
                    ("Health", "health"),
                    ("Creative", "creative"),
                ],
                default="all",
            ),
            FilterSelect(
                name="strength",
                label="Strength",
                options=[
                    ("All", "all"),
                    ("Core", "core"),
                    ("Strong", "strong"),
                    ("Moderate", "moderate"),
                    ("Developing", "developing"),
                    ("Exploring", "exploring"),
                ],
                default="all",
            ),
        ],
        sort_options=[
            ("Strength", "strength"),
            ("Name", "name"),
            ("Recently Created", "created"),
        ],
        sort_default="strength",
        columns=4,
    ),
}
