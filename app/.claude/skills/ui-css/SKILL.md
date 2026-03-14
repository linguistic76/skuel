---
name: ui-css
description: Expert guide for SKUEL's CSS layer — MonsterUI (FrankenUI + Tailwind) components. Use when styling components, choosing between CSS layers, implementing responsive layouts, working with MonsterUI components (buttons, forms, modals, cards, navbar), or when the user mentions MonsterUI, FrankenUI, Tailwind, CSS, styling, component library, responsive design, or dark mode.
allowed-tools: Read, Grep, Glob
---

# SKUEL CSS Layer: MonsterUI + Tailwind

## Core Philosophy

> "Semantic component classes that compose with Tailwind utilities — start with the most specific, fall back to utilities."

SKUEL uses a **two-layer CSS architecture**:

| Layer | Library | Decision Rule | Example |
|-------|---------|---------------|---------|
| **Component** | MonsterUI wrappers | Pre-built FastHTML components | `Button(variant=ButtonT.primary)`, `Alert(variant=AlertT.error)` |
| **Utility** | Tailwind | Custom spacing, layout, one-off adjustments | `flex gap-4 p-6 rounded-lg` |

**Decision Rule:** MonsterUI wrapper first → Tailwind utilities for customization

```python
# ✅ MonsterUI wrapper component + Tailwind customization
Button("Save", variant=ButtonT.primary, cls="w-full mt-4")

# ✅ MonsterUI wrapper for forms
Checkbox(name="agree", cls="uk-checkbox")

# ⚠️ Avoid raw Tailwind when MonsterUI has a wrapper
Button("Save", cls="bg-blue-600 text-white px-4 py-2 rounded")  # Use variant=ButtonT.primary
```

## FastHTML Integration

Tailwind and MonsterUI classes work via `cls=` in FastHTML:

```python
# Single string
Div("Content", cls="flex items-center gap-4 p-6")

# Tuple: combine MonsterUI token + Tailwind utilities
Button("Submit", cls=(ButtonT.primary, "w-full shadow-lg"))

# With Alpine.js directives via **kwargs
Div(
    "Content",
    cls="p-4 bg-base-100 rounded-lg",
    **{"x-show": "open", "x-transition": ""}
)
```

---

## MonsterUI Wrapper Component Reference

All UI components use Python wrapper functions. Import from the appropriate module.

### Buttons

```python
from ui.buttons import Button, ButtonT, ButtonLink, IconButton
from ui.layout import Size

# Variants
Button("Primary", variant=ButtonT.primary)
Button("Secondary", variant=ButtonT.secondary)
Button("Ghost", variant=ButtonT.ghost)
Button("Error", variant=ButtonT.error)
Button("Success", variant=ButtonT.success)

# Sizes
Button("Small", variant=ButtonT.primary, size=Size.sm)
Button("Large", variant=ButtonT.primary, size=Size.lg)

# Link styled as button
ButtonLink("View Details", href="/tasks/123", variant=ButtonT.ghost)

# Icon button
IconButton("pencil", variant=ButtonT.ghost, size=Size.sm)
```

### Form Controls

```python
from ui.forms import FormControl, Label, LabelText, Input, Select, Textarea, Checkbox, Radio, Toggle

# Text input
Input(type="text", name="title", placeholder="Enter text", cls="uk-input w-full")

# Select
Select(
    Option("Pick one", disabled=True, selected=True),
    Option("Option 1", value="1"),
    name="choice", cls="uk-select w-full",
)

# Textarea
Textarea(name="description", rows=4, cls="uk-textarea w-full")

# Checkbox
Checkbox(name="agree", cls="uk-checkbox")

# Toggle
Toggle(name="enabled")

# Radio
Radio(name="priority", value="high")
```

### FormControl Pattern (SKUEL Standard)

Always wrap inputs in `FormControl` + `Label` for accessibility:

```python
from ui.forms import FormControl, Label, LabelText, Input

FormControl(
    Label(LabelText("Email *")),
    Input(type="email", name="email", required=True, cls="uk-input w-full"),
)
```

### Cards

```python
# Using design tokens (preferred)
from ui.tokens import Card

# Basic card
Div(content, cls=Card.BASE)  # "bg-base-100 border border-base-200 rounded-lg"

# Interactive card
Div(content, cls=Card.INTERACTIVE)  # BASE + "hover:shadow-md transition-shadow"
```

### Badges

```python
from ui.feedback import Badge, BadgeT
from ui.layout import Size

Badge("Default")
Badge("Primary", variant=BadgeT.primary)
Badge("Success", variant=BadgeT.success)
Badge("Warning", variant=BadgeT.warning)
Badge("Error", variant=BadgeT.error)
Badge("Ghost", variant=BadgeT.ghost)

# Sizes
Badge("Small", variant=BadgeT.success, size=Size.sm)
```

