# ui-browser Reference: HTMX & Alpine.js Pattern Recipes

> On-demand pattern recipes for the [`ui-browser`](SKILL.md) skill. SKILL.md holds the philosophy, decision table, request lifecycle, component architecture, and anti-patterns; this file holds the copy-paste pattern catalog.

## HTMX Common Patterns

### Active Search

```html
<input type="search" name="q"
       hx-get="/search"
       hx-trigger="input changed delay:300ms, search"
       hx-target="#results"
       hx-indicator=".htmx-indicator"
       placeholder="Search...">
<span class="htmx-indicator loading loading-spinner loading-sm"></span>
<div id="results"></div>
```

### Infinite Scroll

```html
<div id="items">
  <!-- Items here -->
  <div hx-get="/items?page=2"
       hx-trigger="revealed"
       hx-swap="outerHTML">
    Loading more...
  </div>
</div>
```

### Click to Edit

```html
<!-- View mode -->
<div hx-get="/users/1/edit" hx-trigger="click" hx-swap="outerHTML">
  Click to edit: John Doe
</div>
<!-- Server returns edit form; form submits back with hx-put, returns view mode -->
```

### Form Submission (SKUEL Pattern)

```python
Form(
    # ... form controls ...
    Button("Create Task", type="submit", cls=ButtonT.primary),
    hx_post="/tasks/quick-add",
    hx_target="#task-list",
    hx_swap="beforeend",
    hx_on="htmx:afterRequest: this.reset()",  # Clear form on success
)
```

### File Upload with HTMX

HTMX handles multipart file uploads natively via `hx-encoding`:

```python
Form(
    Input(type="file", name="files", accept=".yaml,.yml", multiple=True),
    Button("Upload", type="submit", cls=ButtonT.primary),
    Span(Loading(), id="spinner", cls="htmx-indicator"),  # Loading from ui.components
    **{
        "hx-post": "/upload/files",
        "hx-target": "#results",
        "hx-swap": "innerHTML",
        "hx-encoding": "multipart/form-data",
        "hx-indicator": "#spinner",
    },
)
```

**Server handler** reads `UploadFile` objects from form data:
```python
form = await request.form()
raw_files = form.getlist("files")
for f in raw_files:
    if isinstance(f, UploadFile):
        content = await f.read()
        filename = f.filename
```

**Example:** `/upload` page — see `adapters/inbound/upload_ui.py`.

### Out-of-Band (OOB) Swaps — One Request, Multiple DOM Updates

OOB swaps let a single HTTP response update multiple, non-adjacent DOM elements at once. Any element in the response body tagged with `hx-swap-oob="true"` is pulled out and routed to the page element with the same `id`, independently of where the request was made.

**Mental model:** Normal HTMX swaps one target. OOB swaps are "side channel" deliveries — the server attaches extra payloads to a response and HTMX distributes them automatically.

#### When to use OOB

| Scenario | Solution |
|----------|----------|
| One action should update two unrelated UI regions | OOB |
| Multiple hub blocks share the same DB query | OOB combined endpoint (see Hub Page pattern) |
| N independent hub blocks each need their own DB call | Individual `preview_url` per block |
| Sidebar badges that load after the page is painted | OOB |

**Rule of thumb:** If you find yourself calling the same service method from 3 different HTMX endpoints to populate 3 blocks on the same page, collapse them into one OOB endpoint.

#### Basic pattern

```python
# FastHTML: server returns multiple OOB elements
@rt("/api/sidebar/badges")
async def sidebar_badges(request):
    stats = await service.get_stats(user_uid)
    fragments = []
    for slug, count in stats.items():
        fragments.append(
            Span(
                count,
                id=f"sidebar-badge-{slug}",   # matches page element id
                hx_swap_oob="true",            # this is the OOB marker
            )
        )
    return Div(*fragments)
```

```python
# FastHTML: page renders passive targets (id only, no HTMX attrs)
# and a hidden trigger with hx_swap="none"
Span(id="sidebar-badge-tasks"),    # passive — waits for OOB
Span(id="sidebar-badge-goals"),    # passive — waits for OOB

# Hidden trigger — fires once on load, main swap is discarded
Div(
    hx_get="/api/sidebar/badges",
    hx_trigger="load",
    hx_swap="none",   # ← critical: trigger div has no content to swap
)
```

#### Hub blocks with shared data: StudentHub (canonical example)

The StudentHub has 3 preview blocks (Needs Review, Revision Requested, Completed) that all come from a single `get_student_submissions()` DB call. Before OOB, each block fired its own endpoint — 3 identical DB round-trips. After:

