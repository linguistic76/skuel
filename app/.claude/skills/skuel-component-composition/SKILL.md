---
name: skuel-component-composition
description: Expert guide for composing reusable UI components in SKUEL. Use when building component hierarchies, creating domain-specific patterns, composing layout primitives, or when the user mentions component composition, reusable patterns, UI primitives, or design systems.
allowed-tools: Read, Grep, Glob
related_skills:
- daisyui
- tailwind-css
- base-page-architecture
- custom-sidebar-patterns
- html-htmx
---

# SKUEL Component Composition

## Core Philosophy

> "Compose small, focused components into larger patterns. Primitives provide structure, patterns provide semantics, layouts provide consistency."

SKUEL's UI architecture follows a **three-layer composition model**:

```
Layouts (Pages)
    ↓ compose
Patterns (Semantic Components)
    ↓ compose
Primitives (DaisyUI + Tailwind)
```

**Key Principle:** Each layer focuses on a single responsibility - primitives handle styling, patterns handle domain semantics, layouts handle page structure.

## When to Use This Skill

Use this guide when:

- ✅ Building **reusable components** for Activity Domains (TaskCard, GoalCard, etc.)
- ✅ Creating **composite patterns** (EntityCard, StatsGrid, PageHeader)
- ✅ Composing **layout components** (BasePage, custom sidebars, modal layouts)
- ✅ **Refactoring** duplicated UI code into shared components
- ✅ Understanding **component hierarchy** and composition strategies
- ✅ Deciding **where to create** new components (primitives vs patterns vs layouts)

## Core Concepts

### 1. Three-Layer Composition Model

**Layer 1: Primitives (DaisyUI + Tailwind)**

Location: `/core/ui/daisy_components.py`, `/static/css/`

Purpose: **Atomic styling components** with no domain knowledge

```python
from core.ui.daisy_components import Button, Card, CardBody, Badge, ButtonT

# Primitive usage - no domain semantics
Button("Click Me", variant=ButtonT.primary)
Card(CardBody(H2("Title"), P("Content")))
Badge("New", variant=BadgeT.success)
```

**Characteristics:**
- Generic (work in any domain)
- Style-focused (colors, spacing, layout)
- No business logic
- Directly map to DaisyUI classes

**Layer 2: Patterns (Semantic Components)**

Location: `/ui/patterns/`, `/components/`

Purpose: **Domain-aware reusable components** with semantic meaning

```python
from ui.patterns import PageHeader, SectionHeader, EntityCard, StatsGrid

# Pattern usage - domain semantics
PageHeader("Tasks", subtitle="Manage your daily work")
EntityCard(
    title="Buy groceries",
    status="active",
    priority="high",
    entity_type="task",
)
StatsGrid([
    {"label": "Total", "value": "42"},
    {"label": "Completed", "value": "18"},
])
```

**Characteristics:**
- Domain-specific (Tasks, Goals, Habits)
- Semantic naming (PageHeader, EntityCard, not Div)
- Compose primitives
- Handle common UI patterns

**Layer 3: Layouts (Pages)**

Location: `/ui/layouts/`, `/ui/profile/`, `/ui/tasks/`

Purpose: **Page-level composition** with BasePage integration

```python
from ui.layouts.base_page import BasePage
from ui.tasks.layout import create_tasks_page

# Layout usage - full page structure
return BasePage(
    content,
    title="Tasks",
    page_type=PageType.STANDARD,
    request=request,
)

# Domain-specific page layout
return create_tasks_page(
    content,
    active_view="list",
    request=request,
)
```

**Characteristics:**
- Full page structure
- Navbar + content + footer
- BasePage integration
- Domain-specific wrappers (create_tasks_page)

### 2. Composition Strategies

**Strategy 1: Function Composition (Preferred)**

Use functions that return FastHTML components:

