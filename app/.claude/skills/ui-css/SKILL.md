---
name: ui-css
description: Expert guide for SKUEL's CSS layer — Tailwind + ui/components/ + semantic tokens. Use when styling components, choosing between CSS layers, implementing responsive layouts, working with SKUEL components (buttons, forms, cards, navbar), or when the user mentions Tailwind, CSS, styling, component library, responsive design, dark mode, or ui.components.
allowed-tools: Read, Grep, Glob
---

# SKUEL CSS Layer: Tailwind + ui/components/

## Core Philosophy

> "Component classes that compose with Tailwind utilities — start with the most specific, fall back to utilities."

SKUEL uses a **two-layer CSS architecture**:

| Layer | Source | Decision Rule | Example |
|-------|--------|---------------|---------|
| **Component** | `ui/components/` (pure Tailwind + Alpine.js) | Pre-built FT components | `Button(cls=ButtonT.primary)`, `Alert(variant=AlertT.error)`, `Card(CardBody(...))` |
| **Utility** | Tailwind | Custom spacing, layout, one-off adjustments | `flex gap-4 p-6 rounded-lg` |

**Decision Rule:** `ui/components/` first → Tailwind utilities for customization. All UI is SKUEL-owned pure Tailwind (ADR-071 complete — MonsterUI/FrankenUI/DaisyUI removed).

```python
# ✅ ui.components component + Tailwind extension
from ui.components import Button, ButtonT
Button("Save", cls=ButtonT.primary)
Button("Save", cls=ButtonT.primary, size="sm")   # size kwarg controls geometry
Button("More filters", cls=ButtonT.ghost, size="field")  # beside fields: min-h-11 md:min-h-10
Button("Save", cls=(ButtonT.primary, "w-full mt-4"))           # tuple to compose with extra classes

# ✅ SKUEL form wrappers
from ui.components import LabelInput
LabelInput("Email", name="email", type="email")

# ✅ Fields own their size — cls is layout only; compact=True is the one size variant
Select(*options, name="model", compact=True, full_width=False)
# ❌ A raw fasthtml Input/Select (test_form_fields_use_components.py fails on it)
#    or a cls that restates height/padding/text size/border/background
# ✅ Textareas are TextArea (rows= for height); only the chat composers are raw,
#    borderless inside a box that carries COMPOSER_FOCUS_RING

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
    cls="p-4 bg-background rounded-lg",
    **{"x-show": "open", "x-transition": ""}
)
```

---

## Component & Utility Reference

For the full code reference — SKUEL components (buttons, form controls, cards, badges, alerts, loading, tables) and the Tailwind utility reference (flex/grid layout, spacing, typography, breakpoints, semantic color tokens, states, animations) — see **[reference.md](reference.md)**.

---

## SKUEL Design Tokens

Use tokens from `/ui/tokens.py` instead of hardcoded classes.

**The shell owns the gutter.** `BasePage(STANDARD)` pads its column with `Spacing.PAGE` and `SidebarPage` pads its own; a body handed to either pads none of its sides, top or bottom — a second `px-4` puts 32px of gutter before the first card at 375px. Only a `PageType.CUSTOM` body pads itself. `tests/unit/ui/test_page_gutters.py` holds every shelled body to this, with no exceptions.

```python
from ui.tokens import Container, Spacing, Card

# Containers
Container.STANDARD  # "max-w-6xl mx-auto"  — the STANDARD shell's own width
Container.NARROW    # "max-w-4xl mx-auto"  — a narrower column inside a page
Container.WIDE      # "max-w-7xl mx-auto"

# Spacing
Spacing.PAGE        # "p-4 sm:p-6 lg:p-8"  — the STANDARD shell's own padding, never a body's
Spacing.SECTION     # "space-y-8"    — between sections
Spacing.CONTENT     # "space-y-4"    — between items

# Cards
Card.BASE           # "bg-background border border-border rounded-lg"
Card.INTERACTIVE    # BASE + "hover:shadow-md transition-shadow"
Card.PADDING        # "p-6"
```

---

## Theming

Theme selection is available on `/settings` (Display & Appearance section). The selected theme is saved to Neo4j preferences and localStorage. On page load, `dark_mode_script()` (`ui/theme.py`, wired into `build_head()`) restores the stored theme before CSS paints, falling back to `prefers-color-scheme`. Default: `light`.

