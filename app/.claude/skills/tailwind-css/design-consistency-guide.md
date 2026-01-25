# SKUEL Design Consistency Guide

**Purpose:** Enforce SKUEL design token usage and maintain visual consistency across the application

---

## SKUEL Design Token System

SKUEL uses a centralized design token system located in `/ui/tokens.py` to ensure visual consistency across all pages.

### Spacing Scale

**Location:** `/ui/tokens.py` - `Spacing` class

```python
from ui.tokens import Spacing

# STANDARD SPACING (use tokens)
Div(content, cls=Spacing.PAGE)           # p-6 lg:p-8 (page padding)
Div(*sections, cls=Spacing.SECTION)      # space-y-8 (between sections)
Div(*items, cls=Spacing.CONTENT)         # space-y-4 (between items)
Div(*cards, cls=Spacing.CARD_GRID)       # gap-6 (card grids)
Div(*form_fields, cls=Spacing.FORM)      # space-y-6 (form fields)

# ONE-OFF SPACING (use Tailwind directly)
Div(icon, text, cls="gap-2")             # Small gap between icon and text
Div(badge, label, cls="gap-3")           # Custom component spacing
```

### Container Widths

**Location:** `/ui/tokens.py` - `Container` class

```python
from ui.tokens import Container

Container.STANDARD  # max-w-6xl mx-auto px-6 lg:px-8 - Most pages
Container.NARROW    # max-w-4xl mx-auto px-6 lg:px-8 - Forms, articles
Container.WIDE      # max-w-7xl mx-auto px-6 lg:px-8 - Data tables, dashboards
Container.FULL      # w-full px-6 lg:px-8 - Edge-to-edge layouts
```

### Card Styles

**Location:** `/ui/tokens.py` - `Card` class

```python
from ui.tokens import Card

Card.STANDARD       # bg-base-100 border border-base-300 rounded-lg shadow-sm p-6
Card.HOVER          # Card.STANDARD + hover:shadow-md transition-shadow
Card.INTERACTIVE    # Card.HOVER + cursor-pointer
Card.COMPACT        # Same as STANDARD but p-4
```

### Typography Scale

**Location:** `/ui/tokens.py` - `Typography` class

```python
from ui.tokens import Typography

Typography.H1       # text-4xl font-bold text-base-content
Typography.H2       # text-3xl font-bold text-base-content
Typography.H3       # text-2xl font-semibold text-base-content
Typography.BODY     # text-base text-base-content
Typography.CAPTION  # text-sm text-base-content/70
```

---

## Token vs Tailwind Decision Matrix

| Scenario | Use Token | Use Tailwind | Reason |
|----------|-----------|--------------|--------|
| Page container | `Container.STANDARD` | ❌ | Standard widths |
| Section spacing | `Spacing.SECTION` | ❌ | Consistent gaps |
| Form field spacing | `Spacing.FORM` | ❌ | Uniform forms |
| Card styling | `Card.STANDARD` | ❌ | Consistent cards |
| Heading styles | `Typography.H2` | ❌ | Type hierarchy |
| Icon + text gap | ❌ | `gap-2` | One-off layout |
| Custom component | ❌ | `gap-3 p-5` | Unique spacing |
| Background color | ❌ | `bg-base-100` | DaisyUI semantic |
| Text color | ❌ | `text-base-content` | DaisyUI semantic |

**Rule of Thumb:**
- **Use tokens** for: Containers, page layout, sections, cards, typography
- **Use Tailwind** for: One-off spacing, custom components, colors (via DaisyUI)

---

## Color System (DaisyUI Integration)

**CRITICAL:** SKUEL uses DaisyUI semantic colors, NOT raw Tailwind colors.

### Semantic Color Usage

```python
# GOOD: Semantic colors (theme-aware)
Div(cls="bg-base-100 text-base-content")           # Page background
Div(cls="bg-base-200 text-base-content")           # Card background
Button(cls="btn btn-primary")                      # Primary action
Span(cls="text-primary")                           # Primary text
Div(cls="border border-base-300")                  # Borders

# BAD: Raw Tailwind colors (breaks in dark mode)
Div(cls="bg-white text-gray-900")                  # ❌ Hardcoded
Div(cls="bg-gray-100")                             # ❌ Not theme-aware
Button(cls="bg-blue-600 text-white")               # ❌ Bypasses DaisyUI
```

