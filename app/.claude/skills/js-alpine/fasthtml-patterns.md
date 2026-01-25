# Alpine.js + FastHTML Integration Patterns

This guide shows how to integrate Alpine.js with FastHTML in SKUEL.

## Core Principle

> Alpine attributes are passed as `**kwargs` using Python dict unpacking.

Since Alpine uses `x-` prefixed attributes that aren't valid Python identifiers, we pass them as string keys in a dictionary.

## Basic Integration

### Pattern 1: Inline x-data

Simple state passed directly to the component.

```python
from monsterui.franken import Div, Button, Span

def counter_component() -> Div:
    """A simple counter with increment/decrement buttons."""
    return Div(
        Button("-", **{"x-on:click": "count--"}),
        Span(**{"x-text": "count"}),
        Button("+", **{"x-on:click": "count++"}),
        **{"x-data": "{ count: 0 }"}
    )
```

**Output HTML:**
```html
<div x-data="{ count: 0 }">
    <button x-on:click="count--">-</button>
    <span x-text="count"></span>
    <button x-on:click="count++">+</button>
</div>
```

### Pattern 2: Toggle Visibility

```python
from monsterui.franken import Div, Button, P

def toggle_panel(title: str, content: str) -> Div:
    """Collapsible panel with toggle button."""
    return Div(
        Button(
            title,
            cls="w-full text-left font-semibold p-2 bg-gray-100",
            **{"x-on:click": "open = !open"}
        ),
        P(
            content,
            cls="p-4 bg-gray-50",
            **{"x-show": "open", "x-transition": ""}
        ),
        **{"x-data": "{ open: false }"}
    )
```

### Pattern 3: Modal Dialog

```python
from monsterui.franken import Div, Button, H2, P

def modal_component(trigger_text: str, title: str, content: str) -> Div:
    """Modal dialog with trigger button."""
    return Div(
        # Trigger button
        Button(trigger_text, cls="btn btn-primary", **{"x-on:click": "open = true"}),

        # Modal backdrop
        Div(
            # Modal content (stop propagation to prevent closing on content click)
            Div(
                H2(title, cls="text-xl font-bold mb-4"),
                P(content, cls="mb-4"),
                Button("Close", cls="btn", **{"x-on:click": "open = false"}),
                cls="bg-white rounded-lg p-6 max-w-md mx-auto mt-20",
                **{"x-on:click.stop": ""}
            ),
            cls="fixed inset-0 bg-black/50 flex items-start justify-center",
            **{
                "x-show": "open",
                "x-transition:enter": "ease-out duration-300",
                "x-transition:enter-start": "opacity-0",
                "x-transition:enter-end": "opacity-100",
                "x-transition:leave": "ease-in duration-200",
                "x-transition:leave-start": "opacity-100",
                "x-transition:leave-end": "opacity-0",
                "x-on:click": "open = false"
            }
        ),
        **{"x-data": "{ open: false }"}
    )
```

## Component Factories

### Factory with Alpine Props

Create reusable factories that accept Alpine-specific parameters.

```python
from monsterui.franken import Div, Button, Span
from typing import Any


def create_dropdown(
    trigger_text: str,
    items: list[str],
    on_select: str = "",  # Alpine expression to run on select
) -> Div:
    """
    Dropdown menu factory.

    Args:
        trigger_text: Button text
        items: Menu items
        on_select: Alpine expression (e.g., "selected = item")
    """
    item_elements = [
        Button(
            item,
            cls="block w-full text-left px-4 py-2 hover:bg-gray-100",
            **{
                "x-on:click": f"open = false; {on_select}".strip("; "),
            }
        )
        for item in items
    ]

    return Div(
        Button(
            trigger_text,
            cls="btn",
            **{"x-on:click": "open = !open"}
        ),
        Div(
            *item_elements,
            cls="absolute mt-1 bg-white border rounded shadow-lg z-10",
            **{
                "x-show": "open",
                "x-transition": "",
                "x-on:click.outside": "open = false"
            }
        ),
        cls="relative inline-block",
        **{"x-data": "{ open: false }"}
    )


# Usage
dropdown = create_dropdown(
    trigger_text="Select Color",
    items=["Red", "Green", "Blue"],
    on_select="selectedColor = item"
)
```

### Factory with Custom Alpine Data