### Alerts

```python
from ui.feedback import Alert, AlertT

Alert("Info message", variant=AlertT.info)
Alert("Success message", variant=AlertT.success)
Alert("Warning message", variant=AlertT.warning)
Alert("Error message", variant=AlertT.error)
```

### Modals

```python
from ui.buttons import Button, ButtonT
from ui.modals import Modal, ModalBox, ModalAction, ModalBackdrop

Dialog(
    ModalBox(
        H3("Modal Title", cls="font-bold text-lg"),
        P("Modal content here", cls="py-4"),
        ModalAction(
            Button("Cancel", variant=ButtonT.ghost),
            Button("Confirm", variant=ButtonT.primary),
        ),
    ),
    ModalBackdrop(),
    id="my_modal",
    cls="modal",
)
```

### Navbar

```python
# Navbar uses Tailwind utilities directly (no wrapper needed)
Nav(
    Div(A("Brand", href="/", cls="text-xl font-bold"), cls="navbar-start"),
    Div(
        A("Tasks", href="/tasks", cls="text-sm hover:text-primary"),
        A("Goals", href="/goals", cls="text-sm hover:text-primary"),
        cls="navbar-center hidden sm:flex gap-4",
    ),
    Div(A("Profile", href="/profile"), cls="navbar-end"),
    cls="bg-white border-b border-gray-200 sticky top-0 z-50 px-4 py-2",
)
```

### Loading

```python
from ui.feedback import Loading, LoadingT
from ui.layout import Size

Loading(variant=LoadingT.spinner, size=Size.sm)
Loading(variant=LoadingT.spinner, size=Size.md)
Loading(variant=LoadingT.dots)
```

### Tables

```python
from ui.data import Table

# Striped table
Table(thead, tbody, cls="uk-table uk-table-striped")
```

### Dividers

```python
from ui.data import Divider

Divider()  # renders border-t border-border my-4
```

---

## Tailwind Utility Reference

### Layout — Flexbox

```html
<!-- Row with gap -->
<div class="flex items-center gap-4">

<!-- Space between (navbar pattern) -->
<div class="flex items-center justify-between">

<!-- Column stack -->
<div class="flex flex-col gap-4">

<!-- Responsive: column on mobile, row on desktop -->
<div class="flex flex-col md:flex-row gap-4">
  <aside class="w-full md:w-64">Sidebar</aside>
  <main class="flex-1">Content</main>
</div>
```

### Layout — Grid

```html
<!-- Responsive grid -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">

<!-- Dashboard 12-column -->
<div class="grid grid-cols-12 gap-4">
  <aside class="col-span-12 lg:col-span-3">Sidebar</aside>
  <main class="col-span-12 lg:col-span-9">Content</main>
</div>
```

### Spacing Scale (1 unit = 4px)

| Class | Value | Use |
|-------|-------|-----|
| `p-2` | 8px | Tight padding |
| `p-4` | 16px | Standard padding |
| `p-6` | 24px | Comfortable padding |
| `p-8` | 32px | Large sections |
| `gap-2` | 8px | Tight spacing |
| `gap-4` | 16px | Standard gap |
| `space-y-4` | 16px | Stack spacing |

**Directional:** `px-*` (horizontal), `py-*` (vertical), `pt/pr/pb/pl-*`

### Typography

```html
<!-- Heading hierarchy -->
<h1 class="text-2xl font-bold text-base-content">Page Title</h1>
<h2 class="text-xl font-semibold">Section</h2>
<h3 class="text-lg font-medium">Subsection</h3>
<p class="text-base text-base-content/70">Body text</p>
<p class="text-sm text-base-content/50">Secondary text</p>
<p class="text-xs uppercase tracking-wide font-semibold">Label</p>
```

| Class | Size | Use |
|-------|------|-----|
| `text-xs` | 12px | Labels, metadata |
| `text-sm` | 14px | Secondary, captions |
| `text-base` | 16px | Body text |
| `text-lg` | 18px | Lead text |
| `text-xl` | 20px | Card titles |
| `text-2xl` | 24px | Page headings |

### Responsive Breakpoints (mobile-first)

| Prefix | Min Width | Usage |
|--------|-----------|-------|
| (none) | 0px | Mobile default |
| `sm:` | 640px | Small tablet |
| `md:` | 768px | Tablet |
| `lg:` | 1024px | Desktop |
| `xl:` | 1280px | Wide desktop |

```html
<!-- Mobile: stack, Desktop: side-by-side -->
<div class="flex flex-col lg:flex-row gap-4">

<!-- Hide on mobile -->
<div class="hidden lg:block">Desktop only</div>
<div class="lg:hidden">Mobile only</div>
```

### Semantic Color Tokens (use these instead of Tailwind palette)

