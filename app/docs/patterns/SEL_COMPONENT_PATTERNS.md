---
title: SEL Component Patterns
updated: 2026-02-04
status: current
category: patterns
tags: [sel, components, entity-card, htmx, adaptive-learning]
related:
  - docs/features/SEL_ADAPTIVE_CURRICULUM.md
  - docs/patterns/UI_COMPONENT_PATTERNS.md
  - docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md
---

# SEL Component Patterns

> **Reference Implementation:** `/adapters/inbound/sel_components.py`
> **Updated:** 2026-02-03 (UX Modernization)

## Overview

Reusable component patterns for Social Emotional Learning (SEL) adaptive curriculum. These patterns demonstrate how to build curriculum interfaces using SKUEL's standard UI primitives.

## Key Patterns

### 1. Category Progress Card

**Use Case:** Display user progress in one SEL category with action button

**Pattern:**
```python
from ui.patterns.entity_card import EntityCard, CardConfig
from ui.primitives.badge import Badge
from ui.primitives.button import ButtonLink
from ui.enum_helpers import get_sel_icon

def SELCategoryCard(category: SELCategory, progress: SELCategoryProgress) -> Any:
    """SEL category card showing progress."""
    # Build title with emoji icon
    category_title = f"{get_sel_icon(category.value)} {category.value.replace('_', ' ').title()}"

    # Metadata shows progress stats
    metadata = [
        f"{progress.kus_mastered} mastered",
        f"{progress.kus_in_progress} in progress",
        f"{progress.kus_available} available",
    ]

    # EntityCard provides consistent layout
    card = EntityCard(
        title=category_title,
        description=category.get_description(),
        metadata=metadata,
        actions=ButtonLink(
            "Continue Learning →",
            href=f"/sel/{category.value.replace('_', '-')}",
            variant="primary",
            full_width=True,
        ),
        config=CardConfig.default(),
    )

    # Custom progress bar (not part of EntityCard)
    progress_section = Div(
        Progress(
            value=progress.kus_mastered,
            max_val=progress.total_kus,
            cls="progress progress-primary w-full",
        ),
        P(
            f"{progress.completion_percentage:.0f}% complete",
            cls="text-sm text-base-content/70 mt-1 text-center",
        ),
        cls="mt-3",
    )

    return Div(card, progress_section, cls="mb-4")
```

**Key Techniques:**
- ✅ Use `EntityCard` for consistent layout
- ✅ Add emoji icons to titles for visual interest
- ✅ Custom elements (progress bar) go outside EntityCard
- ✅ `full_width=True` for primary actions
- ✅ Metadata uses plain strings for simple stats

### 2. Adaptive Knowledge Unit Card

**Use Case:** Display one KU with difficulty, time, and prerequisite status

**Pattern:**
```python
def AdaptiveKUCard(ku: Ku, prerequisites_met: bool = True) -> Any:
    """Card for one Knowledge Unit in adaptive curriculum."""
    # Build metadata list dynamically
    metadata = []

    # Time estimate
    if hasattr(ku, "estimated_time_minutes") and ku.estimated_time_minutes:
        metadata.append(f"⏱ {ku.estimated_time_minutes} min")

    # Difficulty rating
    if hasattr(ku, "difficulty_rating") and ku.difficulty_rating is not None:
        metadata.append(f"🎯 {ku.difficulty_rating:.1f}/1.0 difficulty")

    # Learning level badge (component)
    if hasattr(ku, "learning_level") and ku.learning_level:
        metadata.append(Badge(ku.learning_level.value.title(), variant="default"))

    # Prerequisites status badge (component)
    if prerequisites_met:
        metadata.append(Badge("✓ Prerequisites met", variant="success"))
    else:
        metadata.append(Badge("Prerequisites needed", variant="warning"))

    # Truncate long descriptions
    description = ku.content[:150] + "..." if len(ku.content) > 150 else ku.content

    return EntityCard(
        title=ku.title,
        description=description,
        status=None,  # Not applicable for curriculum
        priority=None,  # Not applicable for curriculum
        metadata=metadata,
        actions=ButtonLink(
            "Start Learning →",
            href=f"/knowledge/{ku.uid}",
            variant="primary",
            full_width=True,
        ),
        config=CardConfig.default(),
    )
```

**Key Techniques:**
- ✅ Dynamic metadata building (not all KUs have all fields)
- ✅ Mix strings and Badge components in metadata
- ✅ Defensive programming with `hasattr()` checks
- ✅ Text truncation for long descriptions
- ✅ Semantic badge variants (success/warning)

### 3. Journey Overview

**Use Case:** Display complete SEL journey across all 5 categories

