# Tailwind CSS + FastHTML Integration

## Core Patterns

### Basic Class Application

```python
from fasthtml.common import *
from monsterui.all import *

# Single class string
Div("Content", cls="flex items-center justify-center")

# Multiple classes as string
Div("Card", cls="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow")

# Tuple for combining multiple sources (MonsterUI + Tailwind)
Button("Submit", cls=(ButtonT.primary, "w-full mt-4 shadow-lg"))

# Empty string is safe
Div("Content", cls="")  # Works fine
```

### Responsive Classes

```python
# Mobile-first: base → sm → md → lg → xl
Div(
    "Responsive text",
    cls="text-sm md:text-base lg:text-lg xl:text-xl"
)

# Responsive grid
Grid(
    Card("Item 1"),
    Card("Item 2"),
    Card("Item 3"),
    Card("Item 4"),
    cls="grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
)

# Responsive visibility
Div(
    Div("Mobile menu", cls="lg:hidden"),
    Div("Desktop menu", cls="hidden lg:flex gap-6"),
)

# Responsive layout direction
Div(
    Aside("Sidebar", cls="w-full lg:w-64"),
    Main("Content", cls="flex-1"),
    cls="flex flex-col lg:flex-row gap-4"
)
```

### Dark Mode

MonsterUI's `Theme.blue.headers(mode="auto")` enables dark mode. Use `dark:` prefix:

```python
# Background and text
Card(
    H3("Title", cls="text-gray-900 dark:text-white"),
    P("Description", cls="text-gray-600 dark:text-gray-400"),
    cls="bg-white dark:bg-gray-800 border dark:border-gray-700"
)

# Dark mode hover states
Button(
    "Action",
    cls="bg-blue-600 dark:bg-blue-500 hover:bg-blue-700 dark:hover:bg-blue-400 text-white"
)
```

### Combining with Alpine.js

Use `**kwargs` for Alpine directives alongside Tailwind classes:

```python
# Toggle visibility
Div(
    Button("Toggle", **{"@click": "open = !open"}),
    Div(
        "Dropdown content",
        cls="mt-2 p-4 bg-white rounded-lg shadow-lg",
        **{"x-show": "open", "x-transition": ""}
    ),
    cls="relative",
    **{"x-data": "{ open: false }"}
)

# Conditional classes with Alpine
Div(
    "Tab content",
    cls="p-4 rounded-lg",
    **{"x-bind:class": "active ? 'bg-blue-100 border-blue-500' : 'bg-gray-50'"}
)

# Loading state
Button(
    Span("Submit", **{"x-show": "!loading"}),
    Span("Loading...", cls="flex items-center gap-2", **{"x-show": "loading"}),
    cls=ButtonT.primary,
    **{"x-data": "{ loading: false }", "@click": "loading = true"}
)
```

## Layout Components

### Flexbox Patterns

```python
# Centered content
Div(
    "Centered",
    cls="flex items-center justify-center min-h-screen"
)

# Space between (header pattern)
Div(
    A("Brand", href="/", cls="text-xl font-bold"),
    Nav(
        A("Home", href="/"),
        A("About", href="/about"),
        cls="flex gap-6"
    ),
    cls="flex items-center justify-between p-4"
)

# MonsterUI equivalents (preferred)
DivFullySpaced(left_content, right_content)  # justify-between
DivCentered(content)                          # justify-center
DivLAligned(icon, text)                       # justify-start
DivRAligned(button)                           # justify-end
DivHStacked(icon, label)                      # flex + gap (horizontal)
DivVStacked(title, subtitle)                  # flex-col + gap (vertical)
```

### Grid Patterns

```python
# Basic grid
Div(
    *[Card(f"Item {i}") for i in range(6)],
    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
)

# MonsterUI Grid (preferred)
Grid(
    *[Card(f"Item {i}") for i in range(6)],
    cols=3,  # Responsive by default
    cls="gap-6"
)

# 12-column layout
Div(
    Aside("Sidebar", cls="col-span-12 lg:col-span-3"),
    Main("Content", cls="col-span-12 lg:col-span-9"),
    cls="grid grid-cols-12 gap-4"
)

# Auto-fit (as many as fit)
Div(
    *cards,
    cls="grid grid-cols-[repeat(auto-fit,minmax(250px,1fr))] gap-4"
)
```

## Component Patterns

### Card with Tailwind Customization

```python
def TaskCard(task):
    """Task card combining MonsterUI + Tailwind."""
    status_border = {
        "completed": "border-l-green-500",
        "in_progress": "border-l-blue-500",
        "pending": "border-l-gray-300"
    }.get(task.status, "border-l-gray-300")

    return Card(
        DivFullySpaced(
            DivHStacked(
                UkIcon("check" if task.completed else "circle", height=20),
                H4(task.title, cls="font-medium")
            ),
            Span(task.due_date, cls="text-sm text-gray-500")
        ),
        P(task.description, cls=TextPresets.muted_sm),
        cls=f"border-l-4 {status_border} hover:shadow-md transition-shadow",
        id=f"task-{task.id}"
    )
```

### Form with Mixed Styling

