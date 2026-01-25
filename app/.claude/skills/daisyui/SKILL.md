---
name: daisyui
description: Expert guide for DaisyUI component library. Use when building UI with pre-styled components (buttons, forms, modals, navigation), implementing themes, or when the user mentions DaisyUI, component libraries, semantic components, or accessible UI elements.
allowed-tools: Read, Grep, Glob
---

# DaisyUI 5 Component Library

## Core Philosophy

> "Semantic component classes that compose with Tailwind utilities"

DaisyUI 5 provides pre-built, accessible components as CSS classes for Tailwind CSS 4. No JavaScript required (though integrates with React/Vue/HTMX). Combine DaisyUI components with Tailwind utilities for customization.

## Quick Start

```html
<!-- DaisyUI button vs raw Tailwind -->
<button class="btn btn-primary">DaisyUI (1 class)</button>
<button class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">Tailwind (6+ classes)</button>
```

## Installation (DaisyUI 5)

**Important:** DaisyUI 5 requires Tailwind CSS 4. The `tailwind.config.js` file is deprecated.

### NPM Installation

```bash
npm i -D daisyui@latest
```

**CSS file (the only config needed):**
```css
@import "tailwindcss";
@plugin "daisyui";
```

### CDN Installation

```html
<link href="https://cdn.jsdelivr.net/npm/daisyui@5" rel="stylesheet" type="text/css" />
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
```

## Configuration

DaisyUI 5 config is done in CSS using `@plugin "daisyui"`:

### Minimal Config
```css
@plugin "daisyui";
```

### Light Theme Only
```css
@plugin "daisyui" {
  themes: light --default;
}
```

### Full Config with Defaults
```css
@plugin "daisyui" {
  themes: light --default, dark --prefersdark;
  root: ":root";
  include: ;
  exclude: ;
  prefix: ;
  logs: true;
}
```

### Advanced Config Example
```css
@plugin "daisyui" {
  themes: light, dark, cupcake, bumblebee --default, emerald, corporate,
          synthwave --prefersdark, retro, cyberpunk, valentine, halloween,
          garden, forest, aqua, lofi, pastel, fantasy, wireframe, black,
          luxury, dracula, cmyk, autumn, business, acid, lemonade, night,
          coffee, winter, dim, nord, sunset, caramellatte, abyss, silk;
  root: ":root";
  exclude: rootscrollgutter, checkbox;
  prefix: daisy-;
  logs: false;
}
```

## Custom Themes with OKLCH Colors

```css
@import "tailwindcss";
@plugin "daisyui";
@plugin "daisyui/theme" {
  name: "mytheme";
  default: true;
  prefersdark: false;
  color-scheme: light;

  --color-base-100: oklch(98% 0.02 240);
  --color-base-200: oklch(95% 0.03 240);
  --color-base-300: oklch(92% 0.04 240);
  --color-base-content: oklch(20% 0.05 240);
  --color-primary: oklch(55% 0.3 240);
  --color-primary-content: oklch(98% 0.01 240);
  --color-secondary: oklch(70% 0.25 200);
  --color-secondary-content: oklch(98% 0.01 200);
  --color-accent: oklch(65% 0.25 160);
  --color-accent-content: oklch(98% 0.01 160);
  --color-neutral: oklch(50% 0.05 240);
  --color-neutral-content: oklch(98% 0.01 240);
  --color-info: oklch(70% 0.2 220);
  --color-info-content: oklch(98% 0.01 220);
  --color-success: oklch(65% 0.25 140);
  --color-success-content: oklch(98% 0.01 140);
  --color-warning: oklch(80% 0.25 80);
  --color-warning-content: oklch(20% 0.05 80);
  --color-error: oklch(65% 0.3 30);
  --color-error-content: oklch(98% 0.01 30);

  --radius-selector: 1rem;
  --radius-field: 0.25rem;
  --radius-box: 0.5rem;
  --size-selector: 0.25rem;
  --size-field: 0.25rem;
  --border: 1px;
  --depth: 1;
  --noise: 0;
}
```

## Semantic Colors

DaisyUI uses semantic color names that adapt to themes:

| Color | Purpose |
|-------|---------|
| `primary` | Primary actions, links |
| `primary-content` | Text on primary color |
| `secondary` | Secondary actions |
| `secondary-content` | Text on secondary color |
| `accent` | Accented elements |
| `accent-content` | Text on accent color |
| `neutral` | Neutral backgrounds |
| `neutral-content` | Text on neutral color |
| `base-100` | Page background |
| `base-200` | Slightly darker background |
| `base-300` | Even darker background |
| `base-content` | Text on base colors |
| `info` | Informational |
| `success` | Success states |
| `warning` | Warning states |
| `error` | Error states |

**Rules:**
- Use semantic colors for theme compatibility
- No need for `dark:` prefix with DaisyUI colors
- Avoid Tailwind color names (like `red-500`) to maintain theme flexibility

## Class Name Categories

DaisyUI classes are categorized as:
- `component`: Required component class
- `part`: Child part of a component
- `style`: Sets a specific style
- `behavior`: Changes behavior
- `color`: Sets a specific color
- `size`: Sets a specific size
- `placement`: Sets a specific placement
- `direction`: Sets a specific direction
- `modifier`: Modifies the component
- `variant`: Prefixes for conditional styles (e.g., `is-drawer-open:`)