```python
def TaskCard(task: Task, show_actions: bool = True) -> Any:
    """Task card component."""
    return Card(
        CardBody(
            # Title with status badge
            DivFullySpaced(
                H4(task.title, cls="font-semibold"),
                Badge(task.status.value, variant=_status_badge(task.status)),
            ),
            # Description
            P(task.description or "No description", cls="text-sm text-base-content/70"),
            # Actions (conditional)
            CardActions(
                Button("Edit", variant=ButtonT.ghost, size=Size.sm) if show_actions else None,
                Button("Complete", variant=ButtonT.success, size=Size.sm) if show_actions else None,
            ) if show_actions else None,
        ),
    )
```

**Strategy 2: Class Composition (For Stateful Components)**

Use classes when component needs internal state:

```python
class TasksViewComponents:
    """Stateful task view components."""

    @staticmethod
    def render_list_view(tasks: list[Task], stats: dict) -> Any:
        """Render list view with stats."""
        return Div(
            # Stats header
            TasksViewComponents._render_stats_bar(stats),
            # Task list
            Grid(
                *[TaskCard(task) for task in tasks],
                cols=1,
                gap=4,
            ),
        )

    @staticmethod
    def _render_stats_bar(stats: dict) -> Any:
        """Private helper for stats."""
        return StatsGrid([
            {"label": "Total", "value": str(stats["total"])},
            {"label": "Active", "value": str(stats["active"])},
            {"label": "Completed", "value": str(stats["completed"])},
        ])
```

**Strategy 3: Configuration-Driven Components**

Use dataclasses for configuration:

```python
from dataclasses import dataclass

@dataclass
class CardConfig:
    """Configuration for entity card."""
    show_description: bool = True
    show_status: bool = True
    show_actions: bool = True
    compact: bool = False

def EntityCard(
    title: str,
    config: CardConfig = CardConfig(),
    **kwargs,
) -> Any:
    """Configurable entity card."""
    return Card(
        CardBody(
            H4(title),
            P(kwargs.get("description")) if config.show_description else None,
            Badge(kwargs.get("status")) if config.show_status else None,
            # ... actions if config.show_actions
        ),
        cls="p-4" if config.compact else "p-6",
    )
```

### 3. Component Hierarchy Decision Tree

```
Need to create a new component?
├─ Is it domain-agnostic styling (button, card, input)?
│   ├─ YES → Add to /core/ui/daisy_components.py (Primitive)
│   └─ NO → Continue
├─ Is it reusable across multiple domains?
│   ├─ YES → Add to /ui/patterns/ (Pattern)
│   └─ NO → Continue
├─ Is it domain-specific but reusable within domain?
│   ├─ YES → Add to /components/{domain}_*.py (Pattern)
│   └─ NO → Continue
└─ Is it one-off UI for single route?
    └─ YES → Inline in route file (No separate component)
```

### 4. Naming Conventions

| Component Type | Naming Pattern | Example |
|----------------|----------------|---------|
| **Primitive** | DaisyUI semantic name | `Button`, `Card`, `Input` |
| **Pattern (Generic)** | Semantic purpose | `PageHeader`, `SectionHeader`, `EmptyState` |
| **Pattern (Domain)** | Domain + Entity | `TaskCard`, `GoalProgress`, `HabitStreak` |
| **Layout** | `create_{domain}_page` | `create_tasks_page`, `create_profile_page` |
| **Helper** | `render_{purpose}` | `render_error_banner`, `render_stats_grid` |

### 5. Component API Design

**Good component APIs:**

```python
# ✅ GOOD: Clear parameters, sensible defaults, optional customization
def TaskCard(
    task: Task,
    show_actions: bool = True,
    show_description: bool = True,
    on_complete: str | None = None,  # Optional HTMX handler
    cls: str = "",  # Allow extra classes
) -> Any:
    """Task card with configurable sections."""
    # ...
```

**Poor component APIs:**

