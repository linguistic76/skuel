---
name: ui-css
description: Expert guide for SKUEL's CSS layer — DaisyUI semantic components + Tailwind utility classes. Use when styling components, choosing between CSS layers, implementing responsive layouts, working with DaisyUI components (buttons, forms, modals, cards, navbar), or when the user mentions DaisyUI, Tailwind, CSS, styling, component library, responsive design, or dark mode.
allowed-tools: Read, Grep, Glob
---

# SKUEL CSS Layer: DaisyUI + Tailwind

## Core Philosophy

> "Semantic component classes that compose with Tailwind utilities — start with the most specific, fall back to utilities."

SKUEL uses a **three-layer CSS architecture**:

| Layer | Library | Decision Rule | Example |
|-------|---------|---------------|---------|
| **Component** | MonsterUI | Pre-built FastHTML components | `ButtonT.primary`, `Card`, `Grid` |
| **Semantic** | DaisyUI 5 | Themed UI patterns, no component exists in MonsterUI | `btn btn-primary`, `modal`, `tabs` |
| **Utility** | Tailwind | Custom spacing, layout, one-off adjustments | `flex gap-4 p-6 rounded-lg` |

**Decision Rule:** MonsterUI first → DaisyUI second → Tailwind utilities for customization

```python
# ✅ MonsterUI component + Tailwind customization
Button("Save", cls=(ButtonT.primary, "w-full mt-4"))

# ✅ DaisyUI when MonsterUI doesn't have it
Div(Input(type="checkbox", cls="toggle toggle-primary"))

# ⚠️ Avoid raw Tailwind when MonsterUI has a component
Button("Save", cls="bg-blue-600 text-white px-4 py-2 rounded")  # Use ButtonT.primary
```

## FastHTML Integration

Tailwind and DaisyUI classes work via `cls=` in FastHTML:

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

## DaisyUI 5 Component Reference

### Buttons

```html
<!-- Variants -->
<button class="btn btn-primary">Primary</button>
<button class="btn btn-secondary">Secondary</button>
<button class="btn btn-accent">Accent</button>
<button class="btn btn-ghost">Ghost</button>
<button class="btn btn-outline">Outline</button>
<button class="btn btn-error">Danger</button>
<button class="btn btn-success">Success</button>

<!-- Sizes -->
<button class="btn btn-xs">XSmall</button>
<button class="btn btn-sm">Small</button>
<button class="btn btn-md">Medium (default)</button>
<button class="btn btn-lg">Large</button>

<!-- States -->
<button class="btn btn-primary loading">Loading</button>
<button class="btn" disabled>Disabled</button>

<!-- Shape -->
<button class="btn btn-circle">◉</button>
<button class="btn btn-square">■</button>
```

### Form Controls

```html
<!-- Text input -->
<input type="text" class="input input-bordered w-full" placeholder="Enter text">
<input type="text" class="input input-bordered input-error w-full">

<!-- Select -->
<select class="select select-bordered w-full">
  <option disabled selected>Pick one</option>
  <option>Option 1</option>
</select>

<!-- Textarea -->
<textarea class="textarea textarea-bordered w-full" rows="4"></textarea>

<!-- Checkbox -->
<input type="checkbox" class="checkbox checkbox-primary">

<!-- Toggle -->
<input type="checkbox" class="toggle toggle-primary">

<!-- Radio -->
<input type="radio" name="x" class="radio radio-primary">

<!-- Range -->
<input type="range" min="0" max="100" class="range range-primary">

<!-- File input -->
<input type="file" class="file-input file-input-bordered w-full">
```

### FormControl Pattern (SKUEL Standard)

Always wrap inputs in `form-control` + `label` for accessibility:

```html
<div class="form-control w-full">
  <label class="label">
    <span class="label-text">Email *</span>
    <span class="label-text-alt">Required</span>
  </label>
  <input type="email" name="email" required class="input input-bordered w-full">
  <label class="label">
    <span class="label-text-alt text-error">Error message here</span>
  </label>
</div>
```

```python
# FastHTML equivalent
FormControl(
    Label(LabelText("Email *")),
    Input(type="email", name="email", required=True, cls="input input-bordered w-full"),
)
```

### Cards

```html
<!-- Basic card -->
<div class="card bg-base-100 shadow-md">
  <div class="card-body">
    <h2 class="card-title">Card Title</h2>
    <p>Card description</p>
    <div class="card-actions justify-end">
      <button class="btn btn-primary">Action</button>
    </div>
  </div>
</div>

<!-- Interactive card -->
<div class="card bg-base-100 border border-base-200 hover:shadow-lg transition-shadow cursor-pointer">
  <div class="card-body p-4">
    <h3 class="font-semibold">Title</h3>
    <p class="text-sm text-base-content/70">Description</p>
  </div>
</div>
```

### Badges

```html
<span class="badge">Default</span>
<span class="badge badge-primary">Primary</span>
<span class="badge badge-secondary">Secondary</span>
<span class="badge badge-success">Success</span>
<span class="badge badge-warning">Warning</span>
<span class="badge badge-error">Error</span>
<span class="badge badge-ghost">Ghost</span>

<!-- Sizes -->
<span class="badge badge-xs">XS</span>
<span class="badge badge-sm">SM</span>
<span class="badge badge-lg">LG</span>

<!-- Outline -->
<span class="badge badge-outline badge-primary">Outline</span>
```

