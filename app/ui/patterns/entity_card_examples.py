"""EntityCard variant usage examples.

Demonstrates how to use CardVariant and CardConfig with EntityCard
across different UI contexts (lists, sidebars, featured content).

Phase 3, Task 4: Component Variant System
"""

from ui.patterns.entity_card import CardConfig, CardVariant, EntityCard


def example_default_card():
    """Standard card for main content lists."""
    return EntityCard(
        title="Complete quarterly planning document",
        description="Draft and finalize the Q4 planning document with team input and executive review.",
        status="in_progress",
        priority="high",
        metadata=["Due: Dec 15, 2024", "Project: Q4 Planning", "Team: Leadership"],
        config=CardConfig.default(),  # Explicit config (optional - this is the default)
    )


def example_compact_card():
    """Compact card for sidebars and mobile views."""
    return EntityCard(
        title="Complete quarterly planning document",
        description="This won't show in compact mode",  # Hidden by config
        status="in_progress",
        priority="high",
        metadata=["This won't show either"],  # Hidden by config
        config=CardConfig.compact(),
    )


def example_highlighted_card():
    """Highlighted card for pinned or featured items."""
    return EntityCard(
        title="URGENT: Board meeting preparation",
        description="Prepare presentation materials and talking points for tomorrow's board meeting.",
        status="active",
        priority="critical",
        metadata=["Due: Tomorrow 9 AM", "Location: Conference Room A"],
        config=CardConfig.highlighted(),
    )


def example_custom_config():
    """Custom configuration for specific needs."""
    custom_config = CardConfig(
        variant=CardVariant.DEFAULT,
        show_description=True,
        description_lines=3,  # Show 3 lines instead of default 2
        padding_cls="p-5",  # Extra padding
        border_cls="border-l-4 border-warning",  # Custom border
    )

    return EntityCard(
        title="Review architecture documentation",
        description="Complete review of system architecture docs with focus on API design patterns and database schemas. Provide feedback on clarity and completeness.",
        status="active",
        priority="medium",
        config=custom_config,
    )


def example_sidebar_widget():
    """Example: Recent tasks widget in sidebar."""
    recent_tasks = [
        {"title": "Complete proposal", "status": "active", "priority": "high"},
        {"title": "Review PR #123", "status": "active", "priority": "medium"},
        {"title": "Update documentation", "status": "active", "priority": "low"},
    ]

    # Render compact cards for sidebar
    return [
        EntityCard(
            title=task["title"],
            status=task["status"],
            priority=task["priority"],
            config=CardConfig.compact(),
        )
        for task in recent_tasks
    ]


def example_pinned_items_section():
    """Example: Pinned items with highlighted cards."""
    pinned_items = [
        {
            "title": "Critical: Production deployment",
            "description": "Deploy v2.0 to production servers",
            "priority": "critical",
        },
        {
            "title": "Important: Client meeting",
            "description": "Quarterly review with top client",
            "priority": "high",
        },
    ]

    # Render highlighted cards for pinned items
    return [
        EntityCard(
            title=item["title"],
            description=item["description"],
            priority=item["priority"],
            status="active",
            config=CardConfig.highlighted(),
        )
        for item in pinned_items
    ]


def example_responsive_cards(is_mobile: bool):
    """Example: Responsive cards based on screen size."""
    task = {
        "title": "Complete project milestone",
        "description": "Finish all tasks for Sprint 23 milestone",
        "status": "in_progress",
        "priority": "high",
        "metadata": ["Due: Friday", "Sprint 23"],
    }

    # Use compact on mobile, default on desktop
    config = CardConfig.compact() if is_mobile else CardConfig.default()

    return EntityCard(
        title=task["title"],
        description=task["description"],
        status=task["status"],
        priority=task["priority"],
        metadata=task["metadata"],
        config=config,
    )


# ============================================================================
# USAGE PATTERNS
# ============================================================================

"""
Common Usage Patterns:

1. Main Content List (DEFAULT):
   cards = [
       EntityCard(title=item.title, description=item.desc, config=CardConfig.default())
       for item in items
   ]

2. Sidebar Widget (COMPACT):
   recent = [
       EntityCard(title=task.title, status=task.status, config=CardConfig.compact())
       for task in recent_tasks[:5]
   ]

3. Featured Section (HIGHLIGHTED):
   featured = [
       EntityCard(title=item.title, description=item.desc, config=CardConfig.highlighted())
       for item in featured_items
   ]

4. Responsive (COMPACT on mobile, DEFAULT on desktop):
   config = CardConfig.compact() if is_mobile else CardConfig.default()
   card = EntityCard(title=item.title, config=config)

5. Custom Variant:
   custom = CardConfig(
       variant=CardVariant.DEFAULT,
       description_lines=3,
       padding_cls="p-6",
   )
   card = EntityCard(title=item.title, config=custom)
"""