---

## Components

### Button

```html
<!-- Colors -->
<button class="btn">Default</button>
<button class="btn btn-primary">Primary</button>
<button class="btn btn-secondary">Secondary</button>
<button class="btn btn-accent">Accent</button>
<button class="btn btn-info">Info</button>
<button class="btn btn-success">Success</button>
<button class="btn btn-warning">Warning</button>
<button class="btn btn-error">Error</button>
<button class="btn btn-neutral">Neutral</button>

<!-- Styles -->
<button class="btn btn-outline btn-primary">Outline</button>
<button class="btn btn-dash btn-primary">Dash</button>
<button class="btn btn-soft btn-primary">Soft</button>
<button class="btn btn-ghost">Ghost</button>
<button class="btn btn-link">Link</button>

<!-- Sizes -->
<button class="btn btn-xs">XS</button>
<button class="btn btn-sm">Small</button>
<button class="btn btn-md">Medium</button>
<button class="btn btn-lg">Large</button>
<button class="btn btn-xl">XL</button>

<!-- Modifiers -->
<button class="btn btn-wide">Wide</button>
<button class="btn btn-block">Block (100%)</button>
<button class="btn btn-square">Square</button>
<button class="btn btn-circle">Circle</button>

<!-- States -->
<button class="btn btn-active">Active</button>
<button class="btn btn-disabled">Disabled</button>
```

### Input

```html
<!-- Basic -->
<input type="text" class="input" placeholder="Type here" />

<!-- With colors -->
<input type="text" class="input input-primary" />
<input type="text" class="input input-error" />

<!-- Sizes -->
<input type="text" class="input input-xs" />
<input type="text" class="input input-sm" />
<input type="text" class="input input-md" />
<input type="text" class="input input-lg" />
<input type="text" class="input input-xl" />

<!-- Ghost style -->
<input type="text" class="input input-ghost" />
```

### Label & Floating Label

```html
<!-- Regular label -->
<label class="input">
  <span class="label">Username</span>
  <input type="text" placeholder="Type here" />
</label>

<!-- Floating label -->
<label class="floating-label">
  <input type="text" placeholder="Email" class="input" />
  <span>Email</span>
</label>
```

### Select

```html
<select class="select">
  <option disabled selected>Pick an option</option>
  <option>Option 1</option>
  <option>Option 2</option>
</select>

<!-- With color and size -->
<select class="select select-primary select-lg">...</select>
```

### Textarea

```html
<textarea class="textarea" placeholder="Enter text"></textarea>
<textarea class="textarea textarea-primary textarea-lg"></textarea>
```

### Checkbox

```html
<input type="checkbox" class="checkbox" />
<input type="checkbox" class="checkbox checkbox-primary" />
<input type="checkbox" class="checkbox checkbox-lg" />
```

### Radio

```html
<input type="radio" name="radio-group" class="radio" />
<input type="radio" name="radio-group" class="radio radio-primary" />
```

### Toggle (Switch)

```html
<input type="checkbox" class="toggle" />
<input type="checkbox" class="toggle toggle-primary toggle-lg" />
```

### Range Slider

```html
<input type="range" min="0" max="100" value="50" class="range" />
<input type="range" class="range range-primary range-lg" />
```

### File Input

```html
<input type="file" class="file-input" />
<input type="file" class="file-input file-input-primary file-input-lg" />
```

### Fieldset

```html
<fieldset class="fieldset">
  <legend class="fieldset-legend">Account Info</legend>
  <input type="text" class="input" placeholder="Username" />
  <p class="label">Enter your username</p>
</fieldset>
```

### Filter

```html
<!-- Using HTML form -->
<form class="filter">
  <input class="btn btn-square" type="reset" value="×"/>
  <input class="btn" type="radio" name="filter1" aria-label="All"/>
  <input class="btn" type="radio" name="filter1" aria-label="Active"/>
  <input class="btn" type="radio" name="filter1" aria-label="Inactive"/>
</form>

<!-- Without form -->
<div class="filter">
  <input class="btn filter-reset" type="radio" name="filter2" aria-label="×"/>
  <input class="btn" type="radio" name="filter2" aria-label="Tab 1"/>
  <input class="btn" type="radio" name="filter2" aria-label="Tab 2"/>
</div>
```

### Validator

```html
<input type="email" class="input validator" required />
<p class="validator-hint">Please enter a valid email</p>
```

---

### Card

```html
<div class="card">
  <figure><img src="image.jpg" alt="" /></figure>
  <div class="card-body">
    <h2 class="card-title">Card Title</h2>
    <p>Card description text.</p>
    <div class="card-actions">
      <button class="btn btn-primary">Action</button>
    </div>
  </div>
</div>

<!-- Styles -->
<div class="card card-border">...</div>
<div class="card card-dash">...</div>

<!-- Sizes -->
<div class="card card-xs">...</div>
<div class="card card-sm">...</div>
<div class="card card-md">...</div>
<div class="card card-lg">...</div>
<div class="card card-xl">...</div>

<!-- Horizontal card -->
<div class="card card-side">...</div>
<!-- Responsive: -->
<div class="card sm:card-horizontal">...</div>
```