**Pattern:**
```python
def SELJourneyOverview(journey: SELJourney) -> Div:
    """Complete SEL journey overview showing progress across all 5 categories."""
    # Get recommended next category
    next_category = journey.get_next_recommended_category()

    return Div(
        # Header with overall progress
        PageHeader("Your SEL Journey", subtitle="Social Emotional Learning: 5 core areas"),

        # Overall completion
        Div(
            P(
                f"Overall Completion: {journey.overall_completion:.0f}%",
                cls="text-sm text-base-content/70 mb-2",
            ),
            Progress(
                value=int(journey.overall_completion),
                max_val=100,
                cls="progress progress-primary",
            ),
            cls="mt-4 mb-8",
        ),

        # Recommended focus callout
        Div(
            P(
                f"Recommended Focus: {next_category.value.replace('_', ' ').title()} "
                f"{get_sel_icon(next_category.value)}",
                cls="m-0",
            ),
            cls="alert alert-info mb-4",
        ),

        # Category cards grid
        SectionHeader("Your Progress by Category"),
        Div(
            *[
                SELCategoryCard(category, progress)
                for category, progress in journey.category_progress.items()
            ],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
        cls="container mx-auto max-w-6xl p-4",
    )
```

**Key Techniques:**
- ✅ Use `PageHeader` and `SectionHeader` for consistent headings
- ✅ Alert boxes for important callouts
- ✅ Grid layout for responsive cards
- ✅ List comprehension for dynamic card generation
- ✅ Container max-width for readability

### 4. HTMX Dynamic Curriculum Loading

**Use Case:** Load personalized curriculum on page load (not on initial render)

**Pattern:**
```python
# In route handler
content = Div(
    breadcrumbs,
    PageHeader("Self Awareness", subtitle="Understanding your thoughts and emotions"),
    SectionHeader("About This Competency"),
    P("Description...", cls="text-base-content/70 mb-6"),

    # Personalized curriculum - loaded via HTMX
    SectionHeader("Your Personalized Curriculum"),
    Div(
        # Loading skeleton (shown initially)
        Div(
            P("Loading personalized curriculum...", cls="text-center py-8"),
            cls="animate-pulse",
        ),

        # HTMX attributes
        hx_get="/api/sel/curriculum-html/self_awareness?limit=10",
        hx_trigger="load",  # Trigger on page load
        hx_swap="innerHTML",  # Replace entire contents

        # Accessibility
        **htmx_attrs(
            operation=HTMXOperation.LOAD,
            announce="Curriculum loaded",
            announce_loading="Loading personalized curriculum",
        ),

        id="curriculum-list",
        cls="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6",
    ),
)
```

**HTMX API Endpoint:**
```python
@rt("/api/sel/curriculum-html/{category}")
async def get_curriculum_html(request: Request, category: str, limit: int = 10) -> Any:
    """Returns HTML fragment of KU cards"""
    user_uid = require_authenticated_user(request)

    # Validate category
    try:
        sel_category = SELCategory(category)
    except ValueError:
        return Div(
            P(f"Invalid category: {category}", cls="text-error"),
            cls="alert alert-error",
        )

    # Get curriculum
    result = await services.adaptive_sel.get_personalized_curriculum(
        user_uid=user_uid, sel_category=sel_category, limit=limit
    )

    # Error state
    if result.is_error:
        return Div(
            P("Unable to load curriculum. Please try again.", cls="text-error"),
            cls="alert alert-error",
        )

    curriculum = result.value

    # Empty state
    if not curriculum:
        return EmptyState(
            title="No curriculum available yet",
            description="Complete prerequisite knowledge units to unlock content.",
            icon="📚",
        )

    # Success state - render cards
    return Div(
        *[AdaptiveKUCard(ku) for ku in curriculum],
        cls="grid grid-cols-1 md:grid-cols-2 gap-4",
    )
```

**Key Techniques:**
- ✅ `hx_trigger="load"` for immediate loading
- ✅ Skeleton state shown during load
- ✅ `htmx_attrs()` for accessibility (ARIA announcements)
- ✅ Error handling returns HTML alerts
- ✅ Empty state for zero results
- ✅ API returns HTML fragments (not JSON)

### 5. Breadcrumb Navigation

**Use Case:** Show navigation path for category pages

**Pattern:**
```python
from ui.patterns.breadcrumbs import Breadcrumbs

breadcrumbs = Breadcrumbs(
    path=[
        {"uid": "sel", "title": "SEL", "url": "/sel"},
        {"uid": "self-awareness", "title": "Self Awareness", "url": None},
    ]
)

# Use at top of content
content = Div(
    breadcrumbs,  # First element
    PageHeader(...),
    # ... rest of content
)
```