```python
# ❌ BAD: Too many required parameters, unclear purpose
def TaskCard(
    title: str,
    desc: str,
    stat: str,
    prio: str,
    uid: str,
    cat: str,
    proj: str,
) -> Any:
    """Task card."""  # Unclear what each param does
    # ...
```

**Principles:**
1. **Require domain objects** (task: Task, not individual fields)
2. **Boolean flags** for optional sections (show_actions, show_description)
3. **Sensible defaults** (most common use case works with minimal params)
4. **cls parameter** for extensibility (allow extra Tailwind classes)
5. **Docstrings** explaining purpose and usage

## Implementation Patterns

### Pattern 1: Entity Card Component (Reusable Pattern)

**Purpose:** Generic card for any entity with common sections

**File:** `/home/mike/skuel/app/ui/patterns/entity_card.py`

**Implementation:**

```python
from typing import Any, TYPE_CHECKING
from fasthtml.common import Div, H4, P, Span
from core.ui.daisy_components import Card, CardBody, CardActions, Badge, Button, ButtonT, Size

if TYPE_CHECKING:
    from fasthtml.common import FT

def EntityCard(
    title: str,
    entity_type: str,
    uid: str,
    status: str | None = None,
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
    show_actions: bool = True,
    compact: bool = False,
    cls: str = "",
) -> "FT":
    """Generic entity card for Tasks, Goals, Habits, etc.

    Args:
        title: Entity title
        entity_type: Domain type ("task", "goal", "habit")
        uid: Entity UID for actions
        status: Status badge text
        description: Optional description text
        metadata: Optional metadata dict (displayed as badges)
        show_actions: Whether to show action buttons
        compact: Compact layout (less padding)
        cls: Additional CSS classes

    Returns:
        Card component with entity details
    """
    metadata = metadata or {}

    # Status badge
    status_badge = Badge(status, variant=BadgeT.success) if status else None

    # Metadata badges
    metadata_badges = [
        Badge(f"{k}: {v}", variant=BadgeT.ghost, size=Size.sm)
        for k, v in metadata.items()
    ] if metadata else []

    return Card(
        CardBody(
            # Header (title + status)
            Div(
                H4(title, cls="font-semibold text-base"),
                status_badge,
                cls="flex justify-between items-start mb-2",
            ),

            # Description
            P(
                description or "No description",
                cls="text-sm text-base-content/70 mb-3",
            ) if description else None,

            # Metadata
            Div(
                *metadata_badges,
                cls="flex gap-2 flex-wrap mb-3",
            ) if metadata_badges else None,

            # Actions
            CardActions(
                Button(
                    "👁️ View",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    hx_get=f"/{entity_type}s/{uid}",
                ),
                Button(
                    "✏️ Edit",
                    variant=ButtonT.outline,
                    size=Size.sm,
                    hx_get=f"/{entity_type}s/{uid}/edit",
                    hx_target="#modal",
                ),
            ) if show_actions else None,
        ),
        cls=f"hover:shadow-lg transition-shadow {cls}".strip(),
    )
```

**Usage:**

```python
# Task card
EntityCard(
    title="Buy groceries",
    entity_type="task",
    uid="task_buy-groceries_abc123",
    status="active",
    description="Get milk, eggs, bread",
    metadata={"priority": "high", "due": "2026-02-05"},
)

# Goal card
EntityCard(
    title="Learn Python",
    entity_type="goal",
    uid="goal_learn-python_xyz789",
    status="in_progress",
    metadata={"progress": "45%", "category": "learning"},
    compact=True,
)
```

### Pattern 2: Page Header Component (Semantic Pattern)

**Purpose:** Consistent page headers with title, subtitle, actions

**File:** `/home/mike/skuel/app/ui/patterns/page_header.py`

**Implementation:**

