# Alpine.js + HTMX Integration Patterns

How Alpine.js and HTMX work together in SKUEL's architecture.

## Philosophy

> "Alpine owns the client, HTMX owns the server."

| Concern | Owner | Why |
|---------|-------|-----|
| **UI State** | Alpine | Instant feedback, no round-trip |
| **Data Persistence** | HTMX | Server is source of truth |
| **Animations** | Alpine | Client-side performance |
| **Navigation** | HTMX | URL history, SEO |
| **Form Validation** | Alpine | Immediate feedback |
| **Form Submission** | HTMX | Server-side processing |
| **Loading States** | Both | Alpine shows, HTMX triggers |

## Event Bridge

Alpine and HTMX communicate through DOM events.

### HTMX Events Alpine Can Listen To

```html
<!-- Loading state -->
<div x-data="{ loading: false }"
     x-on:htmx:before-request="loading = true"
     x-on:htmx:after-request="loading = false">
    <button hx-get="/api/data" hx-target="#result">
        <span x-show="!loading">Load</span>
        <span x-show="loading">Loading...</span>
    </button>
    <div id="result"></div>
</div>
```

| HTMX Event | When It Fires |
|------------|---------------|
| `htmx:beforeRequest` | Before request starts |
| `htmx:afterRequest` | After request completes (success or error) |
| `htmx:beforeSwap` | Before content is swapped |
| `htmx:afterSwap` | After content is swapped |
| `htmx:afterSettle` | After CSS transitions complete |
| `htmx:responseError` | On HTTP error response |
| `htmx:sendError` | On network error |
| `htmx:confirm` | Before confirmation dialogs |

### Alpine Events HTMX Can Trigger

Use server response headers to trigger Alpine updates:

```python
# Server-side (FastHTML)
@app.post("/api/save")
async def save_item(response):
    # Trigger Alpine event via HTMX header
    response.headers["HX-Trigger"] = "itemSaved"
    return "<div>Saved!</div>"
```

```html
<!-- Client-side -->
<div x-data="{ saved: false }"
     x-on:item-saved.window="saved = true; setTimeout(() => saved = false, 3000)">
    <button hx-post="/api/save">Save</button>
    <span x-show="saved" x-transition class="text-green-500">Saved!</span>
</div>
```

### With Event Data

```python
# Server sends data with event
response.headers["HX-Trigger"] = json.dumps({
    "itemSaved": {"id": 123, "name": "New Item"}
})
```

```html
<div x-on:item-saved.window="handleSaved($event.detail)">
```

## Common Patterns

### 1. Loading Button

Show loading state while HTMX request is in progress.

```html
<div x-data="{ loading: false }"
     @htmx:before-request="loading = true"
     @htmx:after-request="loading = false">
    <button hx-post="/api/action"
            hx-target="#result"
            :disabled="loading"
            :class="{ 'opacity-50': loading }">
        <span x-show="!loading">Submit</span>
        <span x-show="loading" class="flex items-center gap-2">
            <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
            Loading...
        </span>
    </button>
</div>
```

### 2. Optimistic UI

Update UI immediately, rollback on error.

```html
<div x-data="{ liked: false, error: false }"
     @htmx:before-request="liked = !liked; error = false"
     @htmx:response-error="liked = !liked; error = true">

    <button hx-post="/api/like"
            hx-swap="none"
            :class="{ 'text-red-500': liked }">
        <span x-text="liked ? '❤️ Liked' : '🤍 Like'"></span>
    </button>

    <span x-show="error" x-transition class="text-red-500">
        Failed to update. Try again.
    </span>
</div>
```

### 3. Form with Validation

Alpine validates, HTMX submits.

```html
<form hx-post="/api/register"
      hx-target="#result"
      x-data="{
          email: '',
          password: '',
          get emailValid() { return /^[^@]+@[^@]+\.[^@]+$/.test(this.email) },
          get passwordValid() { return this.password.length >= 8 },
          get formValid() { return this.emailValid && this.passwordValid }
      }">

    <div class="mb-4">
        <input type="email"
               name="email"
               x-model="email"
               placeholder="Email"
               class="border rounded p-2 w-full">
        <p x-show="email && !emailValid" class="text-red-500 text-sm">
            Please enter a valid email
        </p>
    </div>

    <div class="mb-4">
        <input type="password"
               name="password"
               x-model="password"
               placeholder="Password (min 8 chars)"
               class="border rounded p-2 w-full">
        <p x-show="password && !passwordValid" class="text-red-500 text-sm">
            Password must be at least 8 characters
        </p>
    </div>

    <button type="submit"
            :disabled="!formValid"
            :class="{ 'opacity-50 cursor-not-allowed': !formValid }"
            class="btn btn-primary">
        Register
    </button>
</form>
<div id="result"></div>
```