---

## Custom CSS Boundary

| Pattern | Tool |
|---------|------|
| Standard spacing/layout | Tailwind utilities |
| Repeated semantic components | Component layer (`ui/components/`) |
| Repeated 5+ times | `@apply` in component class |
| Complex animations/pseudo | Custom CSS |
| Design tokens | Python class-string tokens in `/ui/tokens.py`; CSS variables in `static/css/input.css` |

```css
/* ✅ @apply only for repeated patterns (5+ uses) */
@layer components {
  .entity-card {
    @apply bg-background border border-border rounded-lg p-4;
    @apply hover:shadow-md transition-shadow;
  }
}
```

---

## Best Practices

1. **Semantic HTML first** — use `<article>`, `<section>`, `<nav>`, not divs for everything
2. **Mobile-first** — apply base classes for mobile, add `md:` / `lg:` prefixes for larger screens
3. **Semantic tokens over the Tailwind palette** — `text-foreground` / `text-muted-foreground` not `text-gray-900` / `text-gray-600`
4. **Design tokens over magic numbers** — `Container.NARROW` not `max-w-4xl mx-auto` repeated; and inside `BasePage` / `SidebarPage` a body adds no padding — the shell owns the gutter
5. **`cls` parameter for extensibility** — components accept extra classes via `cls` parameter

## CSS Loading Architecture

SKUEL's CSS is compiled by the **Tailwind CLI** (`./dev css-build`) into `static/css/output.css` — the single production CSS asset (ADR-071 complete). There is no browser-JIT compiler and no MonsterUI/FrankenUI/DaisyUI vendor files.

| Source | Classes | Defined In |
|--------|---------|------------|
| **Tailwind utilities** | flex, p-4, grid, etc. | scanned + compiled to `output.css` |
| **Semantic variables** | `--primary`, `--background`, `--card`, etc. | SKUEL-owned in `static/css/input.css` (`:root` and `.dark`) |
| **Theme-aware color tokens** | `bg-background`, `text-foreground`, `text-muted-foreground`, `bg-muted`, `border-border`, `bg-primary`, `text-destructive` | `input.css` `@theme inline`, each `hsl(var(--x))`, so they switch under `.dark` |
| **Status tokens** | `text-error`, `bg-success`, `text-warning`, `text-info` | the DaisyUI names, kept so their class strings compile; theme-aware — `--status-*` on `:root` and `.dark`. There are no `base-*` tokens: a `base-100/200/300/content` utility compiles to nothing (`tests/unit/ui/test_a11y_semantics.py` refuses one) |

**All pages load CSS through `build_head()` / `skuel_headers()`** (in `ui/theme.py`) — never hand-assemble `<link>` tags. Two layout functions:
- `BasePage()` — authenticated pages (navbar + chrome)
- `AuthPage()` — unauthenticated pages (login, register — no navbar)

**Dark mode is class-based** — `@custom-variant dark (&:where(.dark, .dark *))` in `input.css` with a `.dark` class toggled on the root element (not DaisyUI `data-theme`). A Chart.js canvas is the one surface CSS cannot reach: `SKUEL.chartTheme` (`static/js/skuel.js`) reads the tokens into Chart.js's defaults and redraws on a switch (chartjs skill § Dark mode).

`output.css` is the production CSS asset, loaded by `skuel_headers()` / `build_head()`. Run `./dev css-prod` after changing component class strings so newly-used utilities are present in the committed compiled output — CI's `css_freshness` job recompiles and **fails on drift** whenever `input.css` or any scanned class-bearing tree changes (ADR-084). `./dev css-build` (unminified) is for local inspection only; the committed artifact is the `css-prod` build.

**Tabs:** there is no shared tabs component and no DaisyUI `.tabs`/`.tab-active` classes. Same-page section switching is hand-built per page (`/groups`' WAI-ARIA tab bar in `ui/groups/hub.py`, the teaching student page's Alpine renderers); a page-to-page row is the sidebar's section nav (`ui/patterns/sidebar.py`), a `<nav>` list with `aria-current`, never `role="tab"`. For dynamic active-state styling, use the Alpine `:style` pattern with semantic CSS variables (see below).

## Dynamic Styling with Alpine `:style`