### Accordion / Collapse

```html
<!-- Single collapse -->
<div tabindex="0" class="collapse collapse-arrow">
  <div class="collapse-title">Click to expand</div>
  <div class="collapse-content">Hidden content here</div>
</div>

<!-- Accordion group (only one open at a time) -->
<div class="collapse collapse-arrow">
  <input type="radio" name="accordion" checked="checked" />
  <div class="collapse-title">Section 1</div>
  <div class="collapse-content">Content 1</div>
</div>
<div class="collapse collapse-arrow">
  <input type="radio" name="accordion" />
  <div class="collapse-title">Section 2</div>
  <div class="collapse-content">Content 2</div>
</div>

<!-- Modifiers -->
<div class="collapse collapse-plus">...</div>  <!-- Plus icon -->
<div class="collapse collapse-open">...</div>  <!-- Force open -->
<div class="collapse collapse-close">...</div> <!-- Force closed -->
```

### Alert

```html
<div role="alert" class="alert">Default alert</div>
<div role="alert" class="alert alert-info">Info message</div>
<div role="alert" class="alert alert-success">Success!</div>
<div role="alert" class="alert alert-warning">Warning</div>
<div role="alert" class="alert alert-error">Error</div>

<!-- Styles -->
<div role="alert" class="alert alert-outline alert-info">Outline</div>
<div role="alert" class="alert alert-dash alert-info">Dash</div>
<div role="alert" class="alert alert-soft alert-info">Soft</div>

<!-- Direction (responsive) -->
<div role="alert" class="alert alert-vertical sm:alert-horizontal">...</div>
```

### Badge

```html
<span class="badge">Default</span>
<span class="badge badge-primary">Primary</span>
<span class="badge badge-secondary">Secondary</span>
<span class="badge badge-accent">Accent</span>
<span class="badge badge-success">Success</span>

<!-- Styles -->
<span class="badge badge-outline badge-primary">Outline</span>
<span class="badge badge-dash badge-primary">Dash</span>
<span class="badge badge-soft badge-primary">Soft</span>
<span class="badge badge-ghost">Ghost</span>

<!-- Sizes -->
<span class="badge badge-xs">XS</span>
<span class="badge badge-sm">SM</span>
<span class="badge badge-md">MD</span>
<span class="badge badge-lg">LG</span>
<span class="badge badge-xl">XL</span>
```

### Avatar

```html
<div class="avatar">
  <div>
    <img src="avatar.jpg" />
  </div>
</div>

<!-- With status -->
<div class="avatar avatar-online">...</div>
<div class="avatar avatar-offline">...</div>

<!-- Placeholder (no image) -->
<div class="avatar avatar-placeholder">
  <div class="w-12 bg-neutral text-neutral-content">AB</div>
</div>

<!-- With mask shapes -->
<div class="avatar">
  <div class="mask mask-squircle w-12">
    <img src="avatar.jpg" />
  </div>
</div>

<!-- Avatar group -->
<div class="avatar-group">
  <div class="avatar"><div><img src="1.jpg" /></div></div>
  <div class="avatar"><div><img src="2.jpg" /></div></div>
  <div class="avatar avatar-placeholder"><div>+5</div></div>
</div>
```

### Indicator

```html
<div class="indicator">
  <span class="indicator-item badge badge-primary">99+</span>
  <button class="btn">Inbox</button>
</div>

<!-- Placement -->
<div class="indicator">
  <span class="indicator-item indicator-start indicator-top badge">Top Left</span>
  <span class="indicator-item indicator-center indicator-middle badge">Center</span>
  <span class="indicator-item indicator-end indicator-bottom badge">Bottom Right</span>
  <div class="bg-base-200 p-8">Content</div>
</div>
```

### Loading

```html
<span class="loading loading-spinner"></span>
<span class="loading loading-dots"></span>
<span class="loading loading-ring"></span>
<span class="loading loading-ball"></span>
<span class="loading loading-bars"></span>
<span class="loading loading-infinity"></span>

<!-- Sizes -->
<span class="loading loading-spinner loading-xs"></span>
<span class="loading loading-spinner loading-sm"></span>
<span class="loading loading-spinner loading-md"></span>
<span class="loading loading-spinner loading-lg"></span>
<span class="loading loading-spinner loading-xl"></span>
```

### Skeleton

```html
<div class="skeleton h-32 w-full"></div>
<div class="skeleton skeleton-text w-48">Loading text...</div>
```

### Progress

```html
<progress class="progress" value="50" max="100"></progress>
<progress class="progress progress-primary" value="70" max="100"></progress>
<progress class="progress progress-success" value="90" max="100"></progress>
```

### Radial Progress

```html
<div class="radial-progress" style="--value:70;" aria-valuenow="70" role="progressbar">70%</div>
<div class="radial-progress text-primary" style="--value:85; --size:8rem; --thickness:4px;">85%</div>
```

### Stat

```html
<div class="stats">
  <div class="stat">
    <div class="stat-title">Total Users</div>
    <div class="stat-value">31K</div>
    <div class="stat-desc">Jan 1st - Feb 1st</div>
  </div>
  <div class="stat">
    <div class="stat-figure text-primary">
      <svg>...</svg>
    </div>
    <div class="stat-title">Revenue</div>
    <div class="stat-value text-primary">$4,200</div>
    <div class="stat-desc text-success">+40%</div>
    <div class="stat-actions">
      <button class="btn btn-sm">View</button>
    </div>
  </div>
</div>

<!-- Direction -->
<div class="stats stats-vertical">...</div>
<div class="stats stats-horizontal">...</div>
```