| Token | Use |
|-------|-----|
| `bg-base-100` | Default background |
| `bg-base-200` | Slightly darker surface |
| `bg-base-300` | Borders, dividers |
| `text-base-content` | Primary text |
| `text-base-content/70` | Secondary text |
| `text-base-content/50` | Muted text |
| `border-base-200` | Subtle borders |
| `bg-primary` / `text-primary` | Brand color |
| `bg-success` / `text-success` | Success state |
| `bg-error` / `text-error` | Error state |
| `bg-warning` / `text-warning` | Warning state |

**Key rule:** Always use semantic tokens (`bg-base-100`, `text-primary`) not Tailwind palette (`bg-white`, `bg-blue-600`). Semantic tokens respect the active theme automatically.

### States & Interactions

```html
<button class="btn hover:shadow-lg active:scale-95 transition">Button</button>
<div class="group hover:bg-base-200">
  <span class="group-hover:text-primary">Changes on parent hover</span>
</div>
<input class="input focus:input-primary transition">
<button class="disabled:opacity-50 disabled:cursor-not-allowed" disabled>
```

### Animations

```html
<div class="transition duration-200 ease-in-out hover:scale-105">
<div class="transition-colors duration-300 hover:bg-base-200">
<div class="animate-pulse">Loading...</div>
<div class="animate-spin">Spinner</div>
```

---

## SKUEL Design Tokens

Use tokens from `/ui/tokens.py` instead of hardcoded classes:

```python
from ui.tokens import Container, Spacing, Card

# Containers
Container.STANDARD  # "max-w-6xl mx-auto"  — use for all standard pages
Container.NARROW    # "max-w-4xl mx-auto"
Container.WIDE      # "max-w-7xl mx-auto"

# Spacing
Spacing.PAGE        # "p-6 lg:p-8"   — page-level padding
Spacing.SECTION     # "space-y-8"    — between sections
Spacing.CONTENT     # "space-y-4"    — between items

# Cards
Card.BASE           # "bg-base-100 border border-base-200 rounded-lg"
Card.INTERACTIVE    # BASE + "hover:shadow-md transition-shadow"
Card.PADDING        # "p-6"
```

---

## Theming

Theme selection is available on `/profile/settings` (Display & Appearance section). The selected theme is saved to Neo4j preferences and localStorage. On page load, `base_page.py` reads from localStorage via `x-init` and applies the theme. Default: `light`.

---

## Custom CSS Boundary

| Pattern | Tool |
|---------|------|
| Standard spacing/layout | Tailwind utilities |
| Repeated semantic components | MonsterUI classes |
| Repeated 5+ times | `@apply` in component class |
| Complex animations/pseudo | Custom CSS |
| Design tokens | CSS variables in `/ui/tokens.py` |

```css
/* ✅ @apply only for repeated patterns (5+ uses) */
@layer components {
  .entity-card {
    @apply bg-base-100 border border-base-200 rounded-lg p-4;
    @apply hover:shadow-md transition-shadow;
  }
}
```

---

## Best Practices

1. **Semantic HTML first** — use `<article>`, `<section>`, `<nav>`, not divs for everything
2. **Mobile-first** — apply base classes for mobile, add `md:` / `lg:` prefixes for larger screens
3. **semantic tokens over Tailwind palette** — `text-base-content` not `text-gray-900`
4. **Design tokens over magic numbers** — `Container.STANDARD` not `max-w-6xl mx-auto` repeated
5. **`cls` parameter for extensibility** — components accept extra classes via `cls` parameter

## Anti-Patterns

```python
# ❌ Raw Tailwind when MonsterUI has it
Div("Error", cls="bg-red-100 text-red-800 p-3 rounded")  # Use Alert(variant=AlertT.error)

# ❌ Tailwind palette instead of semantic tokens
P("Text", cls="text-gray-600")  # Use text-base-content/70

# ❌ Hardcoded container widths
Div(cls="max-w-6xl mx-auto")  # Use Container.STANDARD

# ❌ Inconsistent spacing
Div(cls="p-5")  # Use p-4 or p-6 (standard scale)
```

## Key Files

| File | Purpose |
|------|---------|
| `/ui/tokens.py` | Design tokens (Container, Spacing, Card) |
| `/static/css/main.css` | Custom CSS and `@apply` patterns |
| `/static/css/output.css` | Compiled Tailwind output |
| `ui/buttons.py`, `ui/cards.py`, `ui/forms/`, `ui/modals.py`, `ui/feedback.py`, `ui/layout.py`, `ui/navigation.py`, `ui/data.py` | FastHTML MonsterUI component wrappers — 8 focused modules (March 2026) |

## See Also

- `skuel-ui` — SKUEL-specific UI patterns (pages, forms, navigation, components)
- `ui-browser` — HTMX + Alpine.js interactivity layer
- Tailwind Docs: https://tailwindcss.com/docs
- MonsterUI docs: see monsterui package
