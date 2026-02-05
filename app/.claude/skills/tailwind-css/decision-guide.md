# CSS Decision Guide: MonsterUI vs DaisyUI vs Tailwind

## The Layered Architecture

SKUEL uses three CSS layers, each with a specific purpose:

```
┌─────────────────────────────────────────────────────┐
│  MonsterUI (Component Layer)                        │
│  ButtonT, Card, Grid, LabelInput, TextPresets       │
│  → Use FIRST for standard UI components             │
├─────────────────────────────────────────────────────┤
│  DaisyUI (Semantic Layer)                           │
│  btn, modal, drawer, toggle, tabs, badge            │
│  → Use when MonsterUI doesn't have the component    │
├─────────────────────────────────────────────────────┤
│  Tailwind (Utility Layer)                           │
│  flex, gap, p-4, rounded-lg, hover:shadow-lg        │
│  → Use for customization and one-off styling        │
└─────────────────────────────────────────────────────┘
```

## Quick Decision Flowchart

```
Need to style something?
│
├── Is it a standard component (button, card, form input)?
│   │
│   ├── YES → Does MonsterUI have it?
│   │         │
│   │         ├── YES → Use MonsterUI (ButtonT.primary, Card, LabelInput)
│   │         │
│   │         └── NO → Does DaisyUI have it?
│   │                  │
│   │                  ├── YES → Use DaisyUI (btn-primary, modal, toggle)
│   │                  │
│   │                  └── NO → Build with Tailwind utilities
│   │
│   └── NO → Is it layout/spacing/custom styling?
│            │
│            └── YES → Use Tailwind utilities (flex, p-4, mt-6)
```

## Component Lookup Table

| Need | First Choice | Fallback | Example |
|------|--------------|----------|---------|
| **Buttons** | `ButtonT.primary/secondary/destructive` | `btn btn-primary` | `Button("Save", cls=ButtonT.primary)` |
| **Cards** | `Card()` | `card bg-base-100` | `Card(content, cls="shadow-md")` |
| **Grid layout** | `Grid(cols=3)` | `grid grid-cols-3` | `Grid(*items, cols=3, cls="gap-4")` |
| **Form inputs** | `LabelInput()` | `input input-bordered` | `LabelInput("Email", type="email")` |
| **Text styles** | `TextPresets.muted` | `text-gray-500` | `P("Note", cls=TextPresets.muted_sm)` |
| **Icons** | `UkIcon("home")` | — | `UkIcon("check", height=20)` |
| **Avatars** | `DiceBearAvatar()` | `avatar` | `DiceBearAvatar("Alice", h=40, w=40)` |
| **Modals** | — | `dialog.modal` | Use DaisyUI modal pattern |
| **Toggles** | — | `toggle toggle-primary` | `Input(cls="toggle toggle-primary")` |
| **Tabs** | — | `tabs tabs-bordered` | Use DaisyUI tabs pattern |
| **Badges** | — | `badge badge-primary` | `Span("New", cls="badge badge-primary")` |
| **Drawers** | — | `drawer drawer-open` | Use DaisyUI drawer pattern |
| **Dropdowns** | — | `dropdown` | Use DaisyUI + Alpine |
| **Loading** | — | `loading loading-spinner` | `Span(cls="loading loading-spinner")` |
| **Alerts** | — | `alert alert-success` | Use DaisyUI alert pattern |
| **Navbar** | — | `navbar bg-white border-b border-gray-200` | Use DaisyUI navbar pattern |

## When to Use Each Layer

### MonsterUI (Default Choice)

**Use for:**
- Buttons → `ButtonT.primary`, `ButtonT.outline`, `ButtonT.ghost`
- Cards → `Card(content, footer=actions)`
- Forms → `LabelInput`, `LabelTextarea`, `LabelCheckboxX`
- Layout → `Grid`, `DivFullySpaced`, `DivHStacked`, `DivVStacked`
- Typography → `TextPresets.muted`, `TextPresets.lead`, `TextPresets.bold_lg`
- Icons → `UkIcon("name", height=20)`

**Why:** Pre-styled, accessible, consistent with SKUEL theme.

```python
# ✅ MonsterUI button
Button("Submit", cls=ButtonT.primary)

# ✅ MonsterUI card with layout
Card(
    DivFullySpaced(
        H3("Title"),
        UkIcon("edit", height=16)
    ),
    P("Description", cls=TextPresets.muted),
    footer=DivRAligned(
        Button("Save", cls=ButtonT.primary)
    )
)
```

### DaisyUI (When MonsterUI Lacks Component)