```python
from typing import Any, TYPE_CHECKING
from fasthtml.common import Div, H1, P

if TYPE_CHECKING:
    from fasthtml.common import FT

def PageHeader(
    title: str,
    subtitle: str = "",
    actions: Any = None,
    cls: str = "",
) -> "FT":
    """Consistent page header with title, optional subtitle, and actions.

    Args:
        title: Main page title
        subtitle: Optional subtitle or description
        actions: Optional action buttons (right-aligned)
        cls: Additional CSS classes

    Returns:
        Page header component
    """
    title_section = Div(
        H1(title, cls="text-2xl font-bold text-base-content"),
        P(subtitle, cls="text-base-content/70 mt-1") if subtitle else None,
    )

    if actions:
        return Div(
            title_section,
            Div(actions, cls="flex gap-2"),
            cls=f"flex justify-between items-start mb-8 {cls}".strip(),
        )

    return Div(
        title_section,
        cls=f"mb-8 {cls}".strip(),
    )
```

**Usage:**

```python
from ui.patterns import PageHeader

# Simple header
PageHeader("Tasks", subtitle="Manage your daily work")

# Header with action button
PageHeader(
    "Goals",
    actions=Button("Create Goal", variant=ButtonT.primary, hx_get="/goals/create-modal", hx_target="#modal"),
)
```

### Pattern 3: Stats Grid Component (Reusable Pattern)

**Purpose:** Display metric cards in responsive grid

**File:** `/home/mike/skuel/app/ui/patterns/stats_grid.py`

**Implementation:**

```python
from typing import Any, TYPE_CHECKING
from fasthtml.common import Div, P, Span
from core.ui.daisy_components import Grid, Card, CardBody

if TYPE_CHECKING:
    from fasthtml.common import FT

def StatCard(
    label: str,
    value: str,
    icon: str = "",
    trend: str | None = None,
    cls: str = "",
) -> "FT":
    """Individual stat card.

    Args:
        label: Metric label
        value: Metric value
        icon: Optional icon (emoji or SVG)
        trend: Optional trend indicator ("+5%", "-2%")
        cls: Additional CSS classes

    Returns:
        Stat card component
    """
    return Card(
        CardBody(
            # Icon + Label
            Div(
                Span(icon, cls="text-2xl", aria_hidden="true") if icon else None,
                P(label, cls="text-sm text-base-content/70"),
                cls="flex items-center gap-2 mb-2",
            ),

            # Value
            P(value, cls="text-3xl font-bold text-base-content"),

            # Trend
            Span(
                trend,
                cls=f"text-xs {'text-success' if trend and trend.startswith('+') else 'text-error'}",
            ) if trend else None,
        ),
        cls=f"hover:shadow-md transition-shadow {cls}".strip(),
    )


def StatsGrid(
    stats: list[dict[str, Any]],
    cols: int = 4,
    cls: str = "",
) -> "FT":
    """Responsive grid of stat cards.

    Args:
        stats: List of stat dicts with keys: label, value, icon (optional), trend (optional)
        cols: Number of columns on desktop (1 on mobile, 2 on tablet)
        cls: Additional CSS classes

    Returns:
        Grid of stat cards
    """
    return Grid(
        *[
            StatCard(
                label=stat["label"],
                value=stat["value"],
                icon=stat.get("icon", ""),
                trend=stat.get("trend"),
            )
            for stat in stats
        ],
        cols=cols,
        gap=4,
        cls=cls,
    )
```

**Usage:**

```python
from ui.patterns import StatsGrid

StatsGrid([
    {"label": "Total Tasks", "value": "42", "icon": "✅", "trend": "+5"},
    {"label": "Completed", "value": "18", "icon": "🎉"},
    {"label": "Overdue", "value": "3", "icon": "⚠️", "trend": "-2"},
    {"label": "This Week", "value": "12", "icon": "📅"},
])
```

### Pattern 4: Empty State Component (Reusable Pattern)

**Purpose:** Consistent empty state messaging

**File:** `/home/mike/skuel/app/ui/patterns/empty_state.py`

**Implementation:**

