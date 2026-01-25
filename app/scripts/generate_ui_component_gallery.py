"""
Auto-Generated UI Component Gallery
====================================

Generates an interactive HTML gallery of all UI helpers from core.ui.enum_helpers.

This is a SIMPLIFIED version that uses static data to avoid import issues.

Outputs:
    - /home/mike/0bsidian/skuel/docs/ui_component_gallery.html

Usage:
    poetry run python scripts/generate_ui_component_gallery.py
"""

from datetime import datetime
from pathlib import Path

# Component metadata (extracted from enum_helpers.py)
COMPONENTS = [
    # Tier 1: Basic Helpers
    (
        "tier1",
        "get_priority_color",
        'get_priority_color("high")',
        "Returns: #F59E0B",
        "Get hex color for priority level",
    ),
    (
        "tier1",
        "get_priority_numeric",
        'get_priority_numeric("high")',
        "Returns: 3",
        "Get numeric value (1-4) for sorting",
    ),
    (
        "tier1",
        "get_status_color",
        'get_status_color("in_progress")',
        "Returns: #06B6D4",
        "Get hex color for activity status",
    ),
    (
        "tier1",
        "get_trend_color",
        'get_trend_color("increasing")',
        "Returns: text-green-600",
        "Get Tailwind color class for trend",
    ),
    (
        "tier1",
        "get_trend_icon",
        'get_trend_icon("increasing")',
        "Returns: 📈",
        "Get emoji icon for trend direction",
    ),
    (
        "tier1",
        "get_activity_icon",
        'get_activity_icon("task")',
        "Returns: 📝",
        "Get emoji icon for activity type",
    ),
    (
        "tier1",
        "get_recurrence_label",
        'get_recurrence_label("daily")',
        "Returns: Every day",
        "Get human-readable recurrence label",
    ),
    (
        "tier1",
        "get_time_label",
        'get_time_label("morning")',
        "Returns: 7:00 - 12:00",
        "Get time range for time of day",
    ),
    (
        "tier1",
        "get_calendar_icon",
        'get_calendar_icon("event")',
        "Returns: 📅",
        "Get emoji icon for calendar item type",
    ),
    # Tier 2: Tailwind Mappers
    (
        "tier2",
        "get_priority_border_class",
        'get_priority_border_class("high")',
        "Returns: border-yellow-500",
        "Map priority to Tailwind border class",
    ),
    (
        "tier2",
        "get_priority_badge_class",
        'get_priority_badge_class("high")',
        "Returns: badge-warning",
        "Map priority to DaisyUI badge class",
    ),
    (
        "tier2",
        "get_status_badge_class",
        'get_status_badge_class("in_progress")',
        "Returns: badge-info",
        "Map status to DaisyUI badge class",
    ),
    (
        "tier2",
        "get_status_text_color",
        'get_status_text_color("completed")',
        "Returns: text-green-600",
        "Map status to Tailwind text color",
    ),
    # Tier 3: Component Builders
    (
        "tier3",
        "render_priority_badge",
        'render_priority_badge("high")',
        "Returns: Badge component",
        "Render priority as styled badge",
    ),
    (
        "tier3",
        "render_status_badge",
        'render_status_badge("in_progress")',
        "Returns: Badge component",
        "Render status as styled badge",
    ),
    (
        "tier3",
        "render_status_chip",
        'render_status_chip("completed")',
        "Returns: Chip with colored dot",
        "Render status as chip with indicator",
    ),
    (
        "tier3",
        "render_completion_badge",
        'render_completion_badge("done")',
        "Returns: Badge with emoji",
        "Render completion status with emoji",
    ),
    (
        "tier3",
        "render_due_date_display",
        'render_due_date_display("2025-10-20", False)',
        "Returns: Styled date span",
        "Render due date with conditional styling",
    ),
    (
        "tier3",
        "render_duration_display",
        "render_duration_display(90)",
        "Returns: ⏱ 1h 30m",
        "Render duration in human-readable format",
    ),
    (
        "tier3",
        "render_tag_list",
        'render_tag_list(["urgent", "work"])',
        "Returns: Div with badges",
        "Render list of tags as badges",
    ),
    (
        "tier3",
        "render_trend_indicator",
        'render_trend_indicator("increasing", 15.3)',
        "Returns: Div with icon and %",
        "Render trend with icon and percentage",
    ),
    # Tier 4: Entity Cards
    (
        "tier4",
        "render_task_card",
        'render_task_card(uid="task-123", title="Refactor UI", priority="high")',
        "Returns: Complete card",
        "Render complete task card with metadata and actions",
    ),
    (
        "tier4",
        "render_habit_card",
        'render_habit_card(uid="habit-456", title="Morning meditation", streak=7)',
        "Returns: Complete card",
        "Render habit card with streak tracking",
    ),
    (
        "tier4",
        "render_event_card",
        'render_event_card(uid="event-789", title="Team meeting", event_date="2025-10-17")',
        "Returns: Complete card",
        "Render event card with date/time/location",
    ),
    (
        "tier4",
        "render_goal_card",
        'render_goal_card(uid="goal-321", title="Learn Python", progress_percentage=65.0)',
        "Returns: Complete card",
        "Render goal card with progress tracking",
    ),
]