```python
# ui/teaching/student_hub.py
#
# preview_url=None → HubDomainBlock renders the panel with id only, no hx-* attrs.
# The combined endpoint will OOB-swap the content in.
blocks = [
    HubBlockData(..., slug="pending",   preview_url=None),   # OOB target
    HubBlockData(..., slug="revision",  preview_url=None),   # OOB target
    HubBlockData(..., slug="completed", preview_url=None),   # OOB target
    HubBlockData(..., slug="ku", preview_url=".../ku/preview"),  # independent — different DB call
]

# One hidden trigger covers the 3 shared blocks
oob_trigger = Div(
    hx_get=f"/api/teaching/students/{uid}/submissions/preview",
    hx_trigger="load",
    hx_swap="none",
)
```

```python
# adapters/inbound/teaching_ui.py — combined endpoint
@rt("/api/teaching/students/{uid}/submissions/preview")
async def student_submissions_preview(request, uid, ...):
    pending, revision, completed, _ = await _get_bucketed_submissions(user_uid, uid)

    def _make_fragment(slug, rows, empty_label):
        content = HubPreviewGrid([...]) if rows else HubPreviewEmpty(empty_label)
        return Div(content, id=f"hub-panel-{slug}", hx_swap_oob="true")  # ← OOB

    return Div(
        _make_fragment("pending",   pending,   "submissions needing review"),
        _make_fragment("revision",  revision,  "revision requests"),
        _make_fragment("completed", completed, "completed submissions"),
    )
# Result: 1 DB call instead of 3 identical ones.
```

Network tab before/after on `/teaching/students/{uid}`:
- **Before:** 4 HTMX requests (pending/preview, revision/preview, completed/preview, ku/preview)
- **After:** 2 HTMX requests (submissions/preview → OOB, ku/preview → independent)

#### SKUEL live examples

| Location | Endpoint | OOB count | What it updates |
|----------|----------|-----------|-----------------|
| `user_profile_ui.py:363` | `GET /api/sidebar/badges` | 9 | Sidebar count+health badges |
| `teaching_ui.py` | `GET /api/teaching/students/{uid}/submissions/preview` | 3 | StudentHub submission buckets |

#### Implementation checklist

1. Give each target element a stable, unique `id` (e.g. `hub-panel-{slug}`, `sidebar-badge-{slug}`)
2. Do NOT put HTMX attrs on the passive target elements — they are just `<div id="...">Loading...</div>`
3. The trigger element uses `hx_swap="none"` — its only job is to fire the request
4. Each fragment in the response has `hx_swap_oob="true"` and the matching `id`
5. Wrap all OOB fragments in an outer `Div` so FastHTML renders them — the outer element is the main swap target and gets discarded since `hx_swap="none"`

**See also:** `docs/patterns/HUB_PAGE_PATTERN.md` → "Pattern: OOB Swaps for Shared-Data Hub Blocks"

---

### HTMX Response Headers (Server → Browser)

```python
# Redirect after action
response.headers["HX-Redirect"] = "/dashboard"

# Trigger client event (Alpine can listen)
response.headers["HX-Trigger"] = "taskCreated"
# or with data: '{"taskCreated": {"id": "task_abc"}}'

# Full page refresh
response.headers["HX-Refresh"] = "true"

# Update browser URL
response.headers["HX-Push-Url"] = "/tasks"
```

### Shell-First Page Loading

The standard SKUEL pattern for eliminating blank-screen waits: the route returns page chrome immediately, a `hx-trigger="load"` div fires the content request after the browser paints.

```python
from ui.patterns.loading import content_loading_placeholder

# Shell — returns immediately (zero DB calls)
@rt("/settings")
def settings_page(request: Request) -> Any:
    require_authenticated_user(request)
    content = Div(
        PageHeader("Settings", subtitle="Manage your preferences"),
        content_loading_placeholder("/settings/content", "settings-content"),
    )
    return BasePage(content, title="Settings", request=request)

# Fragment — DB work here, replaces the placeholder
@rt("/settings/content")
async def settings_content_fragment(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    user = await user_service.get_user(user_uid)
    return Div(render_preferences_editor(user), id="settings-content")
```

**Always set `id=` on every fragment return** — success and error alike. The placeholder div that HTMX replaces carries the target id; once swapped out, that id is gone. A bare `render_error_banner(...)` without an `id` leaves nothing for retries to target. Rule: every `return` in a `*/content` fragment must include `id="<target-id>"` on its root element.