```python
from typing import Any, TYPE_CHECKING
from fasthtml.common import Div, P, Span

if TYPE_CHECKING:
    from fasthtml.common import FT

def EmptyState(
    message: str,
    icon: str = "📭",
    action: Any = None,
    cls: str = "",
) -> "FT":
    """Empty state component with optional action.

    Args:
        message: Empty state message
        icon: Emoji or SVG icon
        action: Optional action button
        cls: Additional CSS classes

    Returns:
        Centered empty state component
    """
    return Div(
        Div(
            Span(icon, cls="text-6xl opacity-30 mb-4", aria_hidden="true"),
            P(message, cls="text-base-content/60 mb-4"),
            action if action else None,
            cls="flex flex-col items-center gap-4",
        ),
        cls=f"py-12 {cls}".strip(),
    )
```

**Usage:**

```python
from ui.patterns import EmptyState

# Simple empty state
EmptyState("No tasks found.", icon="✅")

# With action button
EmptyState(
    "No goals yet. Create your first goal!",
    icon="🎯",
    action=Button(
        "Create Goal",
        variant=ButtonT.primary,
        hx_get="/goals/create-modal",
        hx_target="#modal",
    ),
)
```

### Pattern 5: Domain-Specific Component (Task Card)

**Purpose:** Task-specific card with domain knowledge

**File:** `/home/mike/skuel/app/components/todoist_task_components.py`

**Implementation:**

```python
from typing import Any
from core.models.task.task import Task
from core.models.enums import ActivityStatus, Priority
from core.ui.daisy_components import Card, CardBody, Badge, Button, ButtonT, BadgeT, Size

def _priority_badge(priority: Priority) -> BadgeT:
    """Map priority to badge variant."""
    return {
        Priority.CRITICAL: BadgeT.error,
        Priority.HIGH: BadgeT.warning,
        Priority.MEDIUM: BadgeT.info,
        Priority.LOW: BadgeT.success,
    }.get(priority, BadgeT.ghost)


def _status_badge(status: ActivityStatus) -> BadgeT:
    """Map status to badge variant."""
    return {
        ActivityStatus.COMPLETED: BadgeT.success,
        ActivityStatus.IN_PROGRESS: BadgeT.info,
        ActivityStatus.BLOCKED: BadgeT.error,
        ActivityStatus.CANCELLED: BadgeT.ghost,
    }.get(status, BadgeT.ghost)


def TaskCard(task: Task, show_actions: bool = True) -> Any:
    """Task card with domain-specific fields.

    Args:
        task: Task domain model
        show_actions: Whether to show action buttons

    Returns:
        Task card component
    """
    from fasthtml.common import Div, H4, P, Span

    return Card(
        CardBody(
            # Title + Status
            Div(
                H4(task.title, cls="font-semibold"),
                Badge(task.status.value, variant=_status_badge(task.status)),
                cls="flex justify-between items-start mb-2",
            ),

            # Description
            P(
                task.description or "No description",
                cls="text-sm text-base-content/70 mb-3",
            ),

            # Metadata (priority, project, due date)
            Div(
                Badge(task.priority.value, variant=_priority_badge(task.priority), size=Size.sm),
                Span(f"📁 {task.project}", cls="text-xs") if task.project else None,
                Span(f"📅 {task.due_date}", cls="text-xs") if task.due_date else None,
                cls="flex gap-2 items-center mb-3",
            ),

            # Actions
            CardActions(
                Button(
                    "✏️ Edit",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    hx_get=f"/tasks/{task.uid}/edit",
                    hx_target="#modal",
                ),
                Button(
                    "✅ Complete",
                    variant=ButtonT.success,
                    size=Size.sm,
                    hx_post=f"/api/tasks/{task.uid}/complete",
                    hx_target="body",
                ),
            ) if show_actions else None,
        ),
        cls=f"border-l-4 {'border-error' if task.priority == Priority.CRITICAL else 'border-warning' if task.priority == Priority.HIGH else 'border-base-300'}",
    )
```