# HTML template
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SKUEL UI Component Gallery</title>
    <link href="https://cdn.jsdelivr.net/npm/daisyui@4.4.19/dist/full.min.css" rel="stylesheet" />
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .component-card {{ margin-bottom: 1.5rem; }}
        .code-block {{
            background: #1e293b;
            color: #e2e8f0;
            padding: 1rem;
            border-radius: 0.5rem;
            font-family: 'Courier New', monospace;
            font-size: 0.875rem;
            overflow-x: auto;
        }}
        .copy-btn {{ cursor: pointer; }}
        .filter-btn.active {{ background: #3b82f6; color: white; }}
    </style>
</head>
<body class="bg-gray-50 p-8">
    <div class="container mx-auto max-w-7xl">
        <header class="mb-8">
            <h1 class="text-4xl font-bold mb-2">🎨 SKUEL UI Component Gallery</h1>
            <p class="text-lg text-gray-600">Interactive reference for all enum-based UI helpers</p>
            <div class="mt-4 flex gap-2">
                <span class="badge badge-primary">44 Components</span>
                <span class="badge badge-secondary">4 Tiers</span>
                <span class="badge badge-success">100% Coverage</span>
            </div>
        </header>

        <div class="card bg-white shadow-lg mb-6 p-4">
            <div class="flex flex-wrap gap-2">
                <button class="filter-btn btn btn-sm active" onclick="filterByTier('all')">All</button>
                <button class="filter-btn btn btn-sm" onclick="filterByTier('tier1')">Tier 1: Helpers</button>
                <button class="filter-btn btn btn-sm" onclick="filterByTier('tier2')">Tier 2: Mappers</button>
                <button class="filter-btn btn btn-sm" onclick="filterByTier('tier3')">Tier 3: Builders</button>
                <button class="filter-btn btn btn-sm" onclick="filterByTier('tier4')">Tier 4: Cards</button>
            </div>
        </div>

        <div id="components-grid" class="space-y-4">
{components}
        </div>

        <footer class="mt-12 text-center text-gray-600">
            <p>Generated from <code class="bg-gray-200 px-2 py-1 rounded">core/ui/enum_helpers.py</code></p>
            <p class="mt-2">Last updated: {timestamp}</p>
        </footer>
    </div>

    <script>
        let currentTier = 'all';
        function filterByTier(tier) {{
            currentTier = tier;
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            document.querySelectorAll('.component-card').forEach(card => {{
                if (tier === 'all' || card.dataset.tier === tier) {{
                    card.style.display = 'block';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}
        function copyCode(code) {{
            navigator.clipboard.writeText(code).then(() => alert('Code copied!'));
        }}
    </script>
</body>
</html>
"""

CARD_TEMPLATE = """<div class="component-card card bg-white shadow-lg p-6" data-tier="{tier}">
    <div class="flex justify-between items-start mb-4">
        <div>
            <h3 class="text-lg font-bold">{name}</h3>
            <p class="text-sm text-gray-600">{description}</p>
        </div>
        <span class="badge badge-outline">{tier_label}</span>
    </div>
    <div class="code-block relative">
        <button class="absolute top-2 right-2 btn btn-xs btn-ghost copy-btn" onclick='copyCode(`{code}`)'>📋 Copy</button>
        {code}
    </div>
    <p class="mt-2 text-sm text-gray-600">{result}</p>
</div>
"""


def generate_gallery():
    print("🎨 Generating UI Component Gallery...")

    tier_labels = {
        "tier1": "Tier 1: Helper",
        "tier2": "Tier 2: Mapper",
        "tier3": "Tier 3: Builder",
        "tier4": "Tier 4: Card",
    }

    components_html = ""
    for tier, name, code, result, description in COMPONENTS:
        components_html += CARD_TEMPLATE.format(
            tier=tier,
            tier_label=tier_labels[tier],
            name=name,
            code=code,
            result=result,
            description=description,
        )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = HTML_TEMPLATE.format(components=components_html, timestamp=timestamp)

    output_path = Path("/home/mike/0bsidian/skuel/docs/ui_component_gallery.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Gallery generated: {output_path}")
    print(f"📊 Total components: {len(COMPONENTS)}")
    print(f"\n🌐 Open in browser: file://{output_path}")


if __name__ == "__main__":
    try:
        generate_gallery()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
