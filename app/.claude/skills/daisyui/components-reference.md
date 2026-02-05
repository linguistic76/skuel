# DaisyUI Components Reference

## Complete Component List

### Actions

| Component | Class | Description |
|-----------|-------|-------------|
| Button | `btn` | Interactive button |
| Dropdown | `dropdown` | Clickable dropdown menu |
| Modal | `modal` | Dialog popup |
| Swap | `swap` | Toggle between two elements |
| Theme Controller | `theme-controller` | Theme toggle input |

### Data Display

| Component | Class | Description |
|-----------|-------|-------------|
| Accordion | `collapse` | Expandable content sections |
| Avatar | `avatar` | User profile image |
| Badge | `badge` | Status indicator or tag |
| Card | `card` | Content container |
| Carousel | `carousel` | Image/content slider |
| Chat Bubble | `chat` | Chat message bubble |
| Countdown | `countdown` | Animated countdown |
| Diff | `diff` | Compare two items |
| Kbd | `kbd` | Keyboard key indicator |
| Stat | `stat` | Statistics display |
| Table | `table` | Data table |
| Timeline | `timeline` | Vertical timeline |

### Navigation

| Component | Class | Description |
|-----------|-------|-------------|
| Breadcrumbs | `breadcrumbs` | Navigation trail |
| Bottom Navigation | `btm-nav` | Mobile bottom nav |
| Link | `link` | Styled anchor |
| Menu | `menu` | Navigation menu |
| Navbar | `navbar` | Top navigation bar |
| Pagination | `pagination` | Page navigation |
| Steps | `steps` | Progress steps |
| Tabs | `tabs` | Tab navigation |

### Feedback

| Component | Class | Description |
|-----------|-------|-------------|
| Alert | `alert` | Notification banner |
| Loading | `loading` | Loading indicators |
| Progress | `progress` | Progress bar |
| Radial Progress | `radial-progress` | Circular progress |
| Skeleton | `skeleton` | Loading placeholder |
| Toast | `toast` | Popup notification |
| Tooltip | `tooltip` | Hover tooltip |

### Data Input

| Component | Class | Description |
|-----------|-------|-------------|
| Checkbox | `checkbox` | Toggle checkbox |
| File Input | `file-input` | File upload |
| Radio | `radio` | Radio selection |
| Range | `range` | Slider input |
| Rating | `rating` | Star rating |
| Select | `select` | Dropdown select |
| Text Input | `input` | Text field |
| Textarea | `textarea` | Multi-line text |
| Toggle | `toggle` | Switch toggle |

### Layout

| Component | Class | Description |
|-----------|-------|-------------|
| Artboard | `artboard` | Fixed size container |
| Divider | `divider` | Section separator |
| Drawer | `drawer` | Side panel |
| Footer | `footer` | Page footer |
| Hero | `hero` | Hero section |
| Indicator | `indicator` | Position indicator |
| Join | `join` | Group elements |
| Mask | `mask` | Image masks/shapes |
| Stack | `stack` | Stacked elements |

### Mockup

| Component | Class | Description |
|-----------|-------|-------------|
| Browser | `mockup-browser` | Browser mockup |
| Code | `mockup-code` | Code window |
| Phone | `mockup-phone` | Phone mockup |
| Window | `mockup-window` | Window mockup |

---

## Button Modifiers

### Colors
- `btn-primary` - Primary brand color
- `btn-secondary` - Secondary color
- `btn-accent` - Accent color
- `btn-info` - Info blue
- `btn-success` - Success green
- `btn-warning` - Warning yellow
- `btn-error` - Error red
- `btn-ghost` - No background
- `btn-link` - Link style
- `btn-neutral` - Neutral color

### Sizes
- `btn-lg` - Large (h-16)
- `btn-md` - Medium (h-12, default)
- `btn-sm` - Small (h-8)
- `btn-xs` - Extra small (h-6)

### Shapes
- `btn-wide` - Extra horizontal padding
- `btn-block` - Full width
- `btn-circle` - Circle shape
- `btn-square` - Square shape

### States
- `btn-outline` - Outline style
- `btn-active` - Active/pressed
- `btn-disabled` - Disabled style
- `no-animation` - Disable click animation

---

## Input Modifiers

### Variants
- `input-bordered` - With border
- `input-ghost` - Transparent until focus
- `input-primary` - Primary color border on focus
- `input-secondary`, `input-accent`, etc.

### Sizes
- `input-lg`, `input-md`, `input-sm`, `input-xs`

---

## Card Structure

```html
<div class="card">           <!-- Container -->
  <figure></figure>          <!-- Optional image -->
  <div class="card-body">    <!-- Content wrapper -->
    <h2 class="card-title">  <!-- Title -->
      Title
      <div class="badge">NEW</div>  <!-- Optional badge -->
    </h2>
    <p></p>                  <!-- Description -->
    <div class="card-actions justify-end">  <!-- Actions -->
      <button class="btn btn-primary">Action</button>
    </div>
  </div>
</div>
```

### Card Modifiers
- `card-compact` - Less padding
- `card-side` - Image on side (horizontal)
- `card-bordered` - With border
- `image-full` - Image behind content