**Usage:**

```python
from components.todoist_task_components import TaskCard

# In route handler
tasks = await tasks_service.get_user_tasks(user_uid)
return Grid(
    *[TaskCard(task) for task in tasks.value],
    cols=1,
    gap=4,
)
```

### Pattern 6: Layout Wrapper (Domain Page)

**Purpose:** Consistent page structure for domain

**File:** `/home/mike/skuel/app/ui/tasks/layout.py`

**Implementation:**

```python
from typing import Any, TYPE_CHECKING
from ui.layouts.base_page import BasePage
from ui.tokens import Container, Spacing

if TYPE_CHECKING:
    from starlette.requests import Request

def create_tasks_page(
    content: Any,
    active_view: str = "list",
    request: "Request | None" = None,
) -> Any:
    """Create tasks page with consistent layout.

    Args:
        content: Main content HTML
        active_view: Active view tab ("list", "calendar", "create")
        request: Starlette request for auth detection

    Returns:
        Complete page using BasePage
    """
    from ui.patterns import PageHeader

    wrapped_content = Div(
        PageHeader(
            "Tasks",
            subtitle="Manage your daily work",
            actions=Button(
                "New Task",
                variant=ButtonT.primary,
                hx_get="/tasks/create-modal",
                hx_target="#modal",
            ),
        ),
        # View tabs (if applicable)
        render_view_tabs(active_view) if active_view else None,
        # Main content
        content,
        cls=f"{Spacing.PAGE} {Container.STANDARD}",
    )

    return BasePage(
        content=wrapped_content,
        title="Tasks",
        request=request,
        active_page="tasks",
    )


def render_view_tabs(active_view: str) -> Any:
    """Render view tabs for tasks page."""
    from core.ui.daisy_components import Tabs, Tab

    return Tabs(
        Tab("List", active=active_view == "list", hx_get="/tasks/view/list", hx_target="#task-content"),
        Tab("Calendar", active=active_view == "calendar", hx_get="/tasks/view/calendar", hx_target="#task-content"),
        Tab("Create", active=active_view == "create", hx_get="/tasks/view/create", hx_target="#task-content"),
        boxed=True,
        cls="mb-6",
    )
```

**Usage:**

```python
from ui.tasks.layout import create_tasks_page

@rt("/tasks")
async def tasks_dashboard(request):
    user_uid = require_authenticated_user(request)
    tasks = await tasks_service.get_user_tasks(user_uid)

    content = Grid(
        *[TaskCard(task) for task in tasks.value],
        cols=1,
        gap=4,
    )

    return create_tasks_page(
        content,
        active_view="list",
        request=request,
    )
```

### Pattern 7: Conditional Rendering Helper

**Purpose:** Render content conditionally without breaking composition

**Implementation:**

```python
def render_if(condition: bool, component: Any) -> Any | None:
    """Render component only if condition is True."""
    return component if condition else None


def render_unless(condition: bool, component: Any) -> Any | None:
    """Render component unless condition is True."""
    return component if not condition else None


# Usage in component
def TaskCard(task: Task, show_actions: bool = True) -> Any:
    return Card(
        CardBody(
            H4(task.title),
            render_if(task.description, P(task.description)),  # Only if description exists
            render_if(show_actions, CardActions(...)),  # Only if actions enabled
            render_unless(task.is_completed, Badge("Active")),  # Hide if completed
        ),
    )
```

### Pattern 8: Component Variants via Configuration

**Purpose:** Single component with multiple visual variants

**Implementation:**