```python
def create_tabs(tabs: list[dict[str, str]]) -> Div:
    """
    Tab component factory.

    Args:
        tabs: List of {"id": "tab_id", "label": "Tab Label", "content": "Content"}
    """
    first_tab = tabs[0]["id"] if tabs else ""

    tab_buttons = [
        Button(
            tab["label"],
            cls="px-4 py-2",
            **{
                "x-on:click": f"activeTab = '{tab['id']}'",
                "x-bind:class": f"{{ 'border-b-2 border-blue-500': activeTab === '{tab['id']}' }}"
            }
        )
        for tab in tabs
    ]

    tab_panels = [
        Div(
            tab["content"],
            cls="p-4",
            **{"x-show": f"activeTab === '{tab['id']}'", "x-transition": ""}
        )
        for tab in tabs
    ]

    return Div(
        Div(*tab_buttons, cls="flex border-b"),
        Div(*tab_panels),
        **{"x-data": f"{{ activeTab: '{first_tab}' }}"}
    )


# Usage
tabs = create_tabs([
    {"id": "overview", "label": "Overview", "content": "Overview content..."},
    {"id": "details", "label": "Details", "content": "Details content..."},
    {"id": "settings", "label": "Settings", "content": "Settings content..."},
])
```

## Touch Gesture Pattern (SKUEL)

From `atomic_habits_mobile.py` - swipeable card carousel.

```python
from monsterui.franken import Div, Card, Button, H2, P, Span


class SwipeableCards:
    """Mobile-optimized swipeable card component."""

    @staticmethod
    def render(cards: list[dict[str, str]]) -> Div:
        """
        Render swipeable card carousel.

        Args:
            cards: List of {"title": "...", "content": "..."}
        """
        card_elements = [
            SwipeableCards._render_card(card, index)
            for index, card in enumerate(cards)
        ]

        progress_dots = [
            Span(
                cls="w-2 h-2 rounded-full",
                **{
                    "x-bind:class": f"swipeIndex === {i} ? 'bg-blue-600' : 'bg-gray-300'"
                }
            )
            for i in range(len(cards))
        ]

        return Div(
            # Swipe instruction
            P(
                "← Swipe to navigate →",
                cls="text-center text-sm text-gray-500 mb-2",
                **{"x-show": "swipeIndex === 0"}
            ),
            # Cards container
            Div(
                *card_elements,
                cls="relative",
                **{
                    "x-ref": "cards",
                    "x-on:touchstart": "handleTouchStart($event)",
                    "x-on:touchend": "handleTouchEnd($event)"
                }
            ),
            # Progress dots
            Div(*progress_dots, cls="flex justify-center gap-2 mt-4"),
            cls="px-4",
            **{"x-data": f"swipeHandler({len(cards)})"}
        )

    @staticmethod
    def _render_card(card: dict[str, str], index: int) -> Card:
        """Render individual swipeable card."""
        return Card(
            H2(card["title"], cls="text-xl font-bold mb-3"),
            P(card["content"], cls="text-gray-700"),
            cls="shadow-lg p-6",
            **{
                "x-show": f"swipeIndex === {index}",
                "x-transition:enter": "transition ease-out duration-300",
                "x-transition:enter-start": "opacity-0 transform translate-x-full",
                "x-transition:enter-end": "opacity-100 transform translate-x-0",
                "x-transition:leave": "transition ease-in duration-200",
                "x-transition:leave-start": "opacity-100 transform translate-x-0",
                "x-transition:leave-end": "opacity-0 transform -translate-x-full"
            }
        )

    @staticmethod
    def get_swipe_script() -> str:
        """
        Alpine.js script for swipe handling.

        Include via Script(SwipeableCards.get_swipe_script(), type="text/javascript")
        """
        return """
document.addEventListener('alpine:init', () => {
    Alpine.data('swipeHandler', (totalCards) => ({
        swipeIndex: 0,
        touchStartX: 0,
        touchEndX: 0,
        totalCards: totalCards,

        handleTouchStart(event) {
            this.touchStartX = event.changedTouches[0].screenX;
        },

        handleTouchEnd(event) {
            this.touchEndX = event.changedTouches[0].screenX;
            this.handleSwipe();
        },

        handleSwipe() {
            const threshold = 50;

            if (this.touchEndX < this.touchStartX - threshold) {
                // Swipe left - next
                if (this.swipeIndex < this.totalCards - 1) {
                    this.swipeIndex++;
                }
            }

            if (this.touchEndX > this.touchStartX + threshold) {
                // Swipe right - previous
                if (this.swipeIndex > 0) {
                    this.swipeIndex--;
                }
            }
        }
    }))
})
"""


# Usage in route
from monsterui.franken import Script

def habits_mobile_page(habits: list[dict]) -> Div:
    cards = [{"title": h["name"], "content": h["description"]} for h in habits]

    return Div(
        SwipeableCards.render(cards),
        Script(SwipeableCards.get_swipe_script()),
    )
```

