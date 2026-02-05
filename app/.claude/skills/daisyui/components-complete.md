# DaisyUI 5 Complete Component Reference

Quick reference for all DaisyUI 5 components with class names and syntax.

## Class Name Legend

| Type | Purpose |
|------|---------|
| `component` | Required base class |
| `part` | Child element class |
| `style` | Visual variant |
| `behavior` | State/interaction modifier |
| `color` | Color variant |
| `size` | Size variant |
| `placement` | Position variant |
| `direction` | Orientation variant |
| `modifier` | Additional modification |
| `variant` | Conditional prefix (e.g., `is-drawer-open:`) |

---

## Actions

### Button
```
component: btn
color: btn-neutral, btn-primary, btn-secondary, btn-accent, btn-info, btn-success, btn-warning, btn-error
style: btn-outline, btn-dash, btn-soft, btn-ghost, btn-link
behavior: btn-active, btn-disabled
size: btn-xs, btn-sm, btn-md, btn-lg, btn-xl
modifier: btn-wide, btn-block, btn-square, btn-circle
```

### Dropdown
```
component: dropdown
part: dropdown-content
placement: dropdown-start, dropdown-center, dropdown-end, dropdown-top, dropdown-bottom, dropdown-left, dropdown-right
modifier: dropdown-hover, dropdown-open, dropdown-close
```

### Modal
```
component: modal
part: modal-box, modal-action, modal-backdrop, modal-toggle
modifier: modal-open
placement: modal-top, modal-middle, modal-bottom, modal-start, modal-end
```

### Swap
```
component: swap
part: swap-on, swap-off, swap-indeterminate
modifier: swap-active
style: swap-rotate, swap-flip
```

### Theme Controller
```
component: theme-controller
```

---

## Data Display

### Accordion / Collapse
```
component: collapse
part: collapse-title, collapse-content
modifier: collapse-arrow, collapse-plus, collapse-open, collapse-close
```

### Avatar
```
component: avatar, avatar-group
modifier: avatar-online, avatar-offline, avatar-placeholder
```

### Badge
```
component: badge
style: badge-outline, badge-dash, badge-soft, badge-ghost
color: badge-neutral, badge-primary, badge-secondary, badge-accent, badge-info, badge-success, badge-warning, badge-error
size: badge-xs, badge-sm, badge-md, badge-lg, badge-xl
```

### Card
```
component: card
part: card-title, card-body, card-actions
style: card-border, card-dash
modifier: card-side, image-full
size: card-xs, card-sm, card-md, card-lg, card-xl
```

### Carousel
```
component: carousel
part: carousel-item
modifier: carousel-start, carousel-center, carousel-end
direction: carousel-horizontal, carousel-vertical
```

### Chat Bubble
```
component: chat
part: chat-image, chat-header, chat-footer, chat-bubble
placement: chat-start, chat-end
color: chat-bubble-neutral, chat-bubble-primary, chat-bubble-secondary, chat-bubble-accent, chat-bubble-info, chat-bubble-success, chat-bubble-warning, chat-bubble-error
```

### Countdown
```
component: countdown
```
CSS Variable: `--value` (0-999)

### Diff
```
component: diff
part: diff-item-1, diff-item-2, diff-resizer
```

### Kbd (Keyboard)
```
component: kbd
size: kbd-xs, kbd-sm, kbd-md, kbd-lg, kbd-xl
```

### List
```
component: list, list-row
modifier: list-col-wrap, list-col-grow
```

### Stat
```
component: stats
part: stat, stat-title, stat-value, stat-desc, stat-figure, stat-actions
direction: stats-horizontal, stats-vertical
```

### Status
```
component: status
color: status-neutral, status-primary, status-secondary, status-accent, status-info, status-success, status-warning, status-error
size: status-xs, status-sm, status-md, status-lg, status-xl
```

### Table
```
component: table
modifier: table-zebra, table-pin-rows, table-pin-cols
size: table-xs, table-sm, table-md, table-lg, table-xl
```

### Timeline
```
component: timeline
part: timeline-start, timeline-middle, timeline-end
modifier: timeline-snap-icon, timeline-box, timeline-compact
direction: timeline-vertical, timeline-horizontal
```