### 4. Modal with Dynamic Content

Alpine controls open/close, HTMX loads content.

```html
<div x-data="{ open: false, loading: false }">
    <!-- Trigger -->
    <button @click="open = true; loading = true"
            hx-get="/api/modal-content"
            hx-target="#modal-body"
            hx-trigger="click">
        Open Modal
    </button>

    <!-- Modal backdrop -->
    <div x-show="open"
         x-transition:enter="ease-out duration-300"
         x-transition:enter-start="opacity-0"
         x-transition:enter-end="opacity-100"
         x-transition:leave="ease-in duration-200"
         x-transition:leave-start="opacity-100"
         x-transition:leave-end="opacity-0"
         @click="open = false"
         @htmx:after-swap="loading = false"
         class="fixed inset-0 bg-black/50">

        <!-- Modal content -->
        <div @click.stop
             class="bg-white rounded-lg p-6 max-w-md mx-auto mt-20">

            <!-- Close button -->
            <button @click="open = false" class="float-right">&times;</button>

            <!-- Loading state -->
            <div x-show="loading" class="text-center py-8">
                Loading...
            </div>

            <!-- Content loaded by HTMX -->
            <div id="modal-body" x-show="!loading"></div>
        </div>
    </div>
</div>
```

### 5. Tabs with Lazy Loading

Alpine manages active tab, HTMX loads content on first view.

```html
<div x-data="{ activeTab: 'overview', loaded: { overview: true } }">
    <!-- Tab buttons -->
    <nav class="flex border-b">
        <button @click="activeTab = 'overview'"
                :class="{ 'border-b-2 border-blue-500': activeTab === 'overview' }"
                class="px-4 py-2">
            Overview
        </button>
        <button @click="activeTab = 'details'; if (!loaded.details) { loaded.details = true }"
                :class="{ 'border-b-2 border-blue-500': activeTab === 'details' }"
                hx-get="/api/details"
                hx-target="#details-content"
                hx-trigger="click once"
                class="px-4 py-2">
            Details
        </button>
        <button @click="activeTab = 'history'; if (!loaded.history) { loaded.history = true }"
                :class="{ 'border-b-2 border-blue-500': activeTab === 'history' }"
                hx-get="/api/history"
                hx-target="#history-content"
                hx-trigger="click once"
                class="px-4 py-2">
            History
        </button>
    </nav>

    <!-- Tab panels -->
    <div x-show="activeTab === 'overview'" class="p-4">
        Overview content (already loaded)
    </div>
    <div x-show="activeTab === 'details'" class="p-4">
        <div id="details-content">Loading details...</div>
    </div>
    <div x-show="activeTab === 'history'" class="p-4">
        <div id="history-content">Loading history...</div>
    </div>
</div>
```

### 6. Infinite Scroll with Loading State

```html
<div x-data="{ loading: false, page: 1, hasMore: true }"
     @htmx:before-request="loading = true"
     @htmx:after-request="loading = false; page++">

    <div id="items">
        <!-- Initial items -->
    </div>

    <!-- Load more trigger -->
    <div x-show="hasMore"
         hx-get="/api/items"
         hx-target="#items"
         hx-swap="beforeend"
         hx-trigger="revealed"
         hx-vals="js:{ page: page }"
         @htmx:after-request="hasMore = $event.detail.xhr.getResponseHeader('X-Has-More') === 'true'">
        <span x-show="loading">Loading more...</span>
    </div>

    <p x-show="!hasMore" class="text-center text-gray-500">
        No more items
    </p>
</div>
```

### 7. Search with Debounce

```html
<div x-data="{ query: '', searching: false }"
     @htmx:before-request="searching = true"
     @htmx:after-request="searching = false">

    <div class="relative">
        <input type="search"
               x-model="query"
               name="q"
               placeholder="Search..."
               hx-get="/api/search"
               hx-target="#results"
               hx-trigger="input changed delay:300ms, search"
               class="w-full border rounded p-2 pr-10">

        <!-- Loading indicator -->
        <span x-show="searching"
              class="absolute right-3 top-2.5 text-gray-400">
            ⟳
        </span>
    </div>

    <!-- Results -->
    <div id="results" class="mt-4"></div>
</div>
```

### 8. Confirmation Dialog

