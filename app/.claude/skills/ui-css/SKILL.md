---
name: ui-css
description: Expert guide for SKUEL's CSS layer — Tailwind + ui/components/ + semantic tokens. Use when styling components, choosing between CSS layers, implementing responsive layouts, working with SKUEL components (buttons, forms, cards, navbar), or when the user mentions Tailwind, CSS, styling, component library, responsive design, dark mode, MonsterUI, or FrankenUI.
allowed-tools: Read, Grep, Glob
---

# SKUEL CSS Layer: Tailwind + ui/components/

## Core Philosophy

> "Component classes that compose with Tailwind utilities — start with the most specific, fall back to utilities."

SKUEL uses a **two-layer CSS architecture**:

| Layer | Source | Decision Rule | Example |
|-------|--------|---------------|---------|
| **Component** | `ui/components/` (M1–M5 live) | Pre-built FT components | `Button(cls=ButtonT.primary)`, `Alert(variant=AlertT.error)`, `Card(CardBody(...))` |
| **Utility** | Tailwind | Custom spacing, layout, one-off adjustments | `flex gap-4 p-6 rounded-lg` |

**Decision Rule:** `ui/components/` first → Tailwind utilities for customization. `monsterui.franken` only for `ui/theme.py` (removed at M9).

```python
# ✅ ui.components component + Tailwind extension
from ui.components import Button, ButtonT
Button("Save", cls=ButtonT.primary)
Button("Save", cls=ButtonT.primary, size="sm")   # size kwarg controls geometry
Button("Save", cls=(ButtonT.primary, "w-full mt-4"))           # tuple to compose with extra classes

# ✅ SKUEL form wrappers
from ui.components import LabelInput
LabelInput("Email", name="email", type="email")

# ⚠️ Avoid raw Tailwind when a component exists
Button("Save", cls="bg-blue-600 text-white px-4 py-2 rounded")  # Use Button(cls=ButtonT.primary)
```

## FastHTML Integration

Component and Tailwind classes both work via `cls=` in FastHTML:

```python
# Single string
Div("Content", cls="flex items-center gap-4 p-6")

# Tuple: combine SKUEL token + Tailwind utilities
Button("Submit", cls=(ButtonT.primary, "w-full shadow-lg"))

# With Alpine.js directives via **kwargs
Div(
    "Content",
    cls="p-4 bg-base-100 rounded-lg",
    **{"x-show": "open", "x-transition": ""}
)
```

---

## Component & Utility Reference

For the full code reference — SKUEL components (buttons, form controls, cards, badges, alerts, loading, tables) and the Tailwind utility reference (flex/grid layout, spacing, typography, breakpoints, semantic color tokens, states, animations) — see **[reference.md](reference.md)**.

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
Spacing.PAGE        # "p-4 sm:p-6 lg:p-8"  — page-level padding
Spacing.SECTION     # "space-y-8"    — between sections
Spacing.CONTENT     # "space-y-4"    — between items

# Cards
Card.BASE           # "bg-base-100 border border-base-200 rounded-lg"
Card.INTERACTIVE    # BASE + "hover:shadow-md transition-shadow"
Card.PADDING        # "p-6"
```

---

## Theming

Theme selection is available on `/settings` (Display & Appearance section). The selected theme is saved to Neo4j preferences and localStorage. On page load, `base_page.py` reads from localStorage via `x-init` and applies the theme. Default: `light`.

---

## Custom CSS Boundary

| Pattern | Tool |
|---------|------|
| Standard spacing/layout | Tailwind utilities |
| Repeated semantic components | Component layer (`ui/components/`) |
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

## CSS Loading Architecture

MonsterUI orchestrates three CSS frameworks loaded from **local vendor files** (`static/vendor/monsterui/`):

| Framework | Classes | Loaded From |
|-----------|---------|-------------|
| **FrankenUI** | `uk-*` (uk-input, uk-btn, uk-card) + shadcn-style utilities | `franken_css.js` |
| **DaisyUI** | `.btn`, `.card`, `.input` | `daisyui.js` |
| **Tailwind** | Utilities (flex, p-4, etc.) | `tailwind.css` |

**All pages load CSS through `build_head()`** — never hand-assemble `<link>` tags. Two layout functions:
- `BasePage()` — authenticated pages (navbar + chrome)
- `AuthPage()` — unauthenticated pages (login, register — no navbar)

**Global border radius:** `radii="sm"` (2px/4px) — set in both `ui/theme.py` and `ui/layouts/base_page.py`. Keeps corners crisp and visible across all components (buttons, inputs, cards, modals).

**Input visibility:** `main.css` overrides FrankenUI default styling for `.uk-input`/`.uk-select`/`.uk-textarea` classes. This affects MonsterUI-backed form inputs (still active until M7). `Button` now comes from `ui.components` (pure Tailwind, no `.uk-btn` dependency).

`output.css` is compiled by Tailwind CLI (`./dev css-build`). Currently NOT loaded by `build_head()` (MonsterUI's `tailwind.js` browser JIT is still the runtime compiler). This flips at M9 (ADR-071): `skuel_headers()` replaces `monster_headers()`, making `output.css` the production CSS asset and removing the 407KB browser JIT. Until M9 lands, only classes present in the MonsterUI vendor files are guaranteed at runtime.

**Critical: DaisyUI tab classes are NOT in MonsterUI** — `.tabs`, `.tabs-boxed`, `.tab`, `.tab-active` come from DaisyUI's component CSS which is separate from the utility classes in `daisyui.js`. Using these causes collapsed/broken layouts. Use the Alpine `:style` pattern instead (see below).

**`border-b-3` does not exist** — MonsterUI's Tailwind only includes `border-b`, `border-b-2`, `border-b-4`, `border-b-8`. Use `border-b-2` or `border-b-[3px]` (arbitrary value) for a 3px bottom border.

## Dynamic Styling with Alpine `:style`

For Alpine-driven style changes (tabs, toggles, active states), **prefer `:style` with CSS custom properties over `:class`**. Tailwind only compiles classes scanned from content files at build time — a class used only inside an Alpine `:class` string may exist in `franken_css.js` but specificity or load order can still cause failures.

CSS custom properties are guaranteed by MonsterUI and have no compilation dependency:

```python
# ✅ Reliable — uses CSS variables, not Tailwind class names
_ACTIVE = (
    "background-color: hsl(var(--primary));"
    " color: hsl(var(--primary-foreground));"
    " border-radius: 0.375rem;"
)
_INACTIVE = "background-color: transparent; color: hsl(var(--muted-foreground)); border-radius: 0.375rem;"