### Complete Semantic Color Palette

| Purpose | Class | Use Case |
|---------|-------|----------|
| Page background | `bg-base-100` | Main page background |
| Card background | `bg-base-200` | Cards, panels, sections |
| Deeper background | `bg-base-300` | Nested components |
| Text | `text-base-content` | All text on base colors |
| Primary action | `btn-primary`, `text-primary` | Main CTAs, key links |
| Secondary action | `btn-secondary` | Less important actions |
| Accent | `bg-accent`, `text-accent` | Highlights, badges |
| Info | `alert-info`, `badge-info` | Informational messages |
| Success | `alert-success`, `badge-success` | Success states |
| Warning | `alert-warning`, `badge-warning` | Warning states |
| Error | `alert-error`, `badge-error` | Error states |
| Borders | `border-base-300` | Standard borders |

---

## Consistency Checklist

### Before Committing Any UI Code

#### Colors (DaisyUI)
- [ ] Using semantic colors (`bg-base-100`, `text-primary`)?
- [ ] No hardcoded hex/rgb except brand/charts?
- [ ] No raw Tailwind colors (`bg-blue-600`, `text-gray-900`)?

#### Spacing (SKUEL Tokens)
- [ ] Using `Spacing.PAGE`, `Spacing.SECTION`, `Spacing.CONTENT` for standard layouts?
- [ ] Standard gaps (4, 6, 8) not random (5, 7, 9)?
- [ ] Form fields use `Spacing.FORM` (space-y-6)?

#### Container Widths (SKUEL Tokens)
- [ ] Using `Container.STANDARD` for most pages?
- [ ] Not using custom `max-w-*` values without reason?
- [ ] Container includes responsive padding (`px-6 lg:px-8`)?

#### Typography (SKUEL Tokens)
- [ ] Using `Typography.H1`, `Typography.H2`, etc. for headings?
- [ ] Body text uses `Typography.BODY` or semantic classes?
- [ ] Consistent font weights (bold for headings, normal for body)?

#### Cards (SKUEL Tokens)
- [ ] Using `Card.STANDARD`, `Card.HOVER`, or `Card.INTERACTIVE`?
- [ ] Not mixing card styles inconsistently?
- [ ] Cards have consistent padding (p-6 standard, p-4 compact)?

#### Responsive Design
- [ ] Mobile-first approach (base styles, then `md:`, `lg:`)?
- [ ] Tested on mobile, tablet, desktop?
- [ ] No horizontal scroll on small screens?

---

## Common Violations

### ❌ Inconsistent Spacing

```python
# BAD - Random spacing values
Div(
    Section(..., cls="space-y-5"),  # Why 5?
    Section(..., cls="space-y-7"),  # Why 7?
    Section(..., cls="space-y-9"),  # Why 9?
)
```

```python
# GOOD - Standard spacing tokens
from ui.tokens import Spacing

Div(
    Section(..., cls=Spacing.SECTION),  # space-y-8 (standard)
    Section(..., cls=Spacing.SECTION),
    Section(..., cls=Spacing.SECTION),
)
```

### ❌ Wrong Container Width

```python
# BAD - Custom max-width
Div(content, cls="max-w-5xl mx-auto px-4")
```

```python
# GOOD - Standard container token
from ui.tokens import Container

Div(content, cls=Container.STANDARD)  # max-w-6xl mx-auto px-6 lg:px-8
```

### ❌ Hardcoded Colors

```python
# BAD - Raw Tailwind colors
Div(
    H1("Title", cls="text-gray-900"),
    P("Content", cls="text-gray-700"),
    cls="bg-white border border-gray-200"
)
```

```python
# GOOD - Semantic DaisyUI colors
from ui.tokens import Typography

Div(
    H1("Title", cls=Typography.H1),           # Uses text-base-content
    P("Content", cls=Typography.BODY),        # Uses text-base-content
    cls="bg-base-100 border border-base-300"
)
```

