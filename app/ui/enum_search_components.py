"""
Enum-Based UI Component Generation
====================================

Auto-generate search UI components from enum methods.

This module reads enum metadata (colors, icons, synonyms, descriptions)
and generates UI-ready data structures for dropdowns, filters, and badges.

**Core Principle:** "Enums are the single source of truth for UI presentation"

Usage:
    ```python
    from ui.enum_search_components import (
        generate_priority_filter_options,
        generate_status_filter_options,
        generate_all_filter_options,
    )


    # In FastHTML route
    @rt("/search")
    def search_page():
        priority_options = generate_priority_filter_options()
        status_options = generate_status_filter_options()

        return render_search_ui(
            priority_filters=priority_options, status_filters=status_options
        )
    ```

Benefits:
    - Zero hardcoded UI dictionaries
    - UI updates automatically when enums change
    - Consistent presentation across all pages
    - Type-safe component generation
"""

from typing import Any

from core.models.enums import (
    ContentType,
    Domain,
    EducationalLevel,
    EntityStatus,
    LearningLevel,
    Priority,
    SELCategory,
)

# ============================================================================
# INDIVIDUAL ENUM FILTER GENERATORS
# ============================================================================


def generate_priority_filter_options() -> list[dict[str, Any]]:
    """
    Generate UI dropdown options for Priority enum.

    Returns:
        List of dicts with {value, label, icon, color, description}
    """
    return [
        {
            "value": p.value,
            "label": p.value.title(),
            "icon": "●",  # Default icon since Priority doesn't have get_icon()
            "color": p.get_color(),
            "description": p.get_search_description(),
            "synonyms": list(p.get_search_synonyms()),
            "numeric": p.to_numeric(),
        }
        for p in Priority
    ]


def generate_status_filter_options() -> list[dict[str, Any]]:
    """
    Generate UI dropdown options for EntityStatus enum.

    Returns:
        List of dicts with {value, label, icon, color, description, state_info}
    """
    return [
        {
            "value": s.value,
            "label": s.value.replace("_", " ").title(),
            "icon": "●",  # Default icon
            "color": s.get_color(),
            "description": s.get_search_description(),
            "synonyms": list(s.get_search_synonyms()),
            "is_terminal": s.is_terminal(),
            "is_active": s.is_active(),
            "is_pending": s.is_pending(),
        }
        for s in EntityStatus
    ]


def generate_domain_filter_options() -> list[dict[str, Any]]:
    """
    Generate UI dropdown options for Domain enum.

    Returns:
        List of dicts with {value, label, icon, description}
    """
    # Only show searchable domains (exclude system domains)
    searchable_domains = [
        Domain.KNOWLEDGE,
        Domain.TASKS,
        Domain.EVENTS,
        Domain.HABITS,
        Domain.GOALS,
        Domain.CHOICES,
        Domain.PRINCIPLES,
        Domain.REPORTS,
    ]

    return [
        {
            "value": d.value,
            "label": d.value.title(),
            "icon": _get_domain_icon(d),
            "description": f"{d.value.title()} domain",
            "synonyms": list(d.get_search_synonyms()),
        }
        for d in searchable_domains
    ]


def generate_content_type_filter_options() -> list[dict[str, Any]]:
    """
    Generate UI dropdown options for ContentType enum.

    Returns:
        List of dicts with {value, label, icon, color, description}
    """
    return [
        {
            "value": ct.value,
            "label": ct.value.title(),
            "icon": ct.get_icon(),
            "color": ct.get_color(),
            "description": ct.get_search_description(),
            "synonyms": list(ct.get_search_synonyms()),
        }
        for ct in ContentType
    ]


def generate_learning_level_filter_options() -> list[dict[str, Any]]:
    """
    Generate UI dropdown options for LearningLevel enum.

    Returns:
        List of dicts with {value, label, description, numeric}
    """
    return [
        {
            "value": ll.value,
            "label": ll.value.title(),
            "icon": "◆",  # Default icon
            "description": ll.get_search_description(),
            "synonyms": list(ll.get_search_synonyms()),
            "numeric": ll.to_numeric(),
        }
        for ll in LearningLevel
    ]


def generate_educational_level_filter_options() -> list[dict[str, Any]]:
    """
    Generate UI dropdown options for EducationalLevel enum.

    Returns:
        List of dicts with {value, label, icon, color, description, age_range}
    """

    def get_description_safe(el) -> Any:
        try:
            return el.get_description()
        except AttributeError:
            return ""

    return [
        {
            "value": el.value,
            "label": el.value.replace("_", " ").title(),
            "icon": el.get_icon(),
            "color": el.get_color(),
            "description": get_description_safe(el),
            "age_range": el.get_age_range(),
            "numeric": el.to_numeric(),
        }
        for el in EducationalLevel
    ]


def generate_sel_category_filter_options() -> list[dict[str, Any]]:
    """
    Generate UI dropdown options for SELCategory enum.

    Returns:
        List of dicts with {value, label, icon, color, description}
    """
    return [
        {
            "value": sel.value,
            "label": sel.value.replace("_", " ").title(),
            "icon": sel.get_icon(),
            "color": sel.get_color(),
            "description": sel.get_description(),
        }
        for sel in SELCategory
    ]