For Alpine-driven style changes (tabs, toggles, active states), **prefer `:style` with CSS custom properties over `:class`**. Tailwind only compiles classes scanned from content files at build time — a class used only inside an Alpine `:class` string won't be in `output.css` unless it also appears in scanned content.

SKUEL's semantic CSS custom properties (defined in `static/css/input.css`) have no compilation dependency:

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

**SKUEL semantic CSS custom properties for dynamic styling:**

| Property | Value (light theme) | Use |
|----------|--------------------|----|
| `hsl(var(--primary))` | Blue (221.2° 83.2% 53.3%) | Active tab/button background |
| `hsl(var(--primary-foreground))` | Near-white (210° 40% 98%) | Text on primary background |
| `hsl(var(--muted))` | Light gray | Container background, subtle fills |
| `hsl(var(--muted-foreground))` | Medium gray | Secondary/inactive text |
| `hsl(var(--background))` | White | Page background |
| `hsl(var(--border))` | Light gray border | Dividers, outlines |
| `hsl(var(--destructive))` | Red | Delete/danger states |

**`cls` gotcha:** FastHTML drops an attribute whose value is `None`, so `Div(cls=None)` renders a bare `<div>` (measured). The trap is interpolation: `cls=f"p-4 {extra}"` with `extra=None` renders `class="p-4 None"`. Build the string only from present parts, or pass a tuple to a `ui.components` wrapper, which joins its parts and skips empty ones.

## Anti-Patterns

```python
# ❌ Raw Tailwind when a component exists
Div("Error", cls="bg-red-100 text-red-800 p-3 rounded")  # Use Alert(variant=AlertT.error) from ui.components

# ❌ Tailwind palette instead of semantic tokens
P("Text", cls="text-gray-600")  # Use text-muted-foreground

# ❌ Hardcoded container widths
Div(cls="max-w-4xl mx-auto")  # Use Container.NARROW

# ❌ Padding a body the shell already pads (a doubled gutter)
BasePage(Div(content, cls=f"{Container.STANDARD} {Spacing.PAGE}"), request=request)
# ✅ The shell pads; the body adds nothing
BasePage(Div(content), request=request)

# ❌ Inconsistent spacing
Div(cls="p-5")  # Use p-4 or p-6 (standard scale)

# ❌ New arbitrary font sizes
Span("Meta", cls="text-[11px]")  # Use the named scale: text-10/11/13/15 (SKUEL
# compact steps, ADR-084) or stock text-xs/sm/base/lg/xl — audit_font_sizes.py
# --strict (CI + ./dev quality) fails on arbitrary sizes outside the exception ledger

# ❌ Interpolating an optional class into an f-string
Div(*c, cls=f"p-4 {extra}")  # extra=None renders class="p-4 None"
# ✅ Pass only present parts
Div(*c, cls=" ".join(p for p in ("p-4", extra) if p))

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
| `/static/css/input.css` | Tailwind v4 CSS-first config (the whole config — `@source` scanning + inline safelist, `@custom-variant dark`, `@theme inline` color tokens + compact font-size tokens `--text-10/11/13/15`, ADR-084) + SKUEL-owned semantic CSS variables (`--primary`, `--background`, `--card`, …) |
| `/static/css/output.css` | Compiled Tailwind CLI output — **the production CSS asset** (ADR-071) |
| `ui/components/` | **SKUEL-owned component layer (ADR-071 complete)** — pure Tailwind + Alpine.js. Button/ButtonT, Alert/AlertT/Loading/Progress, Icon, form set, table set, Divider, Accordion, layout helpers, Card/CardBody/CardHeader/CardTitle/CardFooter. |
| `ui/forms/`, `ui/feedback.py`, `ui/layout.py`, `ui/data.py`, `ui/theme.py` | Pure Tailwind wrappers (ADR-071 complete). The former `buttons.py`/`cards.py`/`text.py` wrappers were deleted (PR E); the former `navigation.py` was deleted 2026-08 (zero consumers). |

## See Also

- `skuel-ui` — SKUEL-specific UI patterns (pages, forms, navigation, components); also covers ADR-071 migration state
- `ui-browser` — HTMX + Alpine.js interactivity layer
- Tailwind Docs: https://tailwindcss.com/docs
