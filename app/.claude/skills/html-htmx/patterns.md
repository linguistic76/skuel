# HTMX Common UI Patterns

## Active Search

Real-time search with debouncing:

```html
<search>
  <form action="/search" method="get">
    <input type="search"
           name="q"
           placeholder="Search..."
           hx-get="/search"
           hx-trigger="input changed delay:300ms, search"
           hx-target="#search-results"
           hx-indicator=".search-indicator"
           autocomplete="off">
    <span class="search-indicator htmx-indicator">Searching...</span>
  </form>
</search>

<div id="search-results" aria-live="polite">
  <!-- Results appear here -->
</div>
```

**Server response:**
```html
<ul>
  <li><a href="/products/1">Product 1</a></li>
  <li><a href="/products/2">Product 2</a></li>
</ul>
```

## Infinite Scroll

Load more content as user scrolls:

```html
<div id="feed">
  <article>Post 1</article>
  <article>Post 2</article>
  <article>Post 3</article>

  <!-- Sentinel element: loads next page when visible -->
  <div hx-get="/feed?page=2"
       hx-trigger="revealed"
       hx-swap="outerHTML"
       hx-indicator=".loading">
    <span class="loading htmx-indicator">Loading more...</span>
  </div>
</div>
```

**Server response (page 2):**
```html
<article>Post 4</article>
<article>Post 5</article>
<article>Post 6</article>

<!-- Next sentinel for page 3 -->
<div hx-get="/feed?page=3"
     hx-trigger="revealed"
     hx-swap="outerHTML">
  Loading more...
</div>
```

## Click to Edit

Inline editing pattern:

```html
<!-- View mode -->
<div id="user-name"
     hx-get="/users/123/edit-name"
     hx-trigger="click"
     hx-swap="outerHTML"
     class="editable"
     role="button"
     tabindex="0">
  John Doe
</div>
```

**Edit mode (returned by server):**
```html
<form id="user-name"
      hx-put="/users/123/name"
      hx-swap="outerHTML"
      hx-target="this">
  <input type="text"
         name="name"
         value="John Doe"
         autofocus
         hx-on:keydown="if(event.key==='Escape') htmx.ajax('GET', '/users/123/name', {target: this.closest('form'), swap: 'outerHTML'})">
  <button type="submit">Save</button>
  <button type="button"
          hx-get="/users/123/name"
          hx-target="closest form"
          hx-swap="outerHTML">
    Cancel
  </button>
</form>
```

## Bulk Operations

Select multiple items and perform actions:

```html
<form id="bulk-form">
  <div class="bulk-actions">
    <button type="button"
            hx-post="/items/bulk-delete"
            hx-include="#bulk-form"
            hx-target="#item-list"
            hx-confirm="Delete selected items?"
            hx-disabled-elt="this">
      Delete Selected
    </button>
    <button type="button"
            hx-post="/items/bulk-archive"
            hx-include="#bulk-form"
            hx-target="#item-list">
      Archive Selected
    </button>
  </div>

  <table>
    <thead>
      <tr>
        <th><input type="checkbox" id="select-all" onchange="toggleAll(this)"></th>
        <th>Name</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody id="item-list">
      <tr>
        <td><input type="checkbox" name="ids" value="1"></td>
        <td>Item 1</td>
        <td>Active</td>
      </tr>
      <tr>
        <td><input type="checkbox" name="ids" value="2"></td>
        <td>Item 2</td>
        <td>Active</td>
      </tr>
    </tbody>
  </table>
</form>

<script>
function toggleAll(checkbox) {
  document.querySelectorAll('input[name="ids"]')
    .forEach(cb => cb.checked = checkbox.checked);
}
</script>
```

## Modal Dialog

Server-rendered modal:

```html
<!-- Trigger button -->
<button hx-get="/modals/confirm-delete?id=123"
        hx-target="body"
        hx-swap="beforeend">
  Delete Item
</button>
```

**Server returns modal HTML:**
```html
<dialog id="modal" class="modal">
  <div class="modal-box">
    <h3>Confirm Delete</h3>
    <p>Are you sure you want to delete this item?</p>

    <form method="dialog">
      <button type="button"
              hx-delete="/items/123"
              hx-target="#item-123"
              hx-swap="outerHTML"
              hx-on:htmx:after-request="this.closest('dialog').close(); this.closest('dialog').remove()">
        Delete
      </button>
      <button onclick="this.closest('dialog').close(); this.closest('dialog').remove()">
        Cancel
      </button>
    </form>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button onclick="this.closest('dialog').remove()">close</button>
  </form>
</dialog>

<script>document.getElementById('modal').showModal()</script>
```

## Tabs with Content Loading

Lazy-loaded tab content:

```html
<div class="tabs" role="tablist">
  <button role="tab"
          aria-selected="true"
          hx-get="/tabs/overview"
          hx-target="#tab-content"
          hx-swap="innerHTML"
          class="active">
    Overview
  </button>
  <button role="tab"
          aria-selected="false"
          hx-get="/tabs/details"
          hx-target="#tab-content"
          hx-swap="innerHTML">
    Details
  </button>
  <button role="tab"
          aria-selected="false"
          hx-get="/tabs/settings"
          hx-target="#tab-content"
          hx-swap="innerHTML">
    Settings
  </button>
</div>

<div id="tab-content" role="tabpanel" hx-get="/tabs/overview" hx-trigger="load">
  Loading...
</div>
```

## Cascading Selects

Dependent dropdowns:

```html
<form>
  <label>
    Country
    <select name="country"
            hx-get="/states"
            hx-target="#state-select"
            hx-swap="innerHTML"
            hx-indicator=".loading">
      <option value="">Select country</option>
      <option value="us">United States</option>
      <option value="ca">Canada</option>
    </select>
  </label>

  <label>
    State/Province
    <select name="state" id="state-select">
      <option value="">Select country first</option>
    </select>
  </label>

  <label>
    City
    <select name="city" id="city-select"
            hx-swap-oob="true">
      <option value="">Select state first</option>
    </select>
  </label>
</form>
```

**Server response for states:**
```html
<option value="">Select state</option>
<option value="ca">California</option>
<option value="ny">New York</option>
<option value="tx">Texas</option>

<!-- Out-of-band swap to reset cities -->
<select name="city" id="city-select" hx-swap-oob="true">
  <option value="">Select state first</option>
</select>
```

## Progress Indicator

Long-running operation with progress:

```html
<!-- Start job -->
<button hx-post="/jobs/start"
        hx-target="#job-status"
        hx-swap="outerHTML">
  Start Processing
</button>

<div id="job-status"></div>
```

**Server returns polling element:**
```html
<div id="job-status"
     hx-get="/jobs/123/status"
     hx-trigger="every 1s"
     hx-swap="outerHTML">
  <progress value="25" max="100">25%</progress>
  <p>Processing: 25% complete</p>
</div>
```

**When complete, server returns without polling:**
```html
<div id="job-status">
  <p>Complete!</p>
  <a href="/jobs/123/results">View Results</a>
</div>
```

## Toast Notifications

Server-triggered notifications:

```html
<body hx-on:showToast="showToast(event.detail.message, event.detail.type)">

<!-- Toast container -->
<div id="toast-container" aria-live="polite"></div>

<script>
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  document.getElementById('toast-container').appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}
</script>
```

**Server triggers toast:**
```python
@app.post("/items")
async def create_item(response: Response):
    item = await db.create_item(...)
    response.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "Item created!", "type": "success"}
    })
    return render_item(item)
```

## Form Validation

Server-side validation with inline errors:

```html
<form hx-post="/register"
      hx-target="this"
      hx-swap="outerHTML">

  <div class="field">
    <label for="email">Email</label>
    <input type="email"
           id="email"
           name="email"
           hx-post="/validate/email"
           hx-trigger="blur changed"
           hx-target="next .error"
           hx-swap="innerHTML"
           required>
    <span class="error" aria-live="polite"></span>
  </div>

  <div class="field">
    <label for="password">Password</label>
    <input type="password"
           id="password"
           name="password"
           hx-post="/validate/password"
           hx-trigger="blur changed"
           hx-target="next .error"
           hx-swap="innerHTML"
           minlength="8"
           required>
    <span class="error" aria-live="polite"></span>
  </div>

  <button type="submit">Register</button>
</form>
```

**Validation endpoint returns error or empty:**
```python
@app.post("/validate/email")
async def validate_email(email: str):
    if await db.email_exists(email):
        return "Email already registered"
    return ""
```

## Drag and Drop Reorder

Sortable list with server persistence:

```html
<ul id="sortable-list"
    hx-post="/items/reorder"
    hx-trigger="end"
    hx-include="[name='order']">

  <li draggable="true" data-id="1">
    <input type="hidden" name="order" value="1">
    Item 1
  </li>
  <li draggable="true" data-id="2">
    <input type="hidden" name="order" value="2">
    Item 2
  </li>
  <li draggable="true" data-id="3">
    <input type="hidden" name="order" value="3">
    Item 3
  </li>
</ul>

<script>
// Simple drag-and-drop (or use Sortable.js)
const list = document.getElementById('sortable-list');
list.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', e.target.dataset.id));
list.addEventListener('dragover', e => e.preventDefault());
list.addEventListener('drop', e => {
  e.preventDefault();
  // Reorder logic...
  list.dispatchEvent(new Event('end'));
});
</script>
```

## Optimistic UI

Update UI immediately, rollback on error:

```html
<button id="like-btn"
        hx-post="/posts/123/like"
        hx-swap="outerHTML"
        hx-on:htmx:before-request="this.classList.add('liked'); this.textContent = 'Liked (' + (parseInt(this.dataset.count) + 1) + ')'"
        hx-on:htmx:response-error="this.classList.remove('liked'); this.textContent = 'Like (' + this.dataset.count + ')'"
        data-count="42">
  Like (42)
</button>
```

## File Upload with Progress

