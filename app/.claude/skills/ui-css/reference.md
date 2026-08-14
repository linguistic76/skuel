# ui-css Reference: SKUEL Components + Tailwind Utilities

> On-demand reference for the [`ui-css`](SKILL.md) skill. SKILL.md holds the philosophy, design tokens, theming, CSS-loading architecture, and patterns; this file holds the component-by-component and utility-class detail.

## SKUEL Component Reference

All UI components use Python FT functions. Import everything from `ui.components` — SKUEL's owned pure-Tailwind + Alpine.js component layer (ADR-071 complete). MonsterUI/FrankenUI/DaisyUI are removed.

### Buttons

```python
from ui.components import Button, ButtonT
from ui.primitives import ButtonLink

# Style variants (cls=) — controls colour/border/hover
Button("Primary", cls=ButtonT.primary)
Button("Secondary", cls=ButtonT.secondary)
Button("Ghost", cls=ButtonT.ghost)
Button("Destructive", cls=ButtonT.destructive)
Button("Link", cls=ButtonT.link)

# Geometry (size=) — controls height/padding. Never mix size tokens in cls= tuple.
Button("Small", cls=ButtonT.primary, size="sm")    # xs, sm, md (default), lg, xl
Button("Large", cls=ButtonT.primary, size="lg")

# Composing extra Tailwind classes with style variant
Button("Full-width", cls=(ButtonT.primary, "w-full mt-4"))

# ButtonLink — for ALL action CTAs (not raw A() with ad-hoc Tailwind)
# primary CTA → ButtonT.primary, size="sm" | view/navigate → ButtonT.ghost, size="sm" | "view all" → ButtonT.ghost, size="xs"
ButtonLink("Submit →", href="/submit", cls=ButtonT.primary, size="sm")
ButtonLink("View Details", href="/tasks/123", cls=ButtonT.ghost, size="sm")
ButtonLink("View all →", href="/tasks", cls=ButtonT.ghost, size="xs")
```

### Form Controls

```python
from ui.forms import LabelInput, LabelTextArea, LabelSelect, LabelCheckbox, Toggle, Radio

# Text input (label + input in one component)
LabelInput("Title", name="title", placeholder="Enter text")

# Email input (required)
LabelInput("Email *", name="email", type="email", required=True)

# Select
LabelSelect("Choice", Option("Pick one", disabled=True, selected=True), Option("Option 1", value="1"), name="choice")

# Textarea
LabelTextArea("Description", name="description", rows=4)

# Checkbox
LabelCheckbox("I agree", name="agree")

# Toggle
Toggle(name="enabled")

# Radio
Radio(name="priority", value="high")
```

### LabelInput Pattern (SKUEL Standard)

Use `LabelInput` (and siblings) for accessible label+input pairs:

```python
from ui.forms import LabelInput

LabelInput("Email *", name="email", type="email", required=True)
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
# Alpine.js modals — use plain Div with Tailwind + x-show (no ui.modals)
from ui.components import Button, ButtonT

Div(
    Div(
        H3("Modal Title", cls="font-bold text-lg"),
        P("Modal content here", cls="py-4"),
        Div(
            Button("Cancel", cls=ButtonT.ghost, **{"@click": "showModal = false"}),
            Button("Confirm", cls=ButtonT.primary),
            cls="flex justify-end gap-2",
        ),
        cls="bg-background rounded-lg shadow-lg max-w-lg w-full p-6 relative",
        **{"@click.stop": ""},
    ),
    cls="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4",
    **{"@click": "showModal = false"},
    x_show="showModal",
    x_cloak=True,
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
from ui.feedback import Loading
from ui.layout import Size

Loading(size=Size.sm)
Loading(size=Size.md)
Loading()  # md default
```

### Tables & Dividers

```python
from ui.data import Table, TableFromDicts, TableFromLists, TableT, Divider, DividerSplit, DividerT

# Preferred: TableFromDicts for data-driven tables
TableFromDicts(
    header_data=["Name", "Score"],
    body_data=[{"Name": "Alice", "Score": 90}, {"Name": "Bob", "Score": 85}],
    body_cell_render=lambda k, v: Td(v, cls="font-bold" if k == "Name" else ""),
    cls=(TableT.striped, TableT.sm),
)
TableFromLists(header=["Name", "Score"], body=[["Alice", 90], ["Bob", 85]])

# Divider
Divider()  # renders border-t border-border my-4
DividerSplit("or")  # divider with centered text
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
<h1 class="text-2xl font-bold text-foreground">Page Title</h1>
<h2 class="text-xl font-semibold">Section</h2>
<h3 class="text-lg font-medium">Subsection</h3>
<p class="text-base text-muted-foreground">Body text</p>
<p class="text-sm text-muted-foreground">Secondary text</p>
<p class="text-11 uppercase tracking-wide font-semibold">Label</p>
```

The full scale — Tailwind's stock steps plus SKUEL's compact steps
(`text-10`/`text-11`/`text-13`/`text-15`, ADR-084, minted in `input.css`
`@theme inline`). Compact steps emit **font-size only** (line-height is
inherited — deliberately no `--text-N--line-height` companions):

| Class | Size | Use |
|-------|------|-----|
| `text-10` | 10px | Micro labels, badges, mono kickers (SKUEL compact) |
| `text-11` | 11px | Metadata, uppercase section labels (SKUEL compact) |
| `text-xs` | 12px | Labels, metadata |
| `text-13` | 13px | Dense body/list text — house workhorse (SKUEL compact) |
| `text-sm` | 14px | Secondary, captions |
| `text-15` | 15px | Emphasized body, list titles (SKUEL compact) |
| `text-base` | 16px | Body text |
| `text-lg` | 18px | Lead text |
| `text-xl` | 20px | Card titles |
| `text-2xl` | 24px | Page headings |

**Never write a new arbitrary font size** (`text-[13px]`, `sm:text-[40px]`) —
the scale above covers every sanctioned step, and `scripts/audit_font_sizes.py`
flags arbitrary sizes outside the ADR-084 exception ledger. Migrating legacy
sites (campaign mapping): 9–10.5px → `text-10` · 11/11.5 → `text-11` ·
12/12.5 → `text-xs` · 13/13.5 → `text-13` · 14/14.5 → `text-sm` ·
15/15.5 → `text-15` · 16 → `text-base` · 17/18 → `text-lg` · 20/22 →
`text-xl` · ~30 → `text-3xl` · clamp()/40px+ heroes → allowlisted exceptions.

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