---

## Data Input

### Checkbox
```
component: checkbox
color: checkbox-primary, checkbox-secondary, checkbox-accent, checkbox-neutral, checkbox-success, checkbox-warning, checkbox-info, checkbox-error
size: checkbox-xs, checkbox-sm, checkbox-md, checkbox-lg, checkbox-xl
```

### File Input
```
component: file-input
style: file-input-ghost
color: file-input-neutral, file-input-primary, file-input-secondary, file-input-accent, file-input-info, file-input-success, file-input-warning, file-input-error
size: file-input-xs, file-input-sm, file-input-md, file-input-lg, file-input-xl
```

### Filter
```
component: filter
part: filter-reset
```

### Label
```
component: label, floating-label
```

### Radio
```
component: radio
color: radio-neutral, radio-primary, radio-secondary, radio-accent, radio-success, radio-warning, radio-info, radio-error
size: radio-xs, radio-sm, radio-md, radio-lg, radio-xl
```

### Range
```
component: range
color: range-neutral, range-primary, range-secondary, range-accent, range-success, range-warning, range-info, range-error
size: range-xs, range-sm, range-md, range-lg, range-xl
```

### Rating
```
component: rating
modifier: rating-half, rating-hidden
size: rating-xs, rating-sm, rating-md, rating-lg, rating-xl
```

### Select
```
component: select
style: select-ghost
color: select-neutral, select-primary, select-secondary, select-accent, select-info, select-success, select-warning, select-error
size: select-xs, select-sm, select-md, select-lg, select-xl
```

### Text Input
```
component: input
style: input-ghost
color: input-neutral, input-primary, input-secondary, input-accent, input-info, input-success, input-warning, input-error
size: input-xs, input-sm, input-md, input-lg, input-xl
```

### Textarea
```
component: textarea
style: textarea-ghost
color: textarea-neutral, textarea-primary, textarea-secondary, textarea-accent, textarea-info, textarea-success, textarea-warning, textarea-error
size: textarea-xs, textarea-sm, textarea-md, textarea-lg, textarea-xl
```

### Toggle
```
component: toggle
color: toggle-primary, toggle-secondary, toggle-accent, toggle-neutral, toggle-success, toggle-warning, toggle-info, toggle-error
size: toggle-xs, toggle-sm, toggle-md, toggle-lg, toggle-xl
```

### Validator
```
component: validator
part: validator-hint
```

### Fieldset
```
component: fieldset, label
part: fieldset-legend
```

---

## Layout

### Divider
```
component: divider
color: divider-neutral, divider-primary, divider-secondary, divider-accent, divider-success, divider-warning, divider-info, divider-error
direction: divider-vertical, divider-horizontal
placement: divider-start, divider-end
```

### Drawer
```
component: drawer
part: drawer-toggle, drawer-content, drawer-side, drawer-overlay
placement: drawer-end
modifier: drawer-open
variant: is-drawer-open:, is-drawer-close:
```

### Footer
```
component: footer
part: footer-title
placement: footer-center
direction: footer-horizontal, footer-vertical
```

### Hero
```
component: hero
part: hero-content, hero-overlay
```

### Indicator
```
component: indicator
part: indicator-item
placement: indicator-start, indicator-center, indicator-end, indicator-top, indicator-middle, indicator-bottom
```

### Join
```
component: join, join-item
direction: join-vertical, join-horizontal
```

### Mask
```
component: mask
style: mask-squircle, mask-heart, mask-hexagon, mask-hexagon-2, mask-decagon, mask-pentagon, mask-diamond, mask-square, mask-circle, mask-star, mask-star-2, mask-triangle, mask-triangle-2, mask-triangle-3, mask-triangle-4
modifier: mask-half-1, mask-half-2
```

### Stack
```
component: stack
modifier: stack-top, stack-bottom, stack-start, stack-end
```

---

## Navigation

### Breadcrumbs
```
component: breadcrumbs
```

### Dock (Bottom Navigation)
```
component: dock
part: dock-label
modifier: dock-active
size: dock-xs, dock-sm, dock-md, dock-lg, dock-xl
```