```python
from dataclasses import dataclass
from enum import Enum

class CardVariant(str, Enum):
    """Card visual variants."""
    DEFAULT = "default"
    COMPACT = "compact"
    HIGHLIGHTED = "highlighted"


@dataclass
class CardConfig:
    """Configuration for card component."""
    variant: CardVariant = CardVariant.DEFAULT
    show_actions: bool = True
    show_description: bool = True


def EntityCard(
    title: str,
    config: CardConfig = CardConfig(),
    **kwargs,
) -> Any:
    """Entity card with configurable variants."""

    # Variant-specific styling
    card_cls = {
        CardVariant.DEFAULT: "hover:shadow-lg",
        CardVariant.COMPACT: "p-3",
        CardVariant.HIGHLIGHTED: "border-2 border-primary",
    }.get(config.variant, "")

    return Card(
        CardBody(
            H4(title),
            P(kwargs.get("description")) if config.show_description else None,
            CardActions(...) if config.show_actions else None,
        ),
        cls=card_cls,
    )


# Usage
EntityCard("Task 1", config=CardConfig(variant=CardVariant.COMPACT))
EntityCard("Task 2", config=CardConfig(variant=CardVariant.HIGHLIGHTED, show_actions=False))
```

## Real-World Examples

### Example 1: Profile Hub Domain Items (Composition Pattern)

**File:** `/home/mike/skuel/app/ui/profile/layout.py`

**Composing sidebar items from primitives:**

```python
def _domain_menu_item(domain: ProfileDomainItem, is_active: bool) -> "FT":
    """Compose sidebar item from primitives."""
    return Li(  # DaisyUI primitive
        Anchor(  # HTML primitive
            Span(domain.icon, cls="text-lg"),  # Primitive
            Span(domain.name, cls="flex-1"),  # Primitive
            Div(  # Container primitive
                # Compose badges (patterns)
                _count_badge(domain.count, domain.active_count),
                _status_badge(domain.status),
                _insight_badge(domain.insight_count),
                cls="flex items-center gap-2",
            ),
            href=domain.href,
            cls=f"flex items-center gap-2 {'menu-active' if is_active else ''}",
        )
    )
```

### Example 2: Task Dashboard (Full Page Composition)

**File:** `/home/mike/skuel/app/adapters/inbound/tasks_ui.py`

**Complete page from patterns:**

```python
from ui.patterns import PageHeader, StatsGrid, EmptyState
from ui.tasks.layout import create_tasks_page
from components.todoist_task_components import TaskCard

@rt("/tasks")
async def tasks_dashboard(request):
    user_uid = require_authenticated_user(request)
    tasks_result = await get_filtered_tasks(user_uid, "active", "due_date")

    if tasks_result.is_error:
        return create_tasks_page(
            render_error_banner(f"Failed to load tasks: {tasks_result.error}"),
            request=request,
        )

    tasks, stats = tasks_result.value

    # Compose page from patterns
    content = Div(
        # Pattern: Stats grid
        StatsGrid([
            {"label": "Total", "value": str(stats["total"]), "icon": "✅"},
            {"label": "Active", "value": str(stats["active"]), "icon": "🔄"},
            {"label": "Completed", "value": str(stats["completed"]), "icon": "🎉"},
        ]),

        # Pattern: Empty state or task grid
        EmptyState("No tasks found.") if not tasks else Grid(
            *[TaskCard(task) for task in tasks],
            cols=1,
            gap=4,
        ),
    )

    # Layout: Wrap in page layout
    return create_tasks_page(
        content,
        active_view="list",
        request=request,
    )
```

## Common Mistakes & Anti-Patterns

### Mistake 1: Monolithic Component (God Component)

```python
# ❌ BAD: Single function doing everything
def TasksPage(request):
    """200-line function with inline HTML."""
    return Html(
        Head(...),
        Body(
            # Inline navbar
            Nav(...),
            # Inline header
            Div(H1("Tasks"), Button("New")),
            # Inline stats
            Div(Div(...), Div(...), Div(...)),
            # Inline task list
            Div(*[Div(task.title, ...) for task in tasks]),
        ),
    )

# ✅ GOOD: Composed from small components
def tasks_dashboard(request):
    """Orchestrate components."""
    content = Div(
        StatsGrid(stats),
        Grid(*[TaskCard(task) for task in tasks]),
    )
    return create_tasks_page(content, request=request)
```