**Navbar notification bell** is a miniature version of this pattern — already in `_notification_badge_placeholder()`:
```python
Div(
    _notification_button(0),          # renders 0-count immediately
    id="notification-bell",
    hx_get="/api/navbar/notification-badge",
    hx_trigger="load",
    hx_swap="outerHTML",
    cls="relative",
)
```

**When NOT to use this pattern:**
- POST mutation routes (must return synchronous result)
- Hub pages with HTMX tab blocks (already lazy by design)
- Fragments themselves — DB calls in fragments are expected

**See also:** `docs/patterns/SHELL_FIRST_PAGE_PATTERN.md`, `skuel-ui` skill → "Shell-First Page Loading"

---

### Loading States

```html
<!-- Indicator (shows during request) -->
<button hx-get="/slow-data" hx-indicator="#spinner">Load</button>
<span id="spinner" class="htmx-indicator loading loading-spinner loading-sm"></span>

<!-- Disable element during request -->
<button hx-post="/save" hx-disabled-elt="this">Save</button>

<!-- Alpine + HTMX loading state -->
<div x-data="{ loading: false }"
     @htmx:before-request="loading = true"
     @htmx:after-request="loading = false">
  <button hx-get="/data">
    <span x-show="!loading">Load</span>
    <span x-show="loading" class="animate-spin text-muted-foreground text-sm">Loading...</span>
  </button>
</div>
```

### Accessibility with HTMX

```html
<!-- Announce updates to screen readers -->
<div aria-live="polite" id="results">
  <!-- HTMX updates here get announced -->
</div>

<!-- Focus first input after swap -->
<form hx-post="/step"
      hx-on:htmx:after-swap="this.querySelector('input')?.focus()">
```

---

## Alpine.js Common Patterns

### Modal — AlpineModal

Use `AlpineModal` from `ui/patterns/modal.py` for all Alpine.js-controlled modals. It standardizes backdrop, click-outside-to-close, transitions, and `x-cloak`.

```python
from ui.patterns.modal import AlpineModal

AlpineModal(
    H3("Confirm Action", cls="font-bold text-lg"),
    P("Are you sure?"),
    Div(
        Button("Cancel", cls=ButtonT.ghost, **{"@click": "open = false"}),
        Button("Confirm", cls=ButtonT.primary),
        cls="flex gap-2 justify-end mt-4",
    ),
    show="open",              # Alpine.js expression for visibility
    close="open = false",     # Alpine.js expression to close
    max_width="max-w-lg",     # Tailwind max-width class
    scrollable=False,         # Set True for tall content (max-h-[80vh])
)
```

Adopted in: calendar components, sharing modal, insight card modal.

### Collapsible Section

```html
<div x-data="{ expanded: false }">
  <button @click="expanded = !expanded" class="flex justify-between w-full">
    <span>Section Title</span>
    <span x-text="expanded ? '▲' : '▼'"></span>
  </button>
  <div x-show="expanded" x-transition>
    Collapsible content
  </div>
</div>
```

### Tabs

**Prefer SKUEL's `TabContainer` from `ui.components`** for standard tabs. For fully custom dynamic tab styling, use Alpine `:style` with SKUEL's semantic CSS custom properties (defined in `static/css/input.css`) — this bypasses all CSS class compilation concerns.

```python
# ✅ SKUEL tab pattern — inline styles via Alpine :style (home_hub.py canonical example)
_ACTIVE_STYLE = (
    "background-color: hsl(var(--primary));"
    " color: hsl(var(--primary-foreground));"
    " border-radius: 0.375rem;"
    " box-shadow: 0 1px 3px rgba(0,0,0,0.2);"
)
_INACTIVE_STYLE = (
    "background-color: transparent;"
    " color: hsl(var(--muted-foreground));"
    " border-radius: 0.375rem;"
)

Div(
    Div(
        Button("First", role="tab", cls="px-5 py-2 text-sm font-semibold cursor-pointer transition-all",
               **{":style": f"tab === 'first' ? '{_ACTIVE_STYLE}' : '{_INACTIVE_STYLE}'",
                  "@click": "tab = 'first'"}),
        Button("Second", role="tab", cls="px-5 py-2 text-sm font-semibold cursor-pointer transition-all",
               **{":style": f"tab === 'second' ? '{_ACTIVE_STYLE}' : '{_INACTIVE_STYLE}'",
                  "@click": "tab = 'second'"}),
        role="tablist",
        style="display: inline-flex; gap: 4px; padding: 4px; background-color: hsl(var(--muted)); border-radius: 0.5rem; margin-bottom: 1.5rem;",
    ),
    Div(content_one, role="tabpanel", **{"x-show": "tab === 'first'"}),
    Div(content_two, role="tabpanel", **{"x-show": "tab === 'second'"}),
    **{"x-data": "{ tab: 'first' }", "x-cloak": True},
)
```

