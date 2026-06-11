"""
Unit tests for live category filter options on Activity list pages.

`with_user_categories` rebuilds a FilterBarConfig's Category dropdown from the
user's distinct category values (`service.search.list_user_categories`):

- None (fetch failed)  → config unchanged (conservative static fallback)
- 0-1 categories       → category dropdown dropped (cannot narrow anything)
- 2+ categories        → "All" + live values, replacing the static enum list
  (or inserted for domains like Goals that had no static category dropdown)
"""

from fasthtml.common import to_xml

from ui.activities.filter_bar import (
    FILTER_CONFIGS,
    ActivityFilterBar,
    with_user_categories,
)


def _filter_names(config) -> list[str]:
    return [f.name for f in config.filters]


def test_none_keeps_static_config_unchanged() -> None:
    config = FILTER_CONFIGS["habits"]
    assert with_user_categories(config, None) is config


def test_zero_categories_drops_dropdown() -> None:
    rebuilt = with_user_categories(FILTER_CONFIGS["habits"], [])
    assert "category" not in _filter_names(rebuilt)
    assert "status" in _filter_names(rebuilt)


def test_single_category_drops_dropdown() -> None:
    rebuilt = with_user_categories(FILTER_CONFIGS["principles"], ["ethical"])
    assert "category" not in _filter_names(rebuilt)
    # Other dropdowns survive.
    assert "strength" in _filter_names(rebuilt)


def test_live_categories_replace_static_options() -> None:
    rebuilt = with_user_categories(FILTER_CONFIGS["habits"], ["health", "learning"])
    category = next(f for f in rebuilt.filters if f.name == "category")
    assert category.options == [("All", "all"), ("Health", "health"), ("Learning", "learning")]
    # Position preserved (after status, like the static config).
    assert _filter_names(rebuilt) == ["status", "category"]


def test_goals_gains_category_dropdown() -> None:
    """Goals has no static category dropdown — live values insert one."""
    assert "category" not in _filter_names(FILTER_CONFIGS["goals"])
    rebuilt = with_user_categories(FILTER_CONFIGS["goals"], ["wealth", "knowledge"])
    category = next(f for f in rebuilt.filters if f.name == "category")
    assert category.options == [("All", "all"), ("Knowledge", "knowledge"), ("Wealth", "wealth")]


def test_underscored_values_get_human_labels() -> None:
    rebuilt = with_user_categories(FILTER_CONFIGS["goals"], ["personal_growth", "health"])
    category = next(f for f in rebuilt.filters if f.name == "category")
    assert ("Personal Growth", "personal_growth") in category.options


def test_filter_bar_renders_live_options() -> None:
    """The rendered list-page filter bar carries the live category options."""
    rebuilt = with_user_categories(FILTER_CONFIGS["habits"], ["health", "learning"])
    html = to_xml(ActivityFilterBar(rebuilt, {"category": "learning"}))
    assert 'value="health"' in html
    assert 'value="learning" selected' in html
    # The static enum noise (categories the user has no habits in) is gone.
    assert 'value="mindfulness"' not in html