### Status

```html
<span class="status"></span>
<span class="status status-primary"></span>
<span class="status status-success"></span>
<span class="status status-error"></span>

<!-- Sizes -->
<span class="status status-xs"></span>
<span class="status status-sm"></span>
<span class="status status-md"></span>
<span class="status status-lg"></span>
```

### Countdown

```html
<span class="countdown">
  <span style="--value:23;" aria-live="polite" aria-label="23">23</span>
</span>

<!-- Timer example -->
<span class="countdown font-mono text-4xl">
  <span style="--value:10;">10</span>h
  <span style="--value:24;">24</span>m
  <span style="--value:56;">56</span>s
</span>
```

### Diff

```html
<figure class="diff aspect-16/9">
  <div class="diff-item-1"><img src="before.jpg" /></div>
  <div class="diff-item-2"><img src="after.jpg" /></div>
  <div class="diff-resizer"></div>
</figure>
```

---

### Modal

```html
<!-- HTML dialog (recommended) -->
<button onclick="my_modal.showModal()">Open Modal</button>
<dialog id="my_modal" class="modal">
  <div class="modal-box">
    <h3 class="font-bold text-lg">Modal Title</h3>
    <p class="py-4">Modal content here.</p>
    <div class="modal-action">
      <form method="dialog">
        <button class="btn">Close</button>
      </form>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>

<!-- With close button -->
<dialog id="modal2" class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2">×</button>
    </form>
    <h3 class="font-bold text-lg">Title</h3>
    <p>Content</p>
  </div>
</dialog>

<!-- Placement -->
<dialog class="modal modal-bottom">...</dialog>
<dialog class="modal modal-top modal-start">...</dialog>
```

### Drawer

```html
<div class="drawer">
  <input id="my-drawer" type="checkbox" class="drawer-toggle" />
  <div class="drawer-content">
    <!-- Page content -->
    <label for="my-drawer" class="btn drawer-button">Open Drawer</label>
  </div>
  <div class="drawer-side">
    <label for="my-drawer" aria-label="close sidebar" class="drawer-overlay"></label>
    <ul class="menu bg-base-200 min-h-full w-80 p-4">
      <li><a>Item 1</a></li>
      <li><a>Item 2</a></li>
    </ul>
  </div>
</div>

<!-- Always open on large screens -->
<div class="drawer lg:drawer-open">...</div>

<!-- Right side -->
<div class="drawer drawer-end">...</div>
```

**Drawer Variant Prefixes (DaisyUI 5):**

```html
<!-- Collapsible sidebar with icons -->
<div class="drawer lg:drawer-open">
  <input id="my-drawer-4" type="checkbox" class="drawer-toggle" />
  <div class="drawer-content">Page content</div>
  <div class="drawer-side is-drawer-close:overflow-visible">
    <label for="my-drawer-4" class="drawer-overlay"></label>
    <div class="is-drawer-close:w-14 is-drawer-open:w-64 bg-base-200 min-h-full">
      <ul class="menu">
        <li>
          <button class="is-drawer-close:tooltip is-drawer-close:tooltip-right" data-tip="Home">
            🏠
            <span class="is-drawer-close:hidden">Home</span>
          </button>
        </li>
      </ul>
    </div>
  </div>
</div>
```

### Dropdown

```html
<!-- Using details/summary -->
<details class="dropdown">
  <summary class="btn">Click me</summary>
  <ul class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow">
    <li><a>Item 1</a></li>
    <li><a>Item 2</a></li>
  </ul>
</details>

<!-- Using popover API -->
<button popovertarget="dropdown1" style="anchor-name:--dropdown1">Open</button>
<ul class="dropdown-content menu" popover id="dropdown1" style="position-anchor:--dropdown1">
  <li><a>Item 1</a></li>
</ul>

<!-- Placement -->
<details class="dropdown dropdown-end">...</details>
<details class="dropdown dropdown-top">...</details>
<details class="dropdown dropdown-left">...</details>
<details class="dropdown dropdown-right">...</details>

<!-- Hover to open -->
<details class="dropdown dropdown-hover">...</details>
```

### Toast

```html
<div class="toast">
  <div class="alert alert-info">New message</div>
</div>

<!-- Placement -->
<div class="toast toast-start">...</div>
<div class="toast toast-center">...</div>
<div class="toast toast-end">...</div>
<div class="toast toast-top">...</div>
<div class="toast toast-middle">...</div>
<div class="toast toast-bottom">...</div>
```

### Tooltip

```html
<div class="tooltip" data-tip="Hello">
  <button class="btn">Hover me</button>
</div>

<!-- Placement -->
<div class="tooltip tooltip-right" data-tip="Right">...</div>
<div class="tooltip tooltip-left" data-tip="Left">...</div>
<div class="tooltip tooltip-top" data-tip="Top">...</div>
<div class="tooltip tooltip-bottom" data-tip="Bottom">...</div>

<!-- Colors -->
<div class="tooltip tooltip-primary" data-tip="Primary">...</div>
```

