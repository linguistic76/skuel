---
name: tailwind-css
description: Expert guide for utility-first CSS with Tailwind. Use when styling HTML/components, creating responsive layouts, implementing dark mode, writing utility classes, or when the user mentions Tailwind, responsive design, flexbox/grid layouts, or utility-first CSS.
allowed-tools: Read, Grep, Glob
---

# Tailwind CSS for Semantic HTML

## Core Philosophy

> "Utility-first: compose small, single-purpose classes rather than writing custom CSS"

Tailwind CSS applies styles directly via HTML classes. This eliminates context-switching between HTML and CSS files, keeps styles co-located with markup, and enables rapid iteration.

## SKUEL's CSS Architecture

SKUEL uses a **layered approach** with three CSS technologies:

| Layer | Library | Use When | Example |
|-------|---------|----------|---------|
| **Component** | MonsterUI | Pre-built semantic components | `ButtonT.primary`, `Card`, `Grid` |
| **Semantic** | DaisyUI | Themed UI patterns | `btn btn-primary`, `modal`, `drawer` |
| **Utility** | Tailwind | Custom spacing, layout, one-off styling | `flex gap-4 p-6 rounded-lg` |

**Decision Rule:** Start with MonsterUI → Fall back to DaisyUI → Use Tailwind for customization

```python
# ✅ GOOD: MonsterUI component + Tailwind customization
Button("Save", cls=(ButtonT.primary, "w-full mt-4"))

# ✅ GOOD: DaisyUI when MonsterUI doesn't have it
Div(Input(type="checkbox", cls="toggle toggle-primary"))

# ⚠️ AVOID: Raw Tailwind when MonsterUI has component
Button("Save", cls="bg-blue-600 text-white px-4 py-2 rounded")  # Use ButtonT.primary
```

**See:** [decision-guide.md](decision-guide.md) for complete decision flowchart.

## FastHTML Integration

Tailwind classes work in FastHTML via `cls=` parameter:

```python
from fasthtml.common import *
from monsterui.all import *

# Single class string
Div("Content", cls="flex items-center gap-4 p-6")

# Tuple for combining (MonsterUI + Tailwind)
Button("Submit", cls=(ButtonT.primary, "w-full shadow-lg"))

# With Alpine.js directives via **kwargs
Div(
    "Toggle content",
    cls="p-4 bg-base-100 rounded-lg",
    **{"x-data": "{ open: false }", "x-show": "open"}
)
```

**Responsive in FastHTML:**
```python
# Mobile-first responsive grid
Grid(
    *cards,
    cls="grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
)

# Responsive visibility
Div("Desktop only", cls="hidden lg:block")
```

**See:** [fasthtml-integration.md](fasthtml-integration.md) for complete patterns.

## Quick Start

```html
<!-- A responsive card component -->
<article class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow">
  <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-2">Card Title</h2>
  <p class="text-gray-600 dark:text-gray-300">Card description goes here.</p>
</article>
```

## Layout Patterns

### Flexbox (1D Layout)

```html
<!-- Centered content -->
<div class="flex items-center justify-center min-h-screen">
  <div>Centered</div>
</div>

<!-- Space between items -->
<nav class="flex items-center justify-between p-4">
  <div class="logo">Brand</div>
  <ul class="flex gap-4">
    <li><a href="#">Link</a></li>
    <li><a href="#">Link</a></li>
  </ul>
</nav>

<!-- Responsive row → column -->
<div class="flex flex-col md:flex-row gap-4">
  <aside class="w-full md:w-64">Sidebar</aside>
  <main class="flex-1">Content</main>
</div>
```

### CSS Grid (2D Layout)

```html
<!-- Auto-responsive grid -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
  <div class="bg-white p-4 rounded shadow">Item 1</div>
  <div class="bg-white p-4 rounded shadow">Item 2</div>
  <div class="bg-white p-4 rounded shadow">Item 3</div>
  <div class="bg-white p-4 rounded shadow">Item 4</div>
</div>

<!-- Dashboard layout -->
<div class="grid grid-cols-12 gap-4">
  <aside class="col-span-12 lg:col-span-3">Sidebar</aside>
  <main class="col-span-12 lg:col-span-9">Content</main>
</div>
```

## Spacing System

Tailwind uses a consistent spacing scale (1 unit = 4px):

| Class | Value | Example Use |
|-------|-------|-------------|
| `p-1` | 4px | Tight padding |
| `p-2` | 8px | Small padding |
| `p-4` | 16px | Standard padding |
| `p-6` | 24px | Comfortable padding |
| `p-8` | 32px | Large sections |
| `gap-4` | 16px | Grid/flex gaps |
| `space-y-4` | 16px | Stack spacing |

**Directional variants:** `px-*` (horizontal), `py-*` (vertical), `pt-*` (top), `pr-*` (right), `pb-*` (bottom), `pl-*` (left)

## Typography