### Link
```
component: link
style: link-hover
color: link-neutral, link-primary, link-secondary, link-accent, link-success, link-info, link-warning, link-error
```

### Menu
```
component: menu
part: menu-title, menu-dropdown, menu-dropdown-toggle
modifier: menu-disabled, menu-active, menu-focus, menu-dropdown-show
size: menu-xs, menu-sm, menu-md, menu-lg, menu-xl
direction: menu-vertical, menu-horizontal
```

### Navbar
```
component: navbar
part: navbar-start, navbar-center, navbar-end
```

### Pagination
Uses `join` component with `join-item` buttons.

### Steps
```
component: steps
part: step, step-icon
color: step-neutral, step-primary, step-secondary, step-accent, step-info, step-success, step-warning, step-error
direction: steps-vertical, steps-horizontal
```

### Tabs
```
component: tabs
part: tab, tab-content
style: tabs-box, tabs-border, tabs-lift
modifier: tab-active, tab-disabled
placement: tabs-top, tabs-bottom
```

---

## Feedback

### Alert
```
component: alert
style: alert-outline, alert-dash, alert-soft
color: alert-info, alert-success, alert-warning, alert-error
direction: alert-vertical, alert-horizontal
```

### Loading
```
component: loading
style: loading-spinner, loading-dots, loading-ring, loading-ball, loading-bars, loading-infinity
size: loading-xs, loading-sm, loading-md, loading-lg, loading-xl
```

### Progress
```
component: progress
color: progress-neutral, progress-primary, progress-secondary, progress-accent, progress-info, progress-success, progress-warning, progress-error
```

### Radial Progress
```
component: radial-progress
```
CSS Variables: `--value` (0-100), `--size`, `--thickness`

### Skeleton
```
component: skeleton
modifier: skeleton-text
```

### Toast
```
component: toast
placement: toast-start, toast-center, toast-end, toast-top, toast-middle, toast-bottom
```

### Tooltip
```
component: tooltip
placement: tooltip-top, tooltip-bottom, tooltip-left, tooltip-right
color: tooltip-primary, tooltip-secondary, tooltip-accent, tooltip-info, tooltip-success, tooltip-warning, tooltip-error
```

---

## Floating Action Button

### FAB
```
component: fab
part: fab-close, fab-main-action
modifier: fab-flower
```

---

## Interactive Effects

### Hover 3D
```
component: hover-3d
```
Requires exactly 9 children: 1 content + 8 empty divs

### Hover Gallery
```
component: hover-gallery
```
Contains 2-10 images

### Text Rotate
```
component: text-rotate
```
Duration via Tailwind: `duration-{ms}`

---

## Mockups

### Browser
```
component: mockup-browser
part: mockup-browser-toolbar
```

### Code
```
component: mockup-code
```
Use `<pre data-prefix="{prefix}">` for line prefixes

### Phone
```
component: mockup-phone
part: mockup-phone-camera, mockup-phone-display
```

### Window
```
component: mockup-window
```

---

## Calendar Support

### Cally
```
component: cally
```

### Pikaday
```
component: pika-single (on input)
```

### React Day Picker
```
component: react-day-picker
```

---

## Color System

### Semantic Colors
| Color | Purpose |
|-------|---------|
| `primary` | Primary brand color |
| `primary-content` | Text on primary |
| `secondary` | Secondary brand color |
| `secondary-content` | Text on secondary |
| `accent` | Accent color |
| `accent-content` | Text on accent |
| `neutral` | Neutral dark color |
| `neutral-content` | Text on neutral |
| `base-100` | Page background |
| `base-200` | Darker background |
| `base-300` | Even darker background |
| `base-content` | Text on base |
| `info` | Informational |
| `info-content` | Text on info |
| `success` | Success |
| `success-content` | Text on success |
| `warning` | Warning |
| `warning-content` | Text on warning |
| `error` | Error |
| `error-content` | Text on error |

### Built-in Themes
light, dark, cupcake, bumblebee, emerald, corporate, synthwave, retro, cyberpunk, valentine, halloween, garden, forest, aqua, lofi, pastel, fantasy, wireframe, black, luxury, dracula, cmyk, autumn, business, acid, lemonade, night, coffee, winter, dim, nord, sunset, caramellatte, abyss, silk

