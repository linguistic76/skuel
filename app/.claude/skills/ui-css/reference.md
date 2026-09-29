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
ButtonLink("Submit →", href="/submissions/submit", cls=ButtonT.primary, size="sm")
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

# Select — options are positional, label is keyword-only
LabelSelect(Option("Pick one", disabled=True, selected=True), Option("Option 1", value="1"), label="Choice", name="choice")

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
Div(content, cls=Card.BASE)  # "bg-background border border-border rounded-lg"

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
# AlpineModal — backdrop, click-outside-to-close, x-cloak and transitions in one place
from ui.components import Button, ButtonT
from ui.patterns.modal import AlpineModal

AlpineModal(
    H3("Modal Title", cls="font-bold text-lg"),
    P("Modal content here", cls="py-4"),
    Div(
        Button("Cancel", cls=ButtonT.ghost, **{"@click": "showModal = false"}),
        Button("Confirm", cls=ButtonT.primary),
        cls="flex justify-end gap-2",
    ),
    show="showModal",
    close="showModal = false",
    max_width="max-w-lg",
)
```

The `showModal` flag lives in an enclosing `x-data`. Don't hand-roll the backdrop `Div`.

### Navbar

There is one navbar, and pages don't build their own. The global chrome is
`ui/layouts/navbar.py` (spec: `ui/layouts/nav_config.py`), rendered by `BasePage`. A
section's pages are its `SidebarPage` rows. See the `skuel-ui` skill for the chrome's rules.

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
from fasthtml.common import FT, Td

from ui.data import Table, TableFromDicts, TableFromLists, TableT, Divider, DividerSplit, DividerT

# Preferred: TableFromDicts for data-driven tables
def _cell(key: str, value: object) -> FT:
    return Td(value, cls="font-bold" if key == "Name" else "")


TableFromDicts(
    header_data=["Name", "Score"],
    body_data=[{"Name": "Alice", "Score": 90}, {"Name": "Bob", "Score": 85}],
    body_cell_render=_cell,
    cls=(TableT.striped, TableT.sm),
)
TableFromLists(["Name", "Score"], [["Alice", 90], ["Bob", 85]])  # header_row, data_rows

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
the scale above covers every sanctioned step, and `scripts/audit_font_sizes.py
--strict` (CI lint job + `./dev quality`) fails on any arbitrary size outside
the ADR-084 exception ledger (a handful of pinned clamp()/hero sites).

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

Theme-aware tokens: each is `hsl(var(--x))` in `input.css` `@theme inline`, and switches under `.dark`:

| Token | Use |
|-------|-----|
| `bg-background` | Page / card surface |
| `text-foreground` | Primary text |
| `text-muted-foreground` | Secondary and muted text (the house workhorse) |
| `bg-muted` | Subtle fills, inactive surfaces |
| `border-border` | Borders, dividers |
| `bg-primary` / `text-primary` / `text-primary-foreground` | Brand color and text on it |
| `bg-destructive` / `text-destructive` | Danger / delete |
| `bg-accent` / `bg-secondary` | Hover and secondary surfaces |

Fixed compat tokens: concrete hex, kept so pre-ADR-071 class strings compile. They do **not** change in dark mode:

| Token | Value |
|-------|-------|
| `text-error` / `bg-error` | `#dc2626` |
| `text-success` / `bg-success` | `#16a34a` |
| `text-warning` / `bg-warning` | `#d97706` |
| `text-info` / `bg-info` | `#2563eb` |
| `bg-base-200` / `bg-base-300` | `#f3f4f6` / `#e5e7eb` |
| `text-base-content` | `#1f2937` |

There is no `base-100` token, so `bg-base-100` compiles to nothing.

**Key rule:** prefer the theme-aware tokens (`bg-background`, `text-muted-foreground`) over the Tailwind palette (`bg-white`, `bg-blue-600`). Reach for a status color (`text-error`, `bg-success/10`) only for status, and know that it stays the same in dark mode.

### States & Interactions

```html
<button class="hover:shadow-lg active:scale-95 transition">Button</button>
<div class="group hover:bg-muted">
  <span class="group-hover:text-primary">Changes on parent hover</span>
</div>
<input class="focus-visible:ring-2 focus-visible:ring-ring transition">
<button class="disabled:opacity-50 disabled:cursor-not-allowed" disabled>
```

### Animations

```html
<div class="transition duration-200 ease-in-out hover:scale-105">
<div class="transition-colors duration-300 hover:bg-muted">
<div class="animate-pulse">Loading...</div>
<div class="animate-spin">Spinner</div>
```