```python
def ContactForm():
    return Form(
        # MonsterUI labeled inputs
        LabelInput("Name", id="name", required=True),
        LabelInput("Email", type="email", id="email", required=True),
        LabelTextarea("Message", id="message", rows="4"),

        # Custom checkbox with Tailwind
        Div(
            Label(
                Input(type="checkbox", cls="checkbox checkbox-primary mr-2"),
                Span("Subscribe to newsletter", cls="text-sm"),
                cls="flex items-center cursor-pointer"
            ),
            cls="mt-4"
        ),

        # Button with Tailwind additions
        DivRAligned(
            Button("Send", type="submit", cls=(ButtonT.primary, "px-8"))
        ),

        cls="space-y-4 max-w-md mx-auto",
        action="/contact",
        method="post"
    )
```

### Navigation

```python
def Navbar(brand, links, user=None):
    return Nav(
        Div(
            # Logo
            A(brand, href="/", cls="text-xl font-bold text-gray-900 dark:text-white"),

            # Desktop nav
            Div(
                *[A(text, href=href, cls="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors")
                  for text, href in links],
                cls="hidden md:flex items-center gap-6"
            ),

            # User menu or login
            Div(
                DiceBearAvatar(user.name, h=32, w=32) if user else
                Button("Login", cls=ButtonT.outline),
                cls="ml-auto"
            ),

            # Mobile menu button
            Button(
                UkIcon("menu", height=24),
                cls="md:hidden btn btn-ghost btn-square",
                **{"@click": "mobileOpen = !mobileOpen"}
            ),

            cls="flex items-center justify-between max-w-7xl mx-auto px-4 h-16"
        ),
        cls="bg-white dark:bg-gray-900 shadow-sm",
        **{"x-data": "{ mobileOpen: false }"}
    )
```

## Spacing & Sizing

### Consistent Spacing

```python
# Use Tailwind's scale for consistency
# p-1=4px, p-2=8px, p-4=16px, p-6=24px, p-8=32px

# Card spacing
Card(content, cls="p-6")           # Standard
Card(content, cls="p-4")           # Compact
Card(content, cls="p-8")           # Spacious

# Stack spacing
Div(*items, cls="space-y-4")       # Vertical gap
Div(*items, cls="space-x-4")       # Horizontal gap
Div(*items, cls="flex gap-4")      # Flex gap (preferred)

# Section margins
Section(content, cls="py-16 px-4") # Page section
Div(content, cls="mt-8 mb-4")      # Content block
```

### Max Width Containers

```python
# Centered container with max width
Div(
    content,
    cls="max-w-7xl mx-auto px-4"  # 1280px max, centered, side padding
)

# Prose width for text
Div(
    article_content,
    cls="max-w-prose mx-auto"     # 65ch optimal reading width
)

# Responsive max width
Div(
    form,
    cls="max-w-sm md:max-w-md lg:max-w-lg mx-auto"
)
```

## State & Interaction

### Hover Effects

```python
# Card hover
Card(
    content,
    cls="hover:shadow-lg hover:-translate-y-1 transition-all duration-200 cursor-pointer"
)

# Link hover
A("Learn more", href="/more", cls="text-blue-600 hover:text-blue-800 hover:underline")

# Button hover (MonsterUI handles this, but for custom)
Div(
    content,
    cls="bg-gray-100 hover:bg-gray-200 active:bg-gray-300 transition-colors"
)
```

### Focus States

```python
# Input focus
Input(
    type="text",
    cls="border border-gray-300 rounded-lg px-4 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none transition"
)

# Focus-visible (keyboard only)
Button(
    "Action",
    cls="focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
)
```

### Group Hover

```python
# Parent hover affects children
Div(
    UkIcon("arrow-right", cls="group-hover:translate-x-1 transition-transform"),
    Span("View details", cls="group-hover:text-blue-600"),
    cls="group flex items-center gap-2 cursor-pointer"
)
```

## Anti-Patterns

### ❌ Don't: Raw Tailwind for Standard Components

```python
# BAD: Reinventing the wheel
Button("Submit", cls="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700")

# GOOD: Use MonsterUI
Button("Submit", cls=ButtonT.primary)
```

### ❌ Don't: Inconsistent Spacing

```python
# BAD: Arbitrary values everywhere
Div(cls="p-[13px] mt-[27px] gap-[9px]")

# GOOD: Use Tailwind's scale
Div(cls="p-4 mt-6 gap-2")
```

### ❌ Don't: Color Hardcoding in Dark Mode Apps

```python
# BAD: Won't adapt to dark mode
Card(cls="bg-white text-black")

# GOOD: Use semantic colors
Card(cls="bg-base-100 text-base-content")
```

### ❌ Don't: Overly Long Class Strings

```python
# BAD: Hard to read and maintain
Div(cls="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 p-4 md:p-6 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:shadow-lg transition-shadow duration-200")

# GOOD: Break into logical groups or extract component
def ResponsiveCard(children):
    return Div(
        children,
        cls=" ".join([
            "flex flex-col md:flex-row",
            "items-start md:items-center justify-between",
            "gap-4 p-4 md:p-6",
            "bg-white dark:bg-gray-800",
            "rounded-lg shadow-md hover:shadow-lg transition-shadow"
        ])
    )
```

## See Also

- [SKILL.md](SKILL.md) - Core Tailwind concepts
- [decision-guide.md](decision-guide.md) - When to use Tailwind vs MonsterUI vs DaisyUI
- [utilities-reference.md](utilities-reference.md) - Complete utility class reference
- MonsterUI Skill - Pre-styled FastHTML components
- Alpine.js Skill - Client-side interactivity patterns