```html
<!-- Heading hierarchy -->
<h1 class="text-4xl font-bold tracking-tight">Page Title</h1>
<h2 class="text-2xl font-semibold">Section Heading</h2>
<h3 class="text-xl font-medium">Subsection</h3>
<p class="text-base text-gray-700 leading-relaxed">Body text with comfortable line height.</p>

<!-- Text utilities -->
<p class="text-sm text-gray-500">Small muted text</p>
<p class="text-lg font-medium text-blue-600">Emphasized text</p>
<p class="uppercase tracking-wide text-xs font-semibold text-gray-400">Label</p>
```

| Size Class | px | Use |
|------------|-----|-----|
| `text-xs` | 12px | Labels, metadata |
| `text-sm` | 14px | Secondary text |
| `text-base` | 16px | Body text (default) |
| `text-lg` | 18px | Slightly larger body |
| `text-xl` | 20px | Small headings |
| `text-2xl` | 24px | Medium headings |
| `text-4xl` | 36px | Page titles |

## Responsive Design

Tailwind is mobile-first. Apply base styles, then add breakpoint prefixes for larger screens:

| Breakpoint | Min Width | Example |
|------------|-----------|---------|
| (none) | 0px | `flex` (mobile default) |
| `sm:` | 640px | `sm:flex` |
| `md:` | 768px | `md:grid-cols-2` |
| `lg:` | 1024px | `lg:text-xl` |
| `xl:` | 1280px | `xl:max-w-6xl` |
| `2xl:` | 1536px | `2xl:px-0` |

```html
<!-- Mobile: stack, Tablet: 2-col, Desktop: 3-col -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  <!-- items -->
</div>

<!-- Hide on mobile, show on desktop -->
<div class="hidden lg:block">Desktop only</div>
<div class="lg:hidden">Mobile only</div>
```

## Dark Mode

Use the `dark:` prefix for dark mode variants:

```html
<div class="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
  <h1 class="text-gray-800 dark:text-white">Heading</h1>
  <p class="text-gray-600 dark:text-gray-400">Body text</p>
  <button class="bg-blue-600 dark:bg-blue-500 text-white hover:bg-blue-700 dark:hover:bg-blue-400">
    Button
  </button>
</div>
```

**Configuration** (tailwind.config.js):
```javascript
module.exports = {
  darkMode: 'class', // or 'media' for system preference
}
```

## Colors

Use semantic color names from Tailwind's palette:

| Semantic Use | Light Mode | Dark Mode |
|--------------|------------|-----------|
| Background | `bg-white` | `dark:bg-gray-900` |
| Surface | `bg-gray-50` | `dark:bg-gray-800` |
| Primary text | `text-gray-900` | `dark:text-white` |
| Secondary text | `text-gray-600` | `dark:text-gray-400` |
| Primary action | `bg-blue-600` | `dark:bg-blue-500` |
| Success | `text-green-600` | `dark:text-green-400` |
| Warning | `text-amber-600` | `dark:text-amber-400` |
| Error | `text-red-600` | `dark:text-red-400` |

## Common Components

### Buttons

```html
<!-- Primary -->
<button class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition">
  Primary Button
</button>

<!-- Secondary -->
<button class="bg-gray-200 text-gray-800 px-4 py-2 rounded-lg hover:bg-gray-300 transition">
  Secondary
</button>

<!-- Outline -->
<button class="border-2 border-blue-600 text-blue-600 px-4 py-2 rounded-lg hover:bg-blue-50 transition">
  Outline
</button>

<!-- Ghost -->
<button class="text-blue-600 px-4 py-2 rounded-lg hover:bg-blue-50 transition">
  Ghost
</button>
```

### Form Inputs

```html
<!-- Text input -->
<input type="text"
  class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none transition"
  placeholder="Enter text">

<!-- With label -->
<label class="block">
  <span class="text-sm font-medium text-gray-700">Email</span>
  <input type="email"
    class="mt-1 w-full px-4 py-2 border border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none">
</label>

<!-- Textarea -->
<textarea
  class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none resize-none"
  rows="4"></textarea>
```

### Cards

```html
<!-- Basic card -->
<div class="bg-white rounded-lg shadow p-6">
  <h3 class="text-lg font-semibold mb-2">Card Title</h3>
  <p class="text-gray-600">Description</p>
</div>

<!-- Interactive card -->
<article class="bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow cursor-pointer">
  <img src="image.jpg" alt="" class="w-full h-48 object-cover">
  <div class="p-4">
    <h3 class="font-bold">Title</h3>
    <p class="text-gray-600 text-sm mt-1">Description</p>
  </div>
</article>
```

## States & Interactions

```html
<!-- Hover -->
<button class="bg-blue-600 hover:bg-blue-700">Hover me</button>

<!-- Focus -->
<input class="focus:border-blue-500 focus:ring-2 focus:ring-blue-200">

<!-- Active -->
<button class="active:scale-95">Click me</button>

<!-- Disabled -->
<button class="disabled:opacity-50 disabled:cursor-not-allowed" disabled>Disabled</button>

<!-- Group hover (child reacts to parent hover) -->
<div class="group p-4 hover:bg-gray-50">
  <span class="group-hover:text-blue-600">Changes on parent hover</span>
</div>
```