## Collapsible Section Pattern

```python
from monsterui.franken import Div, Button, H3, Span


def collapsible_section(title: str, content: Div, initially_open: bool = False) -> Div:
    """
    Collapsible section with animated expand/collapse.

    Args:
        title: Section title
        content: Section content (any FastHTML element)
        initially_open: Whether to start expanded
    """
    open_state = "true" if initially_open else "false"

    return Div(
        Button(
            Div(
                H3(title, cls="text-lg font-semibold"),
                Span(
                    **{"x-text": "expanded ? '▲' : '▼'"},
                    cls="text-gray-500"
                ),
                cls="flex justify-between items-center w-full"
            ),
            cls="w-full text-left p-4 bg-gray-100 hover:bg-gray-200",
            **{"x-on:click": "expanded = !expanded"}
        ),
        Div(
            content,
            cls="p-4",
            **{"x-show": "expanded", "x-transition": "", "x-collapse": ""}
        ),
        cls="border rounded",
        **{"x-data": f"{{ expanded: {open_state} }}"}
    )


# Usage
section = collapsible_section(
    title="Behavior Design",
    content=Div(
        Div(P("Cue:", cls="font-semibold"), P("Morning alarm")),
        Div(P("Routine:", cls="font-semibold"), P("5 minute stretch")),
        Div(P("Reward:", cls="font-semibold"), P("Coffee")),
    )
)
```

## Form Validation Pattern

```python
from monsterui.franken import Form, Div, Label, Input, Button, Span


def validated_form(action: str) -> Form:
    """
    Form with Alpine.js client-side validation + HTMX submission.

    Combines:
    - Alpine.js for immediate validation feedback
    - HTMX for form submission
    """
    return Form(
        Div(
            Label("Email", fr="email"),
            Input(
                type="email",
                name="email",
                id="email",
                required=True,
                cls="w-full border rounded p-2",
                **{"x-model": "email"}
            ),
            Span(
                "Please enter a valid email",
                cls="text-red-500 text-sm",
                **{"x-show": "email && !emailValid"}
            ),
            cls="mb-4"
        ),
        Div(
            Label("Password", fr="password"),
            Input(
                type="password",
                name="password",
                id="password",
                required=True,
                minlength="8",
                cls="w-full border rounded p-2",
                **{"x-model": "password"}
            ),
            Span(
                "Password must be at least 8 characters",
                cls="text-red-500 text-sm",
                **{"x-show": "password && password.length < 8"}
            ),
            cls="mb-4"
        ),
        Button(
            "Submit",
            type="submit",
            cls="btn btn-primary",
            **{
                "x-bind:disabled": "!formValid",
                "x-bind:class": "{ 'opacity-50 cursor-not-allowed': !formValid }"
            }
        ),
        hx_post=action,
        hx_target="#result",
        **{
            "x-data": """{
                email: '',
                password: '',
                get emailValid() { return /^[^@]+@[^@]+\\.[^@]+$/.test(this.email) },
                get formValid() { return this.emailValid && this.password.length >= 8 }
            }"""
        }
    )
```

## Progress Indicator Pattern

```python
from monsterui.franken import Div, Button, Span


def action_button_with_progress(text: str, action_url: str, target: str) -> Div:
    """
    Button that shows loading state during HTMX request.

    Uses Alpine.js for loading state, HTMX for the request.
    """
    return Div(
        Button(
            Span(text, **{"x-show": "!loading"}),
            Span(
                # Loading spinner (inline SVG or text)
                "Loading...",
                cls="flex items-center gap-2",
                **{"x-show": "loading"}
            ),
            cls="btn btn-primary",
            hx_post=action_url,
            hx_target=target,
            **{"x-bind:disabled": "loading"}
        ),
        **{
            "x-data": "{ loading: false }",
            "x-on:htmx:before-request": "loading = true",
            "x-on:htmx:after-request": "loading = false"
        }
    )
```

## Alpine Helper Functions

Utility functions to reduce boilerplate.