**Why `:style` not `:class`:**  Tailwind only compiles classes found in scanned content files at build time. A class added dynamically only inside an Alpine `:class` string won't be in `output.css` unless it also appears in scanned content. Inline styles via `:style` use SKUEL's semantic CSS custom properties, which are always defined.

**Available SKUEL semantic CSS custom properties for tab styling:**
| Property | Value | Visual |
|----------|-------|--------|
| `hsl(var(--primary))` | Dark charcoal (240°, 5.9%, 10%) | Near-black background |
| `hsl(var(--primary-foreground))` | Off-white (0°, 0%, 98%) | Light text on dark |
| `hsl(var(--muted))` | Light gray | Container background |
| `hsl(var(--muted-foreground))` | Medium gray | Inactive tab text |
| `hsl(var(--background))` | White | Page background |

### Dropdown with Click-Outside

```html
<div x-data="{ open: false }" @click.outside="open = false" class="relative">
  <button @click="open = !open" class="p-2 rounded-full hover:bg-base-200">👤</button>
  <div x-show="open" x-transition.origin.top.right
       class="absolute right-0 mt-2 w-48 bg-base-100 rounded-lg shadow-lg z-50">
    <a href="/profile" class="block px-4 py-2 hover:bg-base-200">Profile</a>
    <a href="/logout" class="block px-4 py-2 hover:bg-base-200">Sign out</a>
  </div>
</div>
```

### Conditional Fields (show/hide based on selection)

```html
<div x-data="{ taskType: 'once' }">
  <select x-model="taskType" name="task_type" class="w-full px-3 py-2 border border-base-300 rounded-md bg-base-100">
    <option value="once">One-time</option>
    <option value="recurring">Recurring</option>
  </select>

  <!-- Only show for recurring -->
  <div x-show="taskType === 'recurring'" x-transition>
    <select name="recurrence_pattern" class="w-full px-3 py-2 border border-base-300 rounded-md bg-base-100">
      <option value="daily">Daily</option>
      <option value="weekly">Weekly</option>
    </select>
  </div>
</div>
```

### Touch Swipe

> **No swipe component ships today.** `swipeHandler` was deleted as dead code in
> `327f26623` (2026-03-28) and nothing in the tree binds `touchstart`. This is a
> recipe to write, not a component to mount — inline, since the state does not
> outlive the element. Only register it in `skuel.js` if a second surface needs it.

```html
<div x-data="{
        currentIndex: 0,
        touchStartX: 0,
        totalCards: 3,
        onStart(e) { this.touchStartX = e.changedTouches[0].screenX; },
        onEnd(e) {
            const delta = e.changedTouches[0].screenX - this.touchStartX;
            if (delta < -50 && this.currentIndex < this.totalCards - 1) this.currentIndex++;
            if (delta >  50 && this.currentIndex > 0) this.currentIndex--;
        }
     }"
     @touchstart="onStart($event)"
     @touchend="onEnd($event)">
  <!-- cards, shown by x-show="currentIndex === n" -->
</div>
```

### Event Modifiers

| Modifier | Effect |
|----------|--------|
| `@click.prevent` | preventDefault() |
| `@click.stop` | stopPropagation() |
| `@click.outside` | Only fires outside element |
| `@keydown.enter` | Enter key only |
| `@keydown.escape` | Escape key only |
| `@input.debounce.300ms` | Debounce 300ms |
| `@scroll.throttle.100ms` | Throttle 100ms |

### Transition Modifiers

```html
<!-- Basic -->
<div x-show="open" x-transition>

<!-- Custom -->
<div x-show="open"
     x-transition:enter="transition ease-out duration-300"
     x-transition:enter-start="opacity-0 scale-95"
     x-transition:enter-end="opacity-100 scale-100"
     x-transition:leave="transition ease-in duration-200"
     x-transition:leave-start="opacity-100 scale-100"
     x-transition:leave-end="opacity-0 scale-95">

<!-- Shorthand -->
<div x-show="open" x-transition.origin.top.right>
<div x-show="open" x-transition.scale.95>
<div x-show="open" x-transition.duration.300ms>
```