**Use for:**
- Modals/Dialogs → `dialog.modal`, `modal-box`
- Toggles/Switches → `toggle toggle-primary`
- Tabs → `tabs tabs-bordered`
- Badges → `badge badge-success`
- Drawers/Sidebars → `drawer lg:drawer-open`
- Progress indicators → `progress progress-primary`, `loading loading-spinner`
- Alerts → `alert alert-info`
- Menus → `menu`, `dropdown`

**Why:** CSS-only components that integrate with MonsterUI's theme.

```python
# ✅ DaisyUI toggle (MonsterUI doesn't have this)
Label(
    Span("Dark mode"),
    Input(type="checkbox", cls="toggle toggle-primary"),
    cls="flex items-center gap-2 cursor-pointer"
)

# ✅ DaisyUI badge
Span("New", cls="badge badge-primary")

# ✅ DaisyUI loading spinner
Span(cls="loading loading-spinner loading-md")
```

### Tailwind (Customization Layer)

**Use for:**
- Layout utilities → `flex`, `grid`, `gap-4`, `justify-between`
- Spacing → `p-4`, `mt-6`, `space-y-4`
- Sizing → `w-full`, `max-w-md`, `h-screen`
- Colors (custom) → `bg-blue-50`, `text-gray-600`, `border-green-500`
- Responsive modifiers → `md:flex`, `lg:grid-cols-3`
- States → `hover:shadow-lg`, `focus:ring-2`, `group-hover:text-blue-600`
- Transitions → `transition-all`, `duration-200`
- One-off styling → `rounded-2xl`, `shadow-xl`, `ring-2`

**Why:** Fine-grained control for layout and custom styling.

```python
# ✅ Tailwind for layout + MonsterUI for components
Div(
    Card("Item 1"),
    Card("Item 2"),
    cls="flex flex-col md:flex-row gap-4 p-6"
)

# ✅ Tailwind to extend MonsterUI
Card(
    content,
    cls="hover:shadow-lg transition-shadow border-l-4 border-l-blue-500"
)

# ✅ Tailwind for responsive visibility
Div("Mobile only", cls="lg:hidden")
Div("Desktop only", cls="hidden lg:block")
```

## Combining Layers

The power is in combination. Use MonsterUI for components, DaisyUI for specialized UI, and Tailwind for customization:

```python
def StatusCard(item):
    """Example combining all three layers."""
    return Card(
        # MonsterUI layout
        DivFullySpaced(
            DivHStacked(
                UkIcon("file", height=20),  # MonsterUI icon
                H4(item.title)
            ),
            # DaisyUI badge
            Span(item.status, cls="badge badge-primary")
        ),
        P(item.description, cls=TextPresets.muted_sm),  # MonsterUI text

        # MonsterUI footer with DaisyUI loading + MonsterUI button
        footer=DivRAligned(
            Span(cls="loading loading-spinner loading-sm htmx-indicator"),
            Button("View", cls=ButtonT.outline, hx_get=f"/items/{item.id}")
        ),

        # Tailwind customization
        cls="hover:shadow-lg transition-shadow border-l-4 border-l-blue-500",
        id=f"item-{item.id}"
    )
```

## Common Mistakes

### ❌ Using Tailwind When MonsterUI Has It

```python
# BAD
Button("Submit", cls="bg-blue-600 text-white px-4 py-2 rounded-lg")

# GOOD
Button("Submit", cls=ButtonT.primary)
```

### ❌ Using DaisyUI When MonsterUI Has It

```python
# BAD
Button("Submit", cls="btn btn-primary")

# GOOD
Button("Submit", cls=ButtonT.primary)
```

### ❌ Forgetting to Combine Properly

```python
# BAD: Trying to use tuple with DaisyUI classes
Button("Action", cls=(ButtonT.primary, "btn-lg"))  # Conflicting

# GOOD: Pick one system for the component, use Tailwind for extras
Button("Action", cls=(ButtonT.primary, "w-full"))  # MonsterUI + Tailwind
Button("Action", cls="btn btn-primary btn-lg")     # Pure DaisyUI
```

### ❌ Hardcoding Colors

```python
# BAD: Won't adapt to dark mode
Div(cls="bg-white text-black")

# GOOD: Use semantic colors (from DaisyUI/MonsterUI theme)
Div(cls="bg-base-100 text-base-content")
```

## Summary

| Layer | Purpose | Examples |
|-------|---------|----------|
| **MonsterUI** | Standard components | `ButtonT`, `Card`, `Grid`, `LabelInput` |
| **DaisyUI** | Specialized UI components | `modal`, `toggle`, `tabs`, `badge`, `drawer` |
| **Tailwind** | Layout, spacing, customization | `flex`, `gap-4`, `hover:shadow-lg` |

**Rule of thumb:** If MonsterUI has it, use MonsterUI. If DaisyUI has it, use DaisyUI. Use Tailwind to customize and for layout.