# ============================================================================
# COMBINED FILTER GENERATORS
# ============================================================================


def generate_all_filter_options() -> dict[str, list[dict[str, Any]]]:
    """
    Generate all filter options in one call.

    Returns:
        Dict mapping filter_type to list of options:
        {
            'priority': [...],
            'status': [...],
            'domain': [...],
            'content_type': [...],
            'learning_level': [...],
            'educational_level': [...],
            'sel_category': [...]
        }
    """
    return {
        "priority": generate_priority_filter_options(),
        "status": generate_status_filter_options(),
        "domain": generate_domain_filter_options(),
        "content_type": generate_content_type_filter_options(),
        "learning_level": generate_learning_level_filter_options(),
        "educational_level": generate_educational_level_filter_options(),
        "sel_category": generate_sel_category_filter_options(),
    }


def generate_filter_options_for_domain(domain: Domain) -> dict[str, list[dict[str, Any]]]:
    """
    Generate relevant filter options for a specific domain.

    Args:
        domain: The domain to generate filters for,

    Returns:
        Dict of relevant filter options for that domain

    Examples:
        # Knowledge domain
        >>> filters = generate_filter_options_for_domain(Domain.KNOWLEDGE)
        >>> # Returns: sel_category, learning_level, content_type

        # Tasks domain
        >>> filters = generate_filter_options_for_domain(Domain.TASKS)
        >>> # Returns: priority, status
    """
    # Map domains to their relevant filters
    domain_filters = {
        Domain.KNOWLEDGE: ["sel_category", "learning_level", "content_type", "educational_level"],
        Domain.TASKS: ["priority", "status"],
        Domain.EVENTS: ["priority", "status"],
        Domain.HABITS: ["status"],
        Domain.GOALS: ["status"],
        Domain.CHOICES: [],
        Domain.PRINCIPLES: [],
        Domain.REPORTS: [],
    }

    # Get all filter options
    all_filters = generate_all_filter_options()

    # Return only relevant filters for this domain
    relevant_filter_names = domain_filters.get(domain, [])
    return {
        filter_name: all_filters[filter_name]
        for filter_name in relevant_filter_names
        if filter_name in all_filters
    }


# ============================================================================
# FACET COUNT UI GENERATORS
# ============================================================================


def generate_facet_badge_html(facet: dict[str, Any]) -> str:
    """
    Generate HTML for a single facet filter badge (for DaisyUI).

    Args:
        facet: Dict with {value, label, icon, color, count},

    Returns:
        HTML string for DaisyUI filter badge

    Example:
        >>> facet = {
        ...     "value": "high",
        ...     "label": "High",
        ...     "icon": "●",
        ...     "color": "#F59E0B",
        ...     "count": 12,
        ... }
        >>> html = generate_facet_badge_html(facet)
        >>> # <button class="btn btn-outline btn-sm" data-filter-value="high">
        >>> #   <span style="color: #F59E0B">●</span> High (12)
        >>> # </button>
    """
    return f'''
    <button class="btn btn-outline btn-sm"
            data-filter-value="{facet["value"]}"
            style="border-color: {facet.get("color", "#ccc")}">
        <span style="color: {facet.get("color", "#666")}">{facet.get("icon", "●")}</span>
        {facet["label"]}
        {f"({facet['count']})" if "count" in facet else ""}
    </button>
    '''


def generate_facet_select_html(filter_name: str, options: list[dict[str, Any]]) -> str:
    """
    Generate HTML select dropdown for a filter.

    Args:
        filter_name: Name of the filter (e.g., 'priority', 'status'),
        options: List of option dicts from generate_*_filter_options()

    Returns:
        HTML select element,

    Example:
        >>> options = generate_priority_filter_options()
        >>> html = generate_facet_select_html("priority", options)
    """
    select_html = f'<select name="{filter_name}" class="select select-bordered w-full">\n'
    select_html += f'  <option value="">All {filter_name.replace("_", " ").title()}</option>\n'

    for option in options:
        select_html += f'  <option value="{option["value"]}">'
        select_html += f"{option.get('icon', '')} {option['label']}"
        select_html += "</option>\n"

    select_html += "</select>"
    return select_html


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _get_domain_icon(domain: Domain) -> str:
    """Get icon for domain (since Domain enum doesn't have get_icon())"""
    icons = {
        Domain.KNOWLEDGE: "📚",
        Domain.TASKS: "✅",
        Domain.EVENTS: "📅",
        Domain.HABITS: "🔄",
        Domain.GOALS: "🎯",
        Domain.CHOICES: "⚖️",
        Domain.PRINCIPLES: "💎",
        Domain.REPORTS: "📄",
    }
    return icons.get(domain, "📋")


# ============================================================================
# PUBLIC API
# ============================================================================

__all__ = [
    "generate_all_filter_options",
    "generate_content_type_filter_options",
    "generate_domain_filter_options",
    "generate_educational_level_filter_options",
    "generate_facet_badge_html",
    "generate_facet_select_html",
    "generate_filter_options_for_domain",
    "generate_learning_level_filter_options",
    "generate_priority_filter_options",
    "generate_sel_category_filter_options",
    "generate_status_filter_options",
]