---

## Size Modifiers Quick Reference

| Size | Button | Input | Badge | Loading | Menu |
|------|--------|-------|-------|---------|------|
| xs | btn-xs | input-xs | badge-xs | loading-xs | menu-xs |
| sm | btn-sm | input-sm | badge-sm | loading-sm | menu-sm |
| md | btn-md | input-md | badge-md | loading-md | menu-md |
| lg | btn-lg | input-lg | badge-lg | loading-lg | menu-lg |
| xl | btn-xl | input-xl | badge-xl | loading-xl | - |

---

## Common Patterns

### Form with Labels
```html
<label class="input">
  <span class="label">Email</span>
  <input type="email" />
</label>
```

### Card with Actions
```html
<div class="card">
  <div class="card-body">
    <h2 class="card-title">Title</h2>
    <p>Content</p>
    <div class="card-actions justify-end">
      <button class="btn btn-primary">Action</button>
    </div>
  </div>
</div>
```

### Modal Dialog
```html
<dialog id="modal" class="modal">
  <div class="modal-box">
    <h3>Title</h3>
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
```

### Responsive Drawer
```html
<div class="drawer lg:drawer-open">
  <input id="drawer" type="checkbox" class="drawer-toggle" />
  <div class="drawer-content">
    <!-- Content -->
  </div>
  <div class="drawer-side">
    <label for="drawer" class="drawer-overlay"></label>
    <ul class="menu bg-white w-80 min-h-full">
      <!-- Menu items -->
    </ul>
  </div>
</div>
```

### Navbar with Dropdown
```html
<div class="navbar bg-white border-b border-gray-200">
  <div class="navbar-start">
    <a class="btn btn-ghost text-xl">Brand</a>
  </div>
  <div class="navbar-end">
    <details class="dropdown dropdown-end">
      <summary class="btn btn-ghost">Menu</summary>
      <ul class="dropdown-content menu bg-base-100 w-52">
        <li><a>Item 1</a></li>
        <li><a>Item 2</a></li>
      </ul>
    </details>
  </div>
</div>
```

### Stats Block
```html
<div class="stats shadow">
  <div class="stat">
    <div class="stat-title">Users</div>
    <div class="stat-value">4,200</div>
    <div class="stat-desc">+21% from last month</div>
  </div>
</div>
```

### Steps Progress
```html
<ul class="steps">
  <li class="step step-primary">Start</li>
  <li class="step step-primary">Process</li>
  <li class="step">Complete</li>
</ul>
```

---

## CSS Variables

### Theme Customization
```css
--radius-selector: 1rem;    /* checkbox, toggle, badge */
--radius-field: 0.25rem;    /* button, input, select */
--radius-box: 0.5rem;       /* card, modal, alert */
--size-selector: 0.25rem;   /* checkbox, toggle */
--size-field: 0.25rem;      /* button, input */
--border: 1px;              /* border width */
--depth: 1;                 /* 0 or 1: shadow/3D effect */
--noise: 0;                 /* 0 or 1: grain effect */
```

### Component Variables
```css
/* Radial Progress */
--value: 70;        /* 0-100 */
--size: 5rem;       /* diameter */
--thickness: 4px;   /* stroke width */

/* Countdown */
--value: 42;        /* 0-999 */
```

---

## Responsive Prefixes

Apply responsive variants:
```html
<!-- Menu horizontal on large screens -->
<ul class="menu menu-vertical lg:menu-horizontal">

<!-- Stats horizontal on medium screens -->
<div class="stats stats-vertical md:stats-horizontal">

<!-- Drawer always open on large screens -->
<div class="drawer lg:drawer-open">

<!-- Card horizontal on small screens -->
<div class="card sm:card-horizontal">
```

---

## Accessibility Notes

- Use `role="tablist"` for tabs
- Use `role="tab"` for tab buttons
- Use `aria-label` for icon buttons
- Use `aria-valuenow` for progress indicators
- Use `aria-live="polite"` for countdown
- Use `tabindex="0"` for focusable elements
- Use `form method="dialog"` for modal close buttons