### Mistake 2: Tight Coupling to Domain Model

```python
# ❌ BAD: Component tightly coupled to Task model
def TaskCard(task: Task):
    """Must pass entire Task object."""
    return Card(
        H4(task.title),
        P(task.description),
        Badge(task.priority.value),
    )

# ✅ GOOD: Accept primitives, allow flexibility
def EntityCard(
    title: str,
    description: str | None = None,
    priority: str | None = None,
):
    """Works with any entity type."""
    return Card(
        H4(title),
        P(description) if description else None,
        Badge(priority) if priority else None,
    )
```

### Mistake 3: No Default Values

```python
# ❌ BAD: All parameters required
def PageHeader(title: str, subtitle: str, actions: Any):
    """Must provide all params."""
    # ...

# ✅ GOOD: Sensible defaults
def PageHeader(
    title: str,
    subtitle: str = "",
    actions: Any = None,
):
    """Only title required."""
    # ...
```

### Mistake 4: Inline Styling Instead of Composition

```python
# ❌ BAD: Hardcoded styles, not composable
def TaskCard(task: Task):
    return Div(
        task.title,
        style="padding: 24px; border: 1px solid gray; border-radius: 8px;",
    )

# ✅ GOOD: Compose from styled primitives
def TaskCard(task: Task):
    return Card(
        CardBody(
            H4(task.title),
        ),
    )
```

### Mistake 5: No Extensibility (cls Parameter)

```python
# ❌ BAD: Cannot add extra classes
def TaskCard(task: Task):
    return Card(
        CardBody(H4(task.title)),
        cls="hover:shadow-lg",  # Fixed, cannot override
    )

# ✅ GOOD: Allow extra classes via cls parameter
def TaskCard(task: Task, cls: str = ""):
    return Card(
        CardBody(H4(task.title)),
        cls=f"hover:shadow-lg {cls}".strip(),
    )

# Usage: TaskCard(task, cls="mb-4 border-l-4 border-primary")
```

## Testing & Verification Checklist

### Composition Tests

- [ ] **Single responsibility:** Each component does one thing well
- [ ] **Reusability:** Component used in multiple places
- [ ] **Composition:** Component composes smaller primitives
- [ ] **Extensibility:** Accepts `cls` parameter for customization
- [ ] **Defaults:** Works with minimal parameters

### API Tests

- [ ] **Clear parameters:** Parameter names self-documenting
- [ ] **Type hints:** All parameters have type annotations
- [ ] **Docstrings:** Purpose and usage documented
- [ ] **Sensible defaults:** Most common use case requires fewest params
- [ ] **Optional sections:** Boolean flags for optional content

### Visual Tests

- [ ] **Consistent spacing:** Uses design tokens (Spacing, Container)
- [ ] **Responsive:** Works on mobile (320px) to desktop (1920px)
- [ ] **Accessible:** Semantic HTML, ARIA labels, keyboard navigation
- [ ] **Theme-aware:** Uses DaisyUI colors (works in light/dark themes)

## Related Documentation

### SKUEL Documentation

- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Complete UI patterns guide
- `/ui/patterns/` - Pattern implementations
- `/ui/layouts/` - Layout components
- `/components/` - Domain-specific components

### Related Patterns

- **DaisyUI:** For primitive components (Button, Card, etc.)
- **Tailwind CSS:** For utility classes and responsive design
- **BasePage Architecture:** For page-level composition
- **Custom Sidebar Patterns:** For complex navigation composition

## See Also

- `daisyui` - For primitive component reference
- `tailwind-css` - For utility classes and layout patterns
- `base-page-architecture` - For page-level composition patterns
- `custom-sidebar-patterns` - For complex navigation composition
- `html-htmx` - For semantic HTML structure and HTMX integration