---

### Navbar

```html
<div class="navbar bg-base-200">
  <div class="navbar-start">
    <a class="btn btn-ghost text-xl">Brand</a>
  </div>
  <div class="navbar-center">
    <ul class="menu menu-horizontal">
      <li><a>Home</a></li>
      <li><a>About</a></li>
    </ul>
  </div>
  <div class="navbar-end">
    <button class="btn btn-primary">Login</button>
  </div>
</div>
```

### Menu

```html
<!-- Vertical menu -->
<ul class="menu bg-base-200 w-56 rounded-box">
  <li><a>Item 1</a></li>
  <li><a class="menu-active">Active Item</a></li>
  <li class="menu-title">Category</li>
  <li><a>Item 2</a></li>
  <li>
    <details open>
      <summary>Submenu</summary>
      <ul>
        <li><a>Sub Item 1</a></li>
        <li><a>Sub Item 2</a></li>
      </ul>
    </details>
  </li>
</ul>

<!-- Horizontal menu -->
<ul class="menu menu-horizontal bg-base-200 rounded-box">
  <li><a>Item 1</a></li>
  <li><a>Item 2</a></li>
</ul>

<!-- Sizes -->
<ul class="menu menu-xs">...</ul>
<ul class="menu menu-sm">...</ul>
<ul class="menu menu-md">...</ul>
<ul class="menu menu-lg">...</ul>
```

### Tabs

```html
<!-- Using buttons -->
<div role="tablist" class="tabs tabs-box">
  <button role="tab" class="tab">Tab 1</button>
  <button role="tab" class="tab tab-active">Tab 2</button>
  <button role="tab" class="tab">Tab 3</button>
</div>

<!-- Using radio inputs with content -->
<div role="tablist" class="tabs tabs-lift">
  <input type="radio" name="tabs" class="tab" aria-label="Tab 1" checked />
  <div class="tab-content bg-base-100 p-6">Tab 1 content</div>

  <input type="radio" name="tabs" class="tab" aria-label="Tab 2" />
  <div class="tab-content bg-base-100 p-6">Tab 2 content</div>
</div>

<!-- Styles -->
<div class="tabs tabs-box">...</div>
<div class="tabs tabs-border">...</div>
<div class="tabs tabs-lift">...</div>
```

### Breadcrumbs

```html
<div class="breadcrumbs">
  <ul>
    <li><a>Home</a></li>
    <li><a>Category</a></li>
    <li>Current Page</li>
  </ul>
</div>
```

### Pagination (Join)

```html
<div class="join">
  <button class="join-item btn">«</button>
  <button class="join-item btn">1</button>
  <button class="join-item btn btn-active">2</button>
  <button class="join-item btn">3</button>
  <button class="join-item btn">»</button>
</div>

<!-- Vertical -->
<div class="join join-vertical">...</div>
```

### Steps

```html
<ul class="steps">
  <li class="step step-primary">Register</li>
  <li class="step step-primary">Choose Plan</li>
  <li class="step">Purchase</li>
  <li class="step">Complete</li>
</ul>

<!-- Vertical -->
<ul class="steps steps-vertical">...</ul>

<!-- With icons -->
<ul class="steps">
  <li class="step step-primary" data-content="✓">Done</li>
  <li class="step step-primary step-icon"><span class="step-icon">2</span>Current</li>
</ul>
```

### Dock (Bottom Navigation)

```html
<div class="dock">
  <button>
    <svg><!-- home icon --></svg>
    <span class="dock-label">Home</span>
  </button>
  <button class="dock-active">
    <svg><!-- search icon --></svg>
    <span class="dock-label">Search</span>
  </button>
  <button>
    <svg><!-- profile icon --></svg>
    <span class="dock-label">Profile</span>
  </button>
</div>

<!-- Sizes -->
<div class="dock dock-xs">...</div>
<div class="dock dock-sm">...</div>
<div class="dock dock-lg">...</div>
```

**Note:** Add `<meta name="viewport" content="viewport-fit=cover">` for iOS responsiveness.

---

### FAB (Floating Action Button)

```html
<!-- Simple FAB -->
<div class="fab">
  <button class="btn btn-lg btn-circle btn-primary">+</button>
</div>

<!-- FAB with speed dial -->
<div class="fab">
  <div tabindex="0" role="button" class="btn btn-lg btn-circle btn-primary">+</div>
  <button class="btn btn-lg btn-circle">📝</button>
  <button class="btn btn-lg btn-circle">📷</button>
  <button class="btn btn-lg btn-circle">📎</button>
</div>

<!-- FAB with labels -->
<div class="fab">
  <div tabindex="0" role="button" class="btn btn-lg btn-circle btn-primary">+</div>
  <div>Note<button class="btn btn-lg btn-circle">📝</button></div>
  <div>Photo<button class="btn btn-lg btn-circle">📷</button></div>
</div>

<!-- Flower arrangement (quarter circle) -->
<div class="fab fab-flower">
  <div tabindex="0" role="button" class="btn btn-lg btn-circle btn-primary">+</div>
  <button class="fab-main-action btn btn-circle btn-lg">✓</button>
  <button class="btn btn-lg btn-circle">1</button>
  <button class="btn btn-lg btn-circle">2</button>
  <button class="btn btn-lg btn-circle">3</button>
</div>
```