## Animations & Transitions

```html
<!-- Smooth transitions -->
<div class="transition duration-200 ease-in-out hover:scale-105">
  Scales on hover
</div>

<!-- Specific properties -->
<div class="transition-colors duration-300 hover:bg-blue-500">
  Color transition
</div>

<!-- Built-in animations -->
<div class="animate-pulse">Loading...</div>
<div class="animate-spin">Spinner</div>
<div class="animate-bounce">Bouncing</div>
```

## Best Practices

### 1. Semantic HTML First
```html
<!-- GOOD: Semantic elements with utility classes -->
<article class="p-6">
  <header class="mb-4">
    <h1 class="text-2xl font-bold">Title</h1>
  </header>
  <section class="prose">Content</section>
</article>

<!-- AVOID: Divs for everything -->
<div class="p-6">
  <div class="mb-4">
    <div class="text-2xl font-bold">Title</div>
  </div>
</div>
```

### 2. Mobile-First
```html
<!-- GOOD: Start with mobile, add breakpoints -->
<div class="text-sm md:text-base lg:text-lg">Responsive text</div>

<!-- AVOID: Desktop-first with mobile overrides -->
<div class="text-lg sm:text-base xs:text-sm">Harder to maintain</div>
```

### 3. Consistent Spacing
Use Tailwind's scale (p-2, p-4, p-6, p-8) rather than arbitrary values.

### 4. Extract Components, Not CSS
When patterns repeat, create HTML components (React/Vue components, partials) rather than extracting to CSS with `@apply`.

---

## Custom CSS Boundary

**Principle:** "Tailwind utilities in templates, @apply in stylesheets, custom CSS for complex patterns"

### When to Use What

| Pattern | Tool | Example |
|---------|------|---------|
| Standard spacing/layout | Tailwind utilities | `flex gap-4 p-6` |
| Repeated components | DaisyUI components | `btn btn-primary` |
| Complex hover states | Custom CSS | `.card:hover .overlay { opacity: 1; }` |
| Animations | Custom CSS | `@keyframes slideIn` |
| Design tokens | CSS variables | `var(--space-page)` |

### Pattern: Component Classes with @apply

**Use for:** Repeated patterns needing semantic names (5+ uses)

```css
@layer components {
  .task-card {
    @apply bg-base-100 border border-base-200 rounded-lg p-6;
    @apply hover:shadow-md transition-shadow;
  }
}
```

### Pattern: Custom CSS for Complex Patterns

**Use for:** Animations, complex pseudo-states, sibling selectors

```css
.card-flip {
  perspective: 1000px;
}

.card-flip:hover .card-inner {
  transform: rotateY(180deg);
}
```

### Decision Tree

```
Need styling?
  ├─ Standard spacing/layout? → Tailwind utilities
  ├─ Semantic component? → DaisyUI component
  ├─ Used 5+ times? → @apply component class
  ├─ Complex animation/pseudo? → Custom CSS
  └─ Design token? → CSS variable
```

---

## Additional Resources

**SKUEL-Specific:**
- [fasthtml-integration.md](fasthtml-integration.md) - FastHTML + Tailwind patterns
- [decision-guide.md](decision-guide.md) - When to use Tailwind vs MonsterUI vs DaisyUI

**Reference:**
- [utilities-reference.md](utilities-reference.md) - Complete utility class catalog (including modern features)
- [patterns.md](patterns.md) - Common UI patterns with FastHTML examples
- [design-consistency-guide.md](design-consistency-guide.md) - SKUEL design tokens and consistency

## UX Consistency

**CRITICAL:** Before writing Tailwind utilities, review:
- [ux-consistency-checklist.md](../ux-consistency-checklist.md) - Pre-commit UX verification
- [design-consistency-guide.md](design-consistency-guide.md) - SKUEL design token usage

**Key Rules:**
1. Use SKUEL tokens for spacing/containers
2. Use DaisyUI semantic colors (not Tailwind palette)
3. Follow custom CSS boundary patterns
4. Mobile-first responsive approach

## Related Skills

- **[daisyui](../daisyui/SKILL.md)** - Semantic components built on Tailwind
- **[monsterui](../monsterui/SKILL.md)** - FastHTML components (highest abstraction)
- **[js-alpine](../js-alpine/SKILL.md)** - Client-side interactivity with Tailwind styling

## Foundation

This skill has no prerequisites. It is the base CSS layer.

## See Also

- [decision-guide.md](decision-guide.md) - When to use Tailwind vs MonsterUI vs DaisyUI
- [fasthtml-integration.md](fasthtml-integration.md) - FastHTML integration patterns
- Tailwind Docs: https://tailwindcss.com/docs