```python
from typing import Any


def alpine_data(data: dict[str, Any]) -> dict[str, str]:
    """
    Convert Python dict to Alpine x-data attribute.

    Usage:
        Div(**alpine_data({"count": 0, "open": False}))
    """
    import json
    # Convert Python booleans to JavaScript booleans
    js_data = json.dumps(data).replace("True", "true").replace("False", "false")
    return {"x-data": js_data}


def alpine_show(condition: str) -> dict[str, str]:
    """x-show attribute helper."""
    return {"x-show": condition}


def alpine_on(event: str, handler: str) -> dict[str, str]:
    """x-on attribute helper."""
    return {f"x-on:{event}": handler}


def alpine_bind(attr: str, expression: str) -> dict[str, str]:
    """x-bind attribute helper."""
    return {f"x-bind:{attr}": expression}


def alpine_transition() -> dict[str, str]:
    """Default x-transition attribute."""
    return {"x-transition": ""}


# Usage
from monsterui.franken import Div, Button, P

def example_component():
    return Div(
        Button("Toggle", **alpine_on("click", "open = !open")),
        P(
            "Content",
            **alpine_show("open"),
            **alpine_transition()
        ),
        **alpine_data({"open": False})
    )
```

## Visualization Pattern

SKUEL provides Alpine components for Chart.js, Vis.js Timeline, and Frappe Gantt. These are documented in detail in the Chart.js Skill.

### Quick Chart Example

```python
from components.visualization_components import create_chart_view

def analytics_section(user_uid: str) -> Div:
    """Analytics section with chart."""
    return Div(
        H2("Analytics"),
        create_chart_view(
            data_url=f"/api/visualizations/completion?user_uid={user_uid}",
            chart_type="line",
            title="Task Completion",
        ),
    )
```

### Chart with Dynamic Refresh

```python
def filterable_chart(user_uid: str) -> Div:
    """Chart that updates on filter change."""
    return Div(
        # Filter selector
        Select(
            Option("Week", value="week"),
            Option("Month", value="month"),
            name="period",
            hx_get="/partials/chart",
            hx_trigger="change",
            hx_target="#chart-container",
        ),
        # Chart container (replaced by HTMX)
        Div(
            create_chart_view(
                f"/api/visualizations/completion?user_uid={user_uid}&period=week",
                "line",
                "Completion Rate",
            ),
            id="chart-container",
        ),
    )
```

### Multiple Charts (Scripts Once)

```python
def multi_chart_page(user_uid: str) -> Div:
    """Page with multiple charts - load scripts only once."""
    return Div(
        create_chart_view(
            f"/api/visualizations/completion?user_uid={user_uid}",
            "line",
            "Completion",
            include_scripts=True,  # First chart loads scripts
        ),
        create_chart_view(
            f"/api/visualizations/priority-distribution?user_uid={user_uid}",
            "doughnut",
            "Priorities",
            include_scripts=False,  # Subsequent charts skip scripts
        ),
    )
```

**See:** Chart.js Skill for comprehensive visualization patterns.

## Best Practices

### 1. Keep Alpine Data Close to Usage

```python
# GOOD: Alpine state scoped to component
def toggle_button():
    return Button(
        "Toggle",
        **{"x-data": "{ on: false }", "x-on:click": "on = !on"}
    )

# AVOID: Global state when local suffices
# Instead use Alpine.store() only for truly global state
```

### 2. Use Descriptive x-ref Names

```python
# GOOD
Input(**{"x-ref": "emailInput"})
Button(**{"x-on:click": "$refs.emailInput.focus()"})

# AVOID
Input(**{"x-ref": "i1"})  # Unclear
```

### 3. Extract Complex Logic to Alpine.data()

```python
# For simple components: inline x-data
Div(**{"x-data": "{ count: 0 }"})

# For complex components: use Alpine.data()
# Define in a separate Script() element
Script("""
document.addEventListener('alpine:init', () => {
    Alpine.data('complexComponent', () => ({
        // Complex state and methods here
    }))
})
""")
```

### 4. Combine Alpine Events with HTMX

```python
# Alpine for UI state, HTMX for server communication
Div(
    Button(
        "Save",
        hx_post="/api/save",
        hx_target="#result",
        **{"x-bind:disabled": "saving"}
    ),
    **{
        "x-data": "{ saving: false }",
        "x-on:htmx:before-request": "saving = true",
        "x-on:htmx:after-request": "saving = false"
    }
)
```

### 5. Use Type Hints for Clarity

```python
from typing import Any

def create_component(
    title: str,
    alpine_state: dict[str, Any] | None = None
) -> Div:
    """
    Args:
        title: Component title
        alpine_state: Initial Alpine.js state (e.g., {"open": False})
    """
    state = alpine_state or {"open": False}
    return Div(
        H2(title),
        **alpine_data(state)
    )
```