**Key Techniques:**
- ✅ Last item has `url: None` (current page)
- ✅ Place at very top of content
- ✅ UIDs for keys, titles for display
- ✅ Automatic keyboard navigation

### 6. Sidebar Navigation (SidebarPage)

**Use Case:** Persistent sidebar menu for all SEL pages, using the unified `SidebarPage()` component

**Pattern:**
```python
from ui.patterns.sidebar import SidebarItem, SidebarPage

# Menu items defined at module level
SEL_ITEMS = [
    SidebarItem("Overview", "/sel", "overview", description="Introduction to SEL"),
    SidebarItem("Self Awareness", "/sel/self-awareness", "self-awareness", description="Understanding thoughts/emotions"),
    SidebarItem("Self Management", "/sel/self-management", "self-management", description="Managing emotions"),
    # ... rest
]

# In route handler
@rt("/sel/self-awareness")
async def sel_self_awareness(request: Request) -> Any:
    content = Div(...)  # Your page content

    return await SidebarPage(
        content=content,
        items=SEL_ITEMS,
        active="self-awareness",
        title="SEL",
        subtitle="Social Emotional Learning",
        storage_key="sel-sidebar",
        request=request,
        active_page="sel",
    )
```

**Key Techniques:**
- ✅ Uses unified `SidebarPage()` from `ui/patterns/sidebar.py`
- ✅ Desktop: Collapsible fixed sidebar with Alpine.js state
- ✅ Mobile: Horizontal DaisyUI tabs (no drawer/overlay)
- ✅ Active page slug drives highlighted item
- ✅ No custom CSS files needed

**See:** `@custom-sidebar-patterns` for complete implementation guide

## Best Practices

### Component Composition

**DO:** Build components from primitives
```python
# Good: Uses EntityCard
EntityCard(
    title=title,
    metadata=metadata,
    actions=ButtonLink(...),
)
```

**DON'T:** Manual card layout
```python
# Bad: Reimplements card structure
Card(CardBody(
    Div(...),  # Manual layout
    Div(...),
    A(...),
))
```

### Metadata Building

**DO:** Dynamic list building
```python
metadata = []
if hasattr(ku, "time"):
    metadata.append(f"⏱ {ku.time} min")
if hasattr(ku, "difficulty"):
    metadata.append(f"🎯 {ku.difficulty}")
```

**DON'T:** Conditional rendering in template
```python
# Bad: Harder to read
metadata=[
    f"⏱ {ku.time} min" if hasattr(ku, "time") else None,
    f"🎯 {ku.difficulty}" if hasattr(ku, "difficulty") else None,
]
```

### HTMX Error Handling

**DO:** Return HTML error states
```python
if result.is_error:
    return Div(
        P("Error message", cls="text-error"),
        cls="alert alert-error",
    )
```

**DON'T:** Return JSON errors
```python
# Bad: HTMX expects HTML
if result.is_error:
    return {"error": "Something failed"}
```

### Badge Usage

**DO:** Semantic variants
```python
Badge("Prerequisites met", variant="success")
Badge("Prerequisites needed", variant="warning")
```

**DON'T:** Generic styling
```python
# Bad: No semantic meaning
Badge("Prerequisites met", variant="default")
```

## Testing Patterns

### Visual Testing
```python
# Test that components render
def test_sel_category_card_renders():
    category = SELCategory.SELF_AWARENESS
    progress = SELCategoryProgress(...)
    card = SELCategoryCard(category, progress)
    assert card is not None
    # More assertions on structure
```

### Integration Testing
```python
# Test HTMX endpoints
async def test_curriculum_html_endpoint(client):
    response = await client.get("/api/sel/curriculum-html/self_awareness")
    assert response.status_code == 200
    assert "AdaptiveKUCard" in response.text  # Check component rendered
```

## Related Documentation

**Patterns:**
- [UI Component Patterns](UI_COMPONENT_PATTERNS.md) - EntityCard, BasePage
- [HTMX Accessibility Patterns](HTMX_ACCESSIBILITY_PATTERNS.md) - ARIA announcements

**Features:**
- [SEL Adaptive Curriculum](../features/SEL_ADAPTIVE_CURRICULUM.md) - Complete feature docs

**Migrations:**
- [SEL UX Modernization](../migrations/SEL_UX_MODERNIZATION_2026-02-03.md) - Migration history

## See Also

**Reference Implementations:**
- `/adapters/inbound/sel_components.py` - Component definitions
- `/adapters/inbound/sel_routes.py` - Route handlers with HTMX
- `/ui/patterns/entity_card.py` - EntityCard primitive
- `/ui/primitives/badge.py` - Badge primitive
- `/ui/primitives/button.py` - ButtonLink primitive