```html
<form hx-post="/upload"
      hx-encoding="multipart/form-data"
      hx-target="#upload-result"
      hx-indicator="#upload-progress">

  <input type="file" name="file" required>
  <button type="submit">Upload</button>

  <div id="upload-progress" class="htmx-indicator">
    <progress></progress>
    Uploading...
  </div>
</form>

<div id="upload-result"></div>
```

## Confirmation Pattern

Different confirmation approaches:

```html
<!-- Browser confirm dialog -->
<button hx-delete="/items/123"
        hx-confirm="Are you sure?"
        hx-target="closest tr"
        hx-swap="outerHTML">
  Delete
</button>

<!-- Custom confirm (two-step) -->
<button hx-get="/items/123/confirm-delete"
        hx-target="this"
        hx-swap="outerHTML">
  Delete
</button>

<!-- Server returns confirmation UI -->
<span>
  Are you sure?
  <button hx-delete="/items/123"
          hx-target="closest tr"
          hx-swap="outerHTML">
    Yes, delete
  </button>
  <button hx-get="/items/123/cancel-delete"
          hx-target="closest span"
          hx-swap="outerHTML">
    Cancel
  </button>
</span>
```

## Copy to Clipboard

```html
<div class="copy-container">
  <code id="api-key">sk-abc123xyz</code>
  <button onclick="copyToClipboard()"
          hx-on:click="this.textContent = 'Copied!'; setTimeout(() => this.textContent = 'Copy', 2000)">
    Copy
  </button>
</div>

<script>
function copyToClipboard() {
  navigator.clipboard.writeText(document.getElementById('api-key').textContent);
}
</script>
```

## Keyboard Shortcuts

```html
<body hx-on:keydown="handleShortcut(event)">

<script>
function handleShortcut(event) {
  // Ignore if in input
  if (event.target.matches('input, textarea')) return;

  switch(event.key) {
    case 'n':
      if (event.ctrlKey) {
        event.preventDefault();
        htmx.ajax('GET', '/modals/new-item', {target: 'body', swap: 'beforeend'});
      }
      break;
    case 'Escape':
      document.querySelector('dialog[open]')?.close();
      break;
    case '/':
      event.preventDefault();
      document.querySelector('input[type="search"]')?.focus();
      break;
  }
}
</script>
```

## SPA-like Navigation

Full page navigation with HTMX:

```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://unpkg.com/htmx.org"></script>
</head>
<body hx-boost="true">
  <nav>
    <!-- These links update #main and push URL -->
    <a href="/" hx-target="main" hx-push-url="true">Home</a>
    <a href="/about" hx-target="main" hx-push-url="true">About</a>
    <a href="/contact" hx-target="main" hx-push-url="true">Contact</a>
  </nav>

  <main id="main">
    <!-- Page content loads here -->
  </main>

  <footer>
    <!-- Footer stays constant -->
  </footer>
</body>
</html>
```

**Server detects HTMX and returns fragment:**
```python
@app.get("/about")
async def about(request: Request):
    if request.headers.get("HX-Request"):
        return render_template("about_content.html")  # Fragment only
    return render_template("about_page.html")  # Full page
```

## Error Handling Pattern

Graceful error handling:

```html
<div hx-on:htmx:beforeRequest="this.classList.remove('error')"
     hx-on:htmx:responseError="handleError(event)"
     hx-on:htmx:sendError="handleNetworkError(event)">

  <button hx-get="/api/data" hx-target="#result">Load Data</button>
  <div id="result"></div>
  <div id="error-message" class="error hidden"></div>
</div>

<script>
function handleError(event) {
  const status = event.detail.xhr.status;
  const message = status === 401 ? 'Please log in' :
                  status === 403 ? 'Permission denied' :
                  status === 404 ? 'Not found' :
                  'An error occurred';
  document.getElementById('error-message').textContent = message;
  document.getElementById('error-message').classList.remove('hidden');
}

function handleNetworkError(event) {
  document.getElementById('error-message').textContent = 'Network error. Please try again.';
  document.getElementById('error-message').classList.remove('hidden');
}
</script>
```

## Retry Pattern

Automatic retry on failure:

```html
<div hx-get="/api/unreliable"
     hx-trigger="load"
     hx-target="this"
     hx-on:htmx:sendError="retryRequest(this, event)"
     hx-on:htmx:responseError="retryRequest(this, event)"
     data-retry-count="0"
     data-max-retries="3">
  Loading...
</div>

<script>
function retryRequest(element, event) {
  const count = parseInt(element.dataset.retryCount);
  const max = parseInt(element.dataset.maxRetries);

  if (count < max) {
    element.dataset.retryCount = count + 1;
    setTimeout(() => htmx.trigger(element, 'htmx:load'), 1000 * (count + 1));
  } else {
    element.innerHTML = '<p>Failed to load. <button onclick="resetRetry(this.parentElement.parentElement)">Retry</button></p>';
  }
}

function resetRetry(element) {
  element.dataset.retryCount = 0;
  htmx.trigger(element, 'htmx:load');
}
</script>
```