---

### Table

```html
<div class="overflow-x-auto">
  <table class="table">
    <thead>
      <tr>
        <th></th>
        <th>Name</th>
        <th>Job</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <th>1</th>
        <td>John</td>
        <td>Developer</td>
      </tr>
      <tr>
        <th>2</th>
        <td>Jane</td>
        <td>Designer</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- Zebra stripes -->
<table class="table table-zebra">...</table>

<!-- Pin headers/columns -->
<table class="table table-pin-rows table-pin-cols">...</table>

<!-- Sizes -->
<table class="table table-xs">...</table>
<table class="table table-sm">...</table>
<table class="table table-lg">...</table>
```

### List

```html
<ul class="list">
  <li class="list-row">
    <div><img src="avatar.jpg" class="w-10 rounded" /></div>
    <div>
      <div class="font-bold">Title</div>
      <div class="text-sm opacity-60">Subtitle</div>
    </div>
    <button class="btn btn-ghost btn-sm">Action</button>
  </li>
</ul>

<!-- Modifiers -->
<li class="list-row list-col-wrap">...</li>  <!-- Wrap to next line -->
<li class="list-row list-col-grow">...</li>  <!-- Fill remaining space -->
```

---

### Timeline

```html
<ul class="timeline">
  <li>
    <div class="timeline-start">2020</div>
    <div class="timeline-middle">
      <svg><!-- icon --></svg>
    </div>
    <div class="timeline-end timeline-box">Event 1</div>
    <hr />
  </li>
  <li>
    <hr />
    <div class="timeline-start timeline-box">Event 2</div>
    <div class="timeline-middle">
      <svg><!-- icon --></svg>
    </div>
    <div class="timeline-end">2021</div>
    <hr />
  </li>
</ul>

<!-- Vertical/Horizontal -->
<ul class="timeline timeline-vertical">...</ul>
<ul class="timeline timeline-horizontal">...</ul>

<!-- Snap icon to start -->
<ul class="timeline timeline-snap-icon">...</ul>

<!-- Compact (all items on one side) -->
<ul class="timeline timeline-compact">...</ul>
```

### Chat

```html
<div class="chat chat-start">
  <div class="chat-image avatar">
    <div class="w-10 rounded-full">
      <img src="avatar.jpg" />
    </div>
  </div>
  <div class="chat-header">
    Obi-Wan Kenobi
    <time class="text-xs opacity-50">12:45</time>
  </div>
  <div class="chat-bubble">Hello there!</div>
  <div class="chat-footer opacity-50">Delivered</div>
</div>

<div class="chat chat-end">
  <div class="chat-bubble chat-bubble-primary">General Kenobi!</div>
</div>

<!-- Colors -->
<div class="chat-bubble chat-bubble-primary">...</div>
<div class="chat-bubble chat-bubble-secondary">...</div>
<div class="chat-bubble chat-bubble-accent">...</div>
<div class="chat-bubble chat-bubble-info">...</div>
<div class="chat-bubble chat-bubble-success">...</div>
```

---

### Hero

```html
<div class="hero min-h-screen bg-base-200">
  <div class="hero-content text-center">
    <div class="max-w-md">
      <h1 class="text-5xl font-bold">Hello there</h1>
      <p class="py-6">Welcome to our platform.</p>
      <button class="btn btn-primary">Get Started</button>
    </div>
  </div>
</div>

<!-- With overlay -->
<div class="hero min-h-screen" style="background-image: url(hero.jpg);">
  <div class="hero-overlay bg-opacity-60"></div>
  <div class="hero-content text-neutral-content">
    <h1>Title</h1>
  </div>
</div>
```

### Footer

```html
<footer class="footer bg-base-200 p-10">
  <nav>
    <h6 class="footer-title">Services</h6>
    <a class="link link-hover">Branding</a>
    <a class="link link-hover">Design</a>
  </nav>
  <nav>
    <h6 class="footer-title">Company</h6>
    <a class="link link-hover">About</a>
    <a class="link link-hover">Contact</a>
  </nav>
</footer>

<!-- Centered footer -->
<footer class="footer footer-center p-10 bg-base-200">
  <p>Copyright © 2024</p>
</footer>

<!-- Responsive -->
<footer class="footer footer-vertical sm:footer-horizontal">...</footer>
```

### Carousel

```html
<div class="carousel">
  <div class="carousel-item">
    <img src="1.jpg" />
  </div>
  <div class="carousel-item">
    <img src="2.jpg" />
  </div>
</div>

<!-- Full width items -->
<div class="carousel w-full">
  <div class="carousel-item w-full">...</div>
</div>

<!-- Snap points -->
<div class="carousel carousel-start">...</div>
<div class="carousel carousel-center">...</div>
<div class="carousel carousel-end">...</div>

<!-- Vertical -->
<div class="carousel carousel-vertical h-96">...</div>
```

---

### Mask