Button("Tab", **{":style": f"active ? '{_ACTIVE}' : '{_INACTIVE}'"})

# Container: use style= (not cls=) for guaranteed rendering
Div(..., style="display: inline-flex; gap: 4px; padding: 4px; background-color: hsl(var(--muted)); border-radius: 0.5rem;")
```

**MonsterUI CSS custom properties for dynamic styling:**

| Property | Value (light theme) | Use |
|----------|--------------------|----|
| `hsl(var(--primary))` | Dark charcoal (240°, 5.9%, 10%) | Active tab/button background |
| `hsl(var(--primary-foreground))` | Off-white (0°, 0%, 98%) | Text on primary background |
| `hsl(var(--muted))` | Light gray | Container background, subtle fills |
| `hsl(var(--muted-foreground))` | Medium gray | Secondary/inactive text |
| `hsl(var(--background))` | White | Page background |
| `hsl(var(--border))` | Light gray border | Dividers, outlines |
| `hsl(var(--destructive))` | Red | Delete/danger states |

**`cls` gotcha (remaining `monsterui.franken` wrappers):** Never pass `cls=None` to MonsterUI components — it renders as the literal string `"None"` in the HTML class attribute. Use `cls=""` or omit `cls`. Components from `ui.components` handle this correctly via `_cls()`. Cards migrated to `ui.components` (M5) and are not affected.

## Anti-Patterns

```python
# ❌ Raw Tailwind when a component exists
Div("Error", cls="bg-red-100 text-red-800 p-3 rounded")  # Use Alert(variant=AlertT.error) from ui.components

# ❌ Tailwind palette instead of semantic tokens
P("Text", cls="text-gray-600")  # Use text-base-content/70

# ❌ Hardcoded container widths
Div(cls="max-w-6xl mx-auto")  # Use Container.STANDARD

# ❌ Inconsistent spacing
Div(cls="p-5")  # Use p-4 or p-6 (standard scale)

# ❌ Passing cls=None to MonsterUI
MCardBody(*c, cls=None)  # Renders class="uk-card-body None"
# ✅ Omit cls or pass empty string
MCardBody(*c)             # Renders class="uk-card-body "

# ❌ Raw HTML strings for pages (NotStr with <link> tags)
NotStr("<!DOCTYPE html>...")  # Use AuthPage() or BasePage()

# ❌ Custom CSS classes to replicate framework styling
.skuel-input { border: 1px solid... }  # Use LabelInput() — wrapper handles styling internally
```

## Key Files

| File | Purpose |
|------|---------|
| `/ui/tokens.py` | Design tokens (Container, Spacing, Card) |
| `/static/css/main.css` | Custom CSS: animations, HTMX states, button/input visibility overrides |
| `/static/css/output.css` | Compiled Tailwind CLI output — becomes the production asset at M9 (ADR-071) |
| `ui/components/` | **SKUEL-owned component layer (ADR-071, M1–M8 live)** — Button/ButtonT, Alert/AlertT/Loading/Progress, Icon, form set, table set, Divider, TabContainer, Accordion, layout helpers, Card/CardBody/CardHeader/CardTitle/CardFooter. |
| `ui/forms/`, `ui/feedback.py`, `ui/layout.py`, `ui/navigation.py`, `ui/data.py` | Pure Tailwind wrappers (M1–M8 ✅). `ui/buttons.py`/`ui/cards.py`/`ui/text.py` deleted (PR E). Only `ui/theme.py` remains on MonsterUI (M9 cutover). |

## See Also

- `skuel-ui` — SKUEL-specific UI patterns (pages, forms, navigation, components); also covers ADR-071 migration state
- `ui-browser` — HTMX + Alpine.js interactivity layer
- Tailwind Docs: https://tailwindcss.com/docs