### Alerts

```html
<div class="alert alert-info">Info message</div>
<div class="alert alert-success">Success message</div>
<div class="alert alert-warning">Warning message</div>
<div class="alert alert-error">Error message</div>

<!-- With icon -->
<div class="alert alert-error">
  <span>⚠️</span>
  <span>Something went wrong</span>
</div>
```

### Modals

```html
<!-- Modal trigger -->
<button onclick="my_modal.showModal()" class="btn btn-primary">Open Modal</button>

<!-- Native dialog modal (DaisyUI 5) -->
<dialog id="my_modal" class="modal">
  <div class="modal-box">
    <h3 class="font-bold text-lg">Modal Title</h3>
    <p class="py-4">Modal content here</p>
    <div class="modal-action">
      <form method="dialog">
        <button class="btn btn-ghost">Cancel</button>
        <button class="btn btn-primary">Confirm</button>
      </form>
    </div>
  </div>
  <!-- Backdrop click closes modal -->
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
```

### Navbar

```html
<div class="navbar bg-white border-b border-gray-200 sticky top-0 z-50">
  <div class="navbar-start">
    <a href="/" class="text-xl font-bold">Brand</a>
  </div>
  <div class="navbar-center hidden sm:flex">
    <ul class="menu menu-horizontal gap-1">
      <li><a href="/tasks" class="btn btn-ghost btn-sm">Tasks</a></li>
      <li><a href="/goals" class="btn btn-ghost btn-sm">Goals</a></li>
    </ul>
  </div>
  <div class="navbar-end">
    <button class="btn btn-ghost btn-circle">👤</button>
  </div>
</div>
```

### Tabs

```html
<!-- Bordered tabs (used in mobile sidebars) -->
<div class="tabs tabs-bordered">
  <a class="tab tab-active">Active</a>
  <a class="tab">Tab 2</a>
  <a class="tab">Tab 3</a>
</div>

<!-- Boxed tabs -->
<div class="tabs tabs-boxed">
  <a class="tab tab-active">Active</a>
  <a class="tab">Tab 2</a>
</div>
```

### Menu (Sidebar Nav)

```html
<ul class="menu bg-base-100 rounded-box w-56">
  <li class="menu-title">Section Title</li>
  <li><a class="active">Active item</a></li>
  <li><a>Item 2</a></li>
  <li>
    <details>
      <summary>Submenu</summary>
      <ul>
        <li><a>Sub item 1</a></li>
      </ul>
    </details>
  </li>
</ul>
```

### Loading

```html
<span class="loading loading-spinner loading-sm"></span>
<span class="loading loading-spinner loading-md"></span>
<span class="loading loading-dots"></span>
<span class="loading loading-ring"></span>
```

### Toast / Notifications

```html
<div class="toast toast-end">
  <div class="alert alert-success">
    <span>Task created!</span>
  </div>
</div>
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

### DaisyUI Color Tokens (use these instead of Tailwind palette)

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

**Key rule:** Always use DaisyUI semantic tokens (`bg-base-100`, `text-primary`) not Tailwind palette (`bg-white`, `bg-blue-600`). Semantic tokens respect the active DaisyUI theme automatically.

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

## Theming (DaisyUI 5)

DaisyUI 5 themes configured in CSS:

```css
@import "tailwindcss";
@plugin "daisyui" {
  themes: light --default, dark --prefersdark;
}
```

**SKUEL uses light theme only** — all surfaces are `bg-white`, sections separated by borders not color contrast:
- Navbar: `bg-white border-b border-gray-200`
- HUB sidebar: `bg-white border-r border-gray-200`
- Content areas: `bg-white`

---

## Custom CSS Boundary

| Pattern | Tool |
|---------|------|
| Standard spacing/layout | Tailwind utilities |
| Repeated semantic components | DaisyUI classes |
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
3. **DaisyUI tokens over Tailwind palette** — `text-base-content` not `text-gray-900`
4. **Design tokens over magic numbers** — `Container.STANDARD` not `max-w-6xl mx-auto` repeated
5. **`cls` parameter for extensibility** — components accept extra classes via `cls` parameter

## Anti-Patterns

```python
# ❌ Raw Tailwind when DaisyUI has it
Div("Error", cls="bg-red-100 text-red-800 p-3 rounded")  # Use alert alert-error

# ❌ Tailwind palette instead of DaisyUI tokens
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
| `ui/buttons.py`, `ui/cards.py`, `ui/forms.py`, `ui/modals.py`, `ui/feedback.py`, `ui/layout.py`, `ui/navigation.py`, `ui/data.py` | FastHTML DaisyUI component wrappers (8 focused modules, March 2026) |

## See Also

- `skuel-ui` — SKUEL-specific UI patterns (pages, forms, navigation, components)
- `ui-browser` — HTMX + Alpine.js interactivity layer
- Tailwind Docs: https://tailwindcss.com/docs
- DaisyUI Docs: https://daisyui.com/components/