### ❌ Inconsistent Card Styling

```python
# BAD - Manual card styling varies across pages
Div(content, cls="bg-white p-6 rounded shadow")         # Page 1
Div(content, cls="bg-base-100 p-4 rounded-lg shadow")   # Page 2
Div(content, cls="bg-gray-50 p-8 rounded-md")           # Page 3
```

```python
# GOOD - Consistent card token
from ui.tokens import Card

Div(content, cls=Card.STANDARD)  # All pages use same style
```

---

## Automated Checks

Use these grep commands to find violations before committing:

### Find Hardcoded Colors

```bash
# Find raw Tailwind colors in routes/components
grep -r "bg-gray-\|text-gray-\|bg-white\|text-black" adapters/inbound/ components/

# Find hardcoded blue/red/green (except charts)
grep -r "bg-blue-\|bg-red-\|bg-green-" adapters/inbound/ components/ | grep -v chart
```

### Find Custom Container Widths

```bash
# Find custom max-width values (should use Container tokens)
grep -r "max-w-[0-9xl]\+" adapters/inbound/ components/ | grep -v "Container\."
```

### Find Non-Standard Spacing

```bash
# Find unusual spacing values (1, 3, 5, 7, 9 are non-standard)
grep -r "space-y-[135579]\|gap-[135579]" adapters/inbound/ components/
```

### Find Missing Token Imports

```bash
# Find files using spacing/containers without importing tokens
grep -l "Spacing\.\|Container\.\|Card\.\|Typography\." adapters/inbound/*.py | \
  xargs grep -L "from ui.tokens import"
```

---

## Quick Reference

### Import Statement

```python
# At top of route/component file
from ui.tokens import Spacing, Container, Card, Typography
```

### Standard Page Layout

```python
from ui.tokens import Container, Spacing, Typography

def TasksPage(tasks):
    return Div(
        # Page container
        Div(
            # Page header
            H1("Tasks", cls=Typography.H1),

            # Sections
            Div(
                # Section 1
                Section(
                    H2("Active Tasks", cls=Typography.H2),
                    Div(*task_cards, cls=Spacing.CARD_GRID),
                ),

                # Section 2
                Section(
                    H2("Completed Tasks", cls=Typography.H2),
                    Div(*completed_cards, cls=Spacing.CARD_GRID),
                ),

                cls=Spacing.SECTION  # Space between sections
            ),

            cls=Container.STANDARD  # Page container
        ),
        cls=Spacing.PAGE  # Page padding
    )
```

### Standard Card Pattern

```python
from ui.tokens import Card

def TaskCard(task):
    return Div(
        H3(task.title, cls="text-lg font-semibold"),
        P(task.description, cls="text-sm text-base-content/70"),
        cls=Card.INTERACTIVE  # Includes hover, cursor-pointer
    )
```

### Standard Form Pattern

```python
from ui.tokens import Spacing, Container

def TaskForm():
    return Form(
        Div(
            # Form fields
            Label("Title"),
            Input(type="text", name="title", cls="input input-bordered"),

            Label("Description"),
            Textarea(name="description", cls="textarea textarea-bordered"),

            Button("Submit", cls="btn btn-primary"),

            cls=Spacing.FORM  # space-y-6 between fields
        ),
        cls=Container.NARROW  # Form container
    )
```

---

## Priority Fixes

If you find violations, address them in this order:

1. **CRITICAL:** Hardcoded colors → Semantic DaisyUI colors
2. **HIGH:** Custom containers → Container tokens
3. **HIGH:** Inconsistent spacing → Spacing tokens
4. **MEDIUM:** Manual cards → Card tokens
5. **MEDIUM:** Inconsistent typography → Typography tokens
6. **LOW:** One-off spacing tweaks (usually acceptable)

---

## Related Guides

- [../daisyui/SKILL.md](../daisyui/SKILL.md) - DaisyUI component reference
- [../ux-consistency-checklist.md](../ux-consistency-checklist.md) - Pre-commit UX verification
- [SKILL.md](SKILL.md) - Complete Tailwind CSS reference
- `/ui/tokens.py` - Design token source code