```html
<img class="mask mask-squircle" src="image.jpg" />
<img class="mask mask-heart" src="image.jpg" />
<img class="mask mask-hexagon" src="image.jpg" />
<img class="mask mask-pentagon" src="image.jpg" />
<img class="mask mask-diamond" src="image.jpg" />
<img class="mask mask-circle" src="image.jpg" />
<img class="mask mask-star" src="image.jpg" />
<img class="mask mask-triangle" src="image.jpg" />
```

### Rating

```html
<div class="rating">
  <input type="radio" name="rating-1" class="mask mask-star" />
  <input type="radio" name="rating-1" class="mask mask-star" checked />
  <input type="radio" name="rating-1" class="mask mask-star" />
  <input type="radio" name="rating-1" class="mask mask-star" />
  <input type="radio" name="rating-1" class="mask mask-star" />
</div>

<!-- Half stars -->
<div class="rating rating-half">
  <input type="radio" name="rating-2" class="rating-hidden" />
  <input type="radio" name="rating-2" class="mask mask-star mask-half-1" />
  <input type="radio" name="rating-2" class="mask mask-star mask-half-2" />
  <!-- ... more halves -->
</div>

<!-- Sizes -->
<div class="rating rating-xs">...</div>
<div class="rating rating-lg">...</div>
```

### Swap

```html
<!-- Checkbox controlled -->
<label class="swap">
  <input type="checkbox" />
  <div class="swap-on">ON</div>
  <div class="swap-off">OFF</div>
</label>

<!-- With animation -->
<label class="swap swap-rotate">
  <input type="checkbox" />
  <svg class="swap-on"><!-- sun icon --></svg>
  <svg class="swap-off"><!-- moon icon --></svg>
</label>

<label class="swap swap-flip">
  <input type="checkbox" />
  <div class="swap-on">😊</div>
  <div class="swap-off">😢</div>
</label>
```

### Stack

```html
<div class="stack">
  <div class="card bg-primary text-primary-content">Card 1</div>
  <div class="card bg-secondary text-secondary-content">Card 2</div>
  <div class="card bg-accent text-accent-content">Card 3</div>
</div>

<!-- Direction -->
<div class="stack stack-top">...</div>
<div class="stack stack-bottom">...</div>
<div class="stack stack-start">...</div>
<div class="stack stack-end">...</div>
```

---

### Hover 3D

```html
<div class="hover-3d my-12 mx-2">
  <figure class="max-w-100 rounded-2xl">
    <img src="card.jpg" alt="3D hover card" />
  </figure>
  <div></div><div></div><div></div><div></div>
  <div></div><div></div><div></div><div></div>
</div>
```

**Rules:**
- Must have exactly 9 children (1 content + 8 empty divs for hover zones)
- Content should be non-interactive (no buttons/links inside)
- Can be a `<div>` or `<a>` tag

### Hover Gallery

```html
<figure class="hover-gallery max-w-60">
  <img src="product-1.jpg" />
  <img src="product-2.jpg" />
  <img src="product-3.jpg" />
  <img src="product-4.jpg" />
</figure>
```

**Rules:**
- Can include up to 10 images
- Needs a max-width set
- Images should have same dimensions

### Text Rotate

```html
<span class="text-rotate text-4xl">
  <span class="justify-items-center">
    <span>DESIGN</span>
    <span>DEVELOP</span>
    <span>DEPLOY</span>
    <span>SCALE</span>
  </span>
</span>

<!-- Inline with sentence -->
<span>
  We help
  <span class="text-rotate">
    <span>
      <span class="bg-teal-400 text-teal-800 px-2">Designers</span>
      <span class="bg-red-400 text-red-800 px-2">Developers</span>
      <span class="bg-blue-400 text-blue-800 px-2">Managers</span>
    </span>
  </span>
</span>

<!-- Custom duration (12 seconds) -->
<span class="text-rotate duration-12000">...</span>
```

---

### Mockups

```html
<!-- Phone -->
<div class="mockup-phone">
  <div class="mockup-phone-camera"></div>
  <div class="mockup-phone-display">
    <img src="screenshot.jpg" />
  </div>
</div>

<!-- Browser -->
<div class="mockup-browser bg-base-300">
  <div class="mockup-browser-toolbar">
    <div class="input">https://example.com</div>
  </div>
  <div class="bg-base-200 p-4">Browser content</div>
</div>

<!-- Code -->
<div class="mockup-code">
  <pre data-prefix="$"><code>npm i daisyui</code></pre>
  <pre data-prefix=">" class="text-warning"><code>installing...</code></pre>
  <pre data-prefix=">" class="text-success"><code>Done!</code></pre>
</div>

<!-- Window -->
<div class="mockup-window bg-base-300">
  <div class="bg-base-200 p-4">Window content</div>
</div>
```

### Calendar

DaisyUI provides styles for popular calendar libraries:

```html
<!-- Cally web component -->
<calendar-date class="cally">...</calendar-date>

<!-- Pikaday -->
<input type="text" class="input pika-single">

<!-- React Day Picker -->
<DayPicker className="react-day-picker" />
```

### Theme Controller

```html
<!-- Toggle theme with checkbox -->
<input type="checkbox" value="dark" class="toggle theme-controller" />

<!-- Select theme with radio -->
<input type="radio" name="theme" value="light" class="btn theme-controller" aria-label="Light" />
<input type="radio" name="theme" value="dark" class="btn theme-controller" aria-label="Dark" />
```

---