---

## Modal Structure

```html
<dialog class="modal">           <!-- Dialog element -->
  <div class="modal-box">        <!-- Content container -->
    <h3 class="font-bold">Title</h3>
    <p>Content</p>
    <div class="modal-action">   <!-- Buttons area -->
      <form method="dialog">
        <button class="btn">Close</button>
      </form>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">  <!-- Click outside -->
    <button>close</button>
  </form>
</dialog>
```

### Opening Modals
```javascript
document.getElementById('my_modal').showModal()
```

---

## Alert Icons

Each alert type pairs with a specific icon:

```html
<!-- Info icon -->
<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" class="stroke-current shrink-0 w-6 h-6">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
</svg>

<!-- Success icon -->
<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
</svg>

<!-- Warning icon -->
<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
</svg>

<!-- Error icon -->
<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
</svg>
```

---

## Loading Variants

| Class | Style |
|-------|-------|
| `loading-spinner` | Rotating spinner |
| `loading-dots` | Bouncing dots |
| `loading-ring` | Rotating ring |
| `loading-ball` | Bouncing ball |
| `loading-bars` | Animated bars |
| `loading-infinity` | Infinity symbol |

Sizes: `loading-xs`, `loading-sm`, `loading-md`, `loading-lg`

---

## Menu Structure

```html
<ul class="menu">
  <li><a>Link</a></li>              <!-- Regular item -->
  <li><a class="active">Active</a></li>  <!-- Active state -->
  <li class="disabled"><a>Disabled</a></li>  <!-- Disabled -->
  <li>
    <details open>                   <!-- Submenu -->
      <summary>Parent</summary>
      <ul>
        <li><a>Child 1</a></li>
        <li><a>Child 2</a></li>
      </ul>
    </details>
  </li>
  <li class="menu-title">Title</li>  <!-- Section title -->
</ul>
```

### Menu Modifiers
- `menu-horizontal` - Horizontal layout
- `menu-vertical` - Vertical layout (default)
- `menu-compact` - Less padding
- `menu-lg`, `menu-md`, `menu-sm`, `menu-xs` - Sizes

---

## Drawer Structure

```html
<div class="drawer">
  <input id="drawer" type="checkbox" class="drawer-toggle">

  <div class="drawer-content">
    <!-- Main content -->
    <label for="drawer" class="btn drawer-button">Open</label>
  </div>

  <div class="drawer-side">
    <label for="drawer" class="drawer-overlay"></label>
    <ul class="menu bg-white min-h-full w-80 p-4">
      <!-- Sidebar content -->
    </ul>
  </div>
</div>
```

### Drawer Modifiers
- `drawer-end` - Drawer on right side
- `lg:drawer-open` - Always open on large screens

---

## Tabs Structure

### Radio-based (Recommended)

```html
<div role="tablist" class="tabs tabs-bordered">
  <input type="radio" name="tabs" role="tab" class="tab" aria-label="Tab 1" checked>
  <div role="tabpanel" class="tab-content p-4">Content 1</div>

  <input type="radio" name="tabs" role="tab" class="tab" aria-label="Tab 2">
  <div role="tabpanel" class="tab-content p-4">Content 2</div>
</div>
```

### Tab Modifiers
- `tabs-bordered` - Border below tabs
- `tabs-lifted` - Lifted card style
- `tabs-boxed` - Box container
- `tabs-lg`, `tabs-md`, `tabs-sm`, `tabs-xs` - Sizes

---

## Form Control Structure

```html
<label class="form-control w-full">
  <div class="label">
    <span class="label-text">Label</span>
    <span class="label-text-alt">Alt text</span>
  </div>
  <input type="text" class="input input-bordered">
  <div class="label">
    <span class="label-text-alt">Helper text</span>
  </div>
</label>
```

---

## Join (Button Groups)

```html
<div class="join">
  <button class="btn join-item">Button 1</button>
  <button class="btn join-item">Button 2</button>
  <button class="btn join-item">Button 3</button>
</div>

<!-- Vertical -->
<div class="join join-vertical">
  <button class="btn join-item">Top</button>
  <button class="btn join-item">Middle</button>
  <button class="btn join-item">Bottom</button>
</div>
```

---

## Indicator

```html
<div class="indicator">
  <span class="indicator-item badge badge-primary">99+</span>
  <button class="btn">Inbox</button>
</div>

<!-- Position modifiers -->
<span class="indicator-item indicator-top indicator-start">Top left</span>
<span class="indicator-item indicator-top indicator-center">Top center</span>
<span class="indicator-item indicator-top indicator-end">Top right</span>
<span class="indicator-item indicator-middle indicator-start">Middle left</span>
<span class="indicator-item indicator-middle indicator-center">Center</span>
<span class="indicator-item indicator-middle indicator-end">Middle right</span>
<span class="indicator-item indicator-bottom indicator-start">Bottom left</span>
<span class="indicator-item indicator-bottom indicator-center">Bottom center</span>
<span class="indicator-item indicator-bottom indicator-end">Bottom right</span>
```