Alpine shows dialog, HTMX executes on confirm.

```html
<div x-data="{ showConfirm: false, itemToDelete: null }">
    <!-- Delete buttons -->
    <button @click="showConfirm = true; itemToDelete = 123"
            class="text-red-500">
        Delete Item
    </button>

    <!-- Confirmation modal -->
    <div x-show="showConfirm"
         x-transition
         class="fixed inset-0 bg-black/50 flex items-center justify-center"
         @click="showConfirm = false">

        <div @click.stop class="bg-white rounded-lg p-6">
            <h3 class="text-lg font-bold mb-4">Confirm Delete</h3>
            <p>Are you sure you want to delete this item?</p>

            <div class="flex gap-4 mt-4">
                <button @click="showConfirm = false"
                        class="btn">
                    Cancel
                </button>
                <button hx-delete="/api/items"
                        :hx-vals="JSON.stringify({ id: itemToDelete })"
                        hx-target="#items"
                        @click="showConfirm = false"
                        class="btn btn-danger">
                    Delete
                </button>
            </div>
        </div>
    </div>
</div>
```

## Re-initializing Alpine After HTMX Swap

When HTMX swaps content containing Alpine components, you may need to reinitialize them.

### Option 1: Use htmx:afterSwap Event

```javascript
document.body.addEventListener('htmx:afterSwap', (event) => {
    // Initialize Alpine on new content
    Alpine.initTree(event.detail.target)
})
```

### Option 2: Use hx-on Attribute

```html
<div hx-get="/api/content"
     hx-target="#container"
     hx-on::after-swap="Alpine.initTree(document.getElementById('container'))">
    Load Content
</div>
```

### Option 3: Alpine x-init in Swapped Content

Ensure swapped content has its own `x-data` and `x-init`:

```html
<!-- Server returns this -->
<div x-data="{ loaded: false }" x-init="loaded = true">
    <span x-show="loaded">Content loaded!</span>
</div>
```

## Preserving Alpine State Across Swaps

### Use hx-preserve

```html
<input id="search-input"
       hx-preserve
       x-data="{ value: '' }"
       x-model="value">
```

### Store State Outside Swapped Area

```html
<div x-data="{ filter: 'all' }">
    <!-- Filter buttons stay outside swap area -->
    <div class="filters">
        <button @click="filter = 'all'"
                hx-get="/api/items?filter=all"
                hx-target="#items">
            All
        </button>
        <button @click="filter = 'active'"
                hx-get="/api/items?filter=active"
                hx-target="#items">
            Active
        </button>
    </div>

    <!-- Only this gets swapped -->
    <div id="items">
        <!-- Items loaded by HTMX -->
    </div>
</div>
```

## Anti-Patterns

### 1. Don't Fetch Data with Alpine

```html
<!-- WRONG: Alpine fetching data -->
<div x-data x-init="fetch('/api/data').then(...)">

<!-- RIGHT: HTMX fetches, Alpine enhances -->
<div hx-get="/api/data" hx-trigger="load">
```

### 2. Don't Use Both for Same Toggle

```html
<!-- WRONG: Both controlling visibility -->
<div x-show="show" hx-get="/content" hx-swap="innerHTML">

<!-- RIGHT: Clear separation -->
<div x-data="{ open: false }">
    <button @click="open = true"
            hx-get="/content"
            hx-target="#modal-content">
        Open
    </button>
    <div x-show="open">
        <div id="modal-content">Loading...</div>
    </div>
</div>
```

### 3. Don't Duplicate State

```html
<!-- WRONG: State in both places -->
<div x-data="{ items: [] }"
     hx-get="/api/items"
     hx-trigger="load">
    <!-- items from Alpine AND items from HTMX -->
</div>

<!-- RIGHT: Single source of truth -->
<div hx-get="/api/items" hx-trigger="load">
    <!-- HTMX provides items as HTML -->
</div>
```

## Summary

| Task | Use |
|------|-----|
| Show/hide based on user action | Alpine (`x-show`) |
| Load data from server | HTMX (`hx-get`) |
| Form validation feedback | Alpine (`x-model` + computed) |
| Form submission | HTMX (`hx-post`) |
| Animations | Alpine (`x-transition`) |
| Loading states | Both (Alpine shows, HTMX triggers) |
| Navigate pages | HTMX (`hx-push-url`) |
| Dropdown/modal open/close | Alpine (`x-data`, `x-show`) |
| Dynamic list rendering | HTMX (server renders HTML) |
| Real-time updates | HTMX (SSE or polling) |