## Join (Grouping)

```html
<!-- Group buttons -->
<div class="join">
  <button class="btn join-item">Left</button>
  <button class="btn join-item">Center</button>
  <button class="btn join-item">Right</button>
</div>

<!-- Group inputs -->
<div class="join">
  <input class="input join-item" placeholder="Email" />
  <button class="btn join-item">Subscribe</button>
</div>

<!-- Vertical -->
<div class="join join-vertical">
  <button class="btn join-item">Top</button>
  <button class="btn join-item">Bottom</button>
</div>

<!-- Responsive -->
<div class="join join-vertical lg:join-horizontal">...</div>
```

## Divider

```html
<div class="divider">OR</div>
<div class="divider divider-primary">Text</div>

<!-- Direction -->
<div class="divider divider-horizontal">AND</div>
<div class="divider divider-vertical">VS</div>

<!-- Placement -->
<div class="divider divider-start">Left aligned</div>
<div class="divider divider-end">Right aligned</div>
```

## KBD (Keyboard)

```html
<kbd class="kbd">A</kbd>
<kbd class="kbd">Ctrl</kbd>+<kbd class="kbd">C</kbd>

<!-- Sizes -->
<kbd class="kbd kbd-xs">xs</kbd>
<kbd class="kbd kbd-sm">sm</kbd>
<kbd class="kbd kbd-md">md</kbd>
<kbd class="kbd kbd-lg">lg</kbd>
```

## Link

```html
<a class="link">Default link</a>
<a class="link link-primary">Primary</a>
<a class="link link-secondary">Secondary</a>
<a class="link link-hover">Hover only</a>
```

---

## Best Practices

### 1. Use DaisyUI 5 Config (not tailwind.config.js)
```css
@import "tailwindcss";
@plugin "daisyui" {
  themes: light --default, dark --prefersdark;
}
```

### 2. Combine with Tailwind Utilities
```html
<button class="btn btn-primary w-full mt-4 shadow-lg">Submit</button>
```

### 3. Use Semantic Colors
```html
<!-- GOOD: Theme-aware -->
<div class="bg-base-100 text-base-content">
  <button class="btn btn-primary">Action</button>
</div>

<!-- AVOID: Fixed colors break in dark mode -->
<div class="bg-white text-gray-900">...</div>
```

### 4. Responsive Patterns
```html
<!-- Responsive drawer -->
<div class="drawer lg:drawer-open">...</div>

<!-- Responsive menu -->
<ul class="menu menu-vertical lg:menu-horizontal">...</ul>

<!-- Responsive stats -->
<div class="stats stats-vertical md:stats-horizontal">...</div>
```

### 5. Force Override with `!`
```html
<!-- When DaisyUI specificity wins, use ! suffix -->
<button class="btn bg-red-500!">Custom background</button>
```

---

## CRITICAL: Avoid Hardcoded Colors

**Rule:** Never use hardcoded colors (hex, rgb, raw Tailwind) when DaisyUI semantic colors exist.

### Decision Matrix

| Use Case | Use This | Don't Use |
|----------|----------|-----------|
| Page background | `bg-base-100` | `bg-white`, `bg-gray-50` |
| Card background | `bg-base-200` | `bg-gray-100` |
| Primary action | `btn-primary` | `bg-blue-600` |
| Text color | `text-base-content` | `text-gray-900` |

### When Hardcoded Colors Are Acceptable

Only for:
1. Brand-specific elements (logo colors)
2. Data visualization (charts with specific meaning)
3. One-off decorative elements (not interactive)

### Migration Pattern

**Before:**
```html
<div class="bg-white border border-gray-200 text-gray-900">
  <button class="bg-blue-600 text-white">Action</button>
</div>
```

**After:**
```html
<div class="bg-base-100 border border-base-300 text-base-content">
  <button class="btn btn-primary">Action</button>
</div>
```

---

## Additional Resources

- [components-reference.md](components-reference.md) - Quick reference
- [components-complete.md](components-complete.md) - Full component catalog
- [css-variables-guide.md](css-variables-guide.md) - DaisyUI 5 CSS variables and OKLCH format
- [theme-application-guide.md](theme-application-guide.md) - Theme cascading and FOUC prevention

## UX Consistency

**CRITICAL:** Before building UI components, review:
- [ux-consistency-checklist.md](../ux-consistency-checklist.md) - Pre-commit UX verification
- [css-variables-guide.md](css-variables-guide.md) - CSS variable naming and OKLCH format
- [theme-application-guide.md](theme-application-guide.md) - Theme application patterns

**Key Rules:**
1. Use semantic colors (not hardcoded)
2. Set data-theme on <html> (not <body>)
3. Understand OKLCH color format
4. Prevent FOUC with inline theme script

## Related Skills

- **[tailwind-css](../tailwind-css/SKILL.md)** - DaisyUI extends Tailwind
- **[monsterui](../monsterui/SKILL.md)** - FastHTML wrapper using DaisyUI
- **[fasthtml](../fasthtml/SKILL.md)** - Server-rendered components

## See Also

- [DaisyUI Docs](https://daisyui.com/components/)
- [Theme Generator](https://daisyui.com/theme-generator/)
- [DaisyUI 5 Release Notes](https://daisyui.com/docs/v5/)
