---
name: html-htmx
description: Expert guide for semantic HTML and HTMX (HTTP-complete HTML). Use when writing HTML structure, creating accessible markup, building hypermedia-driven UIs, making AJAX requests from HTML, or when the user mentions HTML, HTMX, hypermedia, HTML fragments, hx-* attributes, or server-side rendering with dynamic updates.
allowed-tools: Read, Grep, Glob
---

# HTML + HTMX: HTTP-Complete Hypermedia

## Core Philosophy

> "HTML was designed for hypermedia, but limited to two HTTP verbs. HTMX completes HTML by giving every element access to the full HTTP protocol."

**The HTTP Protocol Gap:**

| What HTTP Provides | What Native HTML Supports |
|--------------------|---------------------------|
| GET, POST, PUT, PATCH, DELETE | GET (links), POST (forms) |
| Any element can request | Only `<a>` and `<form>` |
| Target any element for response | Full page replacement |
| Request on any event | Only click and submit |

**HTMX closes this gap.** It's not a framework—it's HTML with full HTTP access.

## The Hypermedia Mental Model

```
Traditional SPA:                    HTMX/Hypermedia:
┌─────────────────┐                ┌─────────────────┐
│  Client (JS)    │                │  Server         │
│  ┌───────────┐  │                │  ┌───────────┐  │
│  │ State     │  │                │  │ State     │  │
│  │ Logic     │  │                │  │ Logic     │  │
│  │ Templates │  │                │  │ Templates │  │
│  └───────────┘  │                │  └───────────┘  │
│       ↕         │                │       ↓         │
│  JSON ← → API   │                │  HTML Response  │
└─────────────────┘                └─────────────────┘
        ↕                                  ↕
┌─────────────────┐                ┌─────────────────┐
│  Server (API)   │                │  Browser        │
│  Data only      │                │  Renders HTML   │
└─────────────────┘                └─────────────────┘
```

With HTMX, the server returns **HTML fragments**, not JSON. The browser does what browsers do best: render HTML.

## Quick Start

```html
<!-- Load HTMX -->
<script src="https://unpkg.com/htmx.org@1.9.10"></script>

<!-- A button that makes a POST request -->
<button hx-post="/api/like" hx-swap="outerHTML">
  Like (0)
</button>

<!-- Server returns HTML fragment -->
<!-- Response: <button hx-post="/api/like" hx-swap="outerHTML">Like (1)</button> -->
```

## HTTP Verbs in HTML

HTMX gives every element access to all HTTP methods:

### GET - Retrieve Resources

```html
<!-- Link behavior on any element -->
<button hx-get="/users" hx-target="#user-list">
  Load Users
</button>

<!-- Lazy loading -->
<div hx-get="/dashboard/stats" hx-trigger="load">
  Loading stats...
</div>

<!-- Search with query params -->
<input type="search"
       name="q"
       hx-get="/search"
       hx-trigger="keyup changed delay:300ms"
       hx-target="#results">
```

### POST - Create Resources

```html
<!-- Form submission (enhanced) -->
<form hx-post="/users" hx-target="#user-list" hx-swap="beforeend">
  <input name="name" required>
  <button type="submit">Add User</button>
</form>

<!-- Button creates resource -->
<button hx-post="/tasks"
        hx-vals='{"title": "New Task"}'
        hx-target="#task-list"
        hx-swap="beforeend">
  Quick Add Task
</button>
```

### PUT - Replace Resources

```html
<!-- Full resource update -->
<form hx-put="/users/123" hx-target="this" hx-swap="outerHTML">
  <input name="name" value="Current Name">
  <input name="email" value="current@email.com">
  <button type="submit">Update</button>
</form>
```

### PATCH - Partial Update

```html
<!-- Toggle single field -->
<button hx-patch="/tasks/123"
        hx-vals='{"completed": true}'
        hx-swap="outerHTML">
  Mark Complete
</button>

<!-- Inline edit -->
<span hx-patch="/users/123"
      hx-trigger="blur"
      hx-vals="js:{name: event.target.innerText}"
      contenteditable>
  Editable Name
</span>
```

### DELETE - Remove Resources

```html
<!-- Delete with confirmation -->
<button hx-delete="/users/123"
        hx-confirm="Delete this user?"
        hx-target="closest tr"
        hx-swap="outerHTML swap:500ms">
  Delete
</button>

<!-- Self-removing element -->
<div hx-delete="/notifications/456"
     hx-trigger="click"
     hx-swap="outerHTML">
  Dismiss notification
</div>
```

## Request Lifecycle

### 1. Trigger (When to Request)

```html
<!-- Default: click for buttons/links, submit for forms, change for inputs -->
<button hx-get="/data">Click triggers GET</button>

<!-- Explicit triggers -->
<div hx-get="/data" hx-trigger="mouseenter">Hover to load</div>
<div hx-get="/data" hx-trigger="load">Load on page load</div>
<div hx-get="/data" hx-trigger="revealed">Load when visible</div>
<div hx-get="/data" hx-trigger="every 5s">Poll every 5 seconds</div>

<!-- Event modifiers -->
<input hx-get="/search" hx-trigger="keyup changed delay:300ms">
<button hx-get="/data" hx-trigger="click once">Load once only</button>
<form hx-post="/save" hx-trigger="submit throttle:1s">Throttled submit</form>
```

### 2. Request (What to Send)

```html
<!-- Include input values -->
<input name="search" hx-get="/search" hx-trigger="keyup changed delay:300ms">

<!-- Include sibling inputs -->
<div hx-include="[name='filters']">
  <input name="filters" value="active">
  <button hx-get="/items">Filter</button>
</div>

<!-- Add custom values -->
<button hx-post="/action" hx-vals='{"key": "value"}'>With JSON values</button>
<button hx-post="/action" hx-vals="js:{timestamp: Date.now()}">With JS values</button>

<!-- Custom headers -->
<button hx-get="/api" hx-headers='{"X-Custom": "value"}'>With headers</button>
```

### 3. Response (What Server Returns)

The server returns **HTML fragments**, not JSON:

```python
# Server endpoint returns HTML
@app.post("/users")
async def create_user(name: str):
    user = await db.create_user(name)
    # Return HTML fragment, not JSON
    return f"""
    <tr id="user-{user.id}">
        <td>{user.name}</td>
        <td>
            <button hx-delete="/users/{user.id}"
                    hx-target="closest tr"
                    hx-swap="outerHTML">
                Delete
            </button>
        </td>
    </tr>
    """
```

### 4. Swap (Where to Put Response)

```html
<!-- innerHTML (default) - replace contents -->
<div hx-get="/content" hx-swap="innerHTML">Content replaced here</div>

<!-- outerHTML - replace entire element -->
<button hx-get="/new-button" hx-swap="outerHTML">I get replaced</button>

<!-- beforeend - append inside -->
<ul hx-post="/items" hx-swap="beforeend">
  <li>New items added after me</li>
</ul>

<!-- afterend - insert after element -->
<div hx-get="/sibling" hx-swap="afterend">Sibling added after me</div>

<!-- delete - remove target -->
<button hx-delete="/item/1" hx-swap="delete">Removes target</button>

<!-- none - no swap (for side effects) -->
<button hx-post="/analytics" hx-swap="none">Track only</button>
```

### 5. Target (What Element to Update)

```html
<!-- Target by CSS selector -->
<button hx-get="/content" hx-target="#content-area">Load into #content-area</button>

<!-- Target relative to element -->
<button hx-delete="/item" hx-target="closest tr">Remove parent row</button>
<button hx-get="/data" hx-target="next .preview">Update next sibling</button>
<button hx-get="/data" hx-target="previous div">Update previous sibling</button>

<!-- Target this element -->
<div hx-get="/self-update" hx-target="this">I update myself</div>
```

## HTTP Headers (HTMX-Specific)

### Request Headers (Browser → Server)

| Header | Purpose |
|--------|---------|
| `HX-Request: true` | Identifies HTMX request |
| `HX-Target` | ID of target element |
| `HX-Trigger` | ID of triggered element |
| `HX-Trigger-Name` | Name of triggered element |
| `HX-Current-URL` | Current browser URL |
| `HX-Prompt` | User response from hx-prompt |

```python
# Server can detect HTMX requests
@app.get("/users")
async def get_users(request):
    if request.headers.get("HX-Request"):
        # Return fragment for HTMX
        return render_fragment("users_list.html", users=users)
    else:
        # Return full page for regular request
        return render_page("users.html", users=users)
```

### Response Headers (Server → Browser)

| Header | Purpose |
|--------|---------|
| `HX-Redirect` | Client-side redirect |
| `HX-Refresh: true` | Full page refresh |
| `HX-Retarget` | Change target element |
| `HX-Reswap` | Change swap method |
| `HX-Trigger` | Trigger client events |
| `HX-Push-Url` | Push URL to history |

```python
# Redirect after action
@app.post("/login")
async def login(response):
    response.headers["HX-Redirect"] = "/dashboard"
    return ""

# Trigger client event
@app.post("/save")
async def save(response):
    response.headers["HX-Trigger"] = "saved"  # or JSON: '{"saved": {"id": 123}}'
    return "<div>Saved!</div>"
```

## Semantic HTML Foundation

HTMX enhances HTML—it doesn't replace semantic structure:

### Document Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Page Title</title>
</head>
<body>
  <header>
    <nav aria-label="Main navigation">
      <ul>
        <li><a href="/" hx-get="/" hx-target="main" hx-push-url="true">Home</a></li>
        <li><a href="/about" hx-get="/about" hx-target="main" hx-push-url="true">About</a></li>
      </ul>
    </nav>
  </header>

  <main id="main">
    <!-- Page content, HTMX updates here -->
  </main>

  <footer>
    <p>&copy; 2026 Company</p>
  </footer>
</body>
</html>
```

### Sectioning Elements

```html
<article>    <!-- Self-contained content (blog post, comment, widget) -->
<section>    <!-- Thematic grouping with heading -->
<nav>        <!-- Navigation links -->
<aside>      <!-- Tangentially related content -->
<header>     <!-- Introductory content -->
<footer>     <!-- Footer content -->
<main>       <!-- Main content (one per page) -->
```

### Content Elements

```html
<h1> - <h6>  <!-- Headings (hierarchy matters for accessibility) -->
<p>          <!-- Paragraph -->
<ul>, <ol>   <!-- Lists -->
<dl>         <!-- Description list (term/definition pairs) -->
<figure>     <!-- Self-contained content with caption -->
<figcaption> <!-- Caption for figure -->
<blockquote> <!-- Extended quotation -->
<pre>        <!-- Preformatted text -->
<code>       <!-- Inline code -->
```

### Interactive Elements

```html
<a href="">           <!-- Links (GET navigation) -->
<button>              <!-- Actions (click handlers) -->
<form>                <!-- Data submission (POST/GET) -->
<input>               <!-- User input -->
<select>              <!-- Dropdown selection -->
<textarea>            <!-- Multi-line text -->
<details>/<summary>   <!-- Expandable content (no JS needed) -->
<dialog>              <!-- Modal dialog (use with showModal()) -->
```

### Tables (Semantic)

```html
<table>
  <caption>User List</caption>
  <thead>
    <tr>
      <th scope="col">Name</th>
      <th scope="col">Email</th>
      <th scope="col">Actions</th>
    </tr>
  </thead>
  <tbody hx-target="closest tr" hx-swap="outerHTML">
    <tr id="user-1">
      <td>Alice</td>
      <td>alice@example.com</td>
      <td>
        <button hx-delete="/users/1" hx-confirm="Delete Alice?">Delete</button>
      </td>
    </tr>
  </tbody>
</table>
```

## Common HTMX Patterns

### Active Search

```html
<input type="search"
       name="q"
       hx-get="/search"
       hx-trigger="input changed delay:300ms, search"
       hx-target="#results"
       hx-indicator=".htmx-indicator"
       placeholder="Search...">

<span class="htmx-indicator">Searching...</span>
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
  <span>Click to edit: John Doe</span>
</div>

<!-- Edit mode (returned by server) -->
<form hx-put="/users/1" hx-swap="outerHTML">
  <input name="name" value="John Doe">
  <button type="submit">Save</button>
  <button hx-get="/users/1" hx-swap="outerHTML">Cancel</button>
</form>
```

### Optimistic UI

```html
<button hx-post="/like"
        hx-swap="outerHTML"
        hx-on::before-request="this.innerText = 'Liked!'"
        hx-on::after-request="if(!event.detail.successful) this.innerText = 'Like'">
  Like
</button>
```

### Form Validation (Server-Side)

```html
<form hx-post="/register" hx-target="this" hx-swap="outerHTML">
  <label>
    Email
    <input type="email" name="email"
           hx-post="/validate/email"
           hx-trigger="blur"
           hx-target="next .error">
    <span class="error"></span>
  </label>
  <button type="submit">Register</button>
</form>

<!-- Server returns validation error as HTML -->
<!-- Response: <span class="error">Email already taken</span> -->
```

### Bulk Actions

```html
<form hx-post="/bulk-delete" hx-target="#items" hx-swap="innerHTML">
  <button type="submit">Delete Selected</button>

  <div id="items">
    <label>
      <input type="checkbox" name="ids" value="1"> Item 1
    </label>
    <label>
      <input type="checkbox" name="ids" value="2"> Item 2
    </label>
  </div>
</form>
```

## Loading States

```html
<!-- Show indicator during request -->
<button hx-get="/slow-data" hx-indicator="#spinner">
  Load Data
</button>
<span id="spinner" class="htmx-indicator">Loading...</span>

<!-- CSS for indicator -->
<style>
  .htmx-indicator { display: none; }
  .htmx-request .htmx-indicator { display: inline; }
  .htmx-request.htmx-indicator { display: inline; }
</style>

<!-- Disable during request -->
<button hx-post="/save" hx-disabled-elt="this">
  Save (disables while loading)
</button>
```

## Events

HTMX fires events throughout the request lifecycle:

```html
<!-- Declarative event handling -->
<div hx-on:htmx:after-swap="console.log('Swapped!')">

<!-- Listen for custom events from HX-Trigger header -->
<body hx-on:saved="alert('Data saved!')">
```

| Event | When |
|-------|------|
| `htmx:configRequest` | Before request, can modify |
| `htmx:beforeRequest` | Request about to be made |
| `htmx:afterRequest` | After request completes |
| `htmx:beforeSwap` | Before DOM swap |
| `htmx:afterSwap` | After DOM swap |
| `htmx:afterSettle` | After settle (CSS transitions) |
| `htmx:responseError` | Server error response |
| `htmx:sendError` | Network error |

## Accessibility with HTMX

### Announce Dynamic Updates

```html
<div aria-live="polite" id="results">
  <!-- HTMX updates here get announced to screen readers -->
</div>

<button hx-get="/search" hx-target="#results">Search</button>
```

### Focus Management

```html
<!-- Focus first input after swap -->
<form hx-post="/step1"
      hx-target="#wizard"
      hx-on:htmx:after-swap="this.querySelector('input')?.focus()">
```

### Preserve Focus During Updates

```html
<input hx-get="/suggest"
       hx-trigger="keyup changed delay:300ms"
       hx-target="#suggestions"
       hx-preserve>  <!-- Keeps focus during parent swap -->
```

## Best Practices

### 1. Progressive Enhancement

```html
<!-- Works without JS, enhanced with HTMX -->
<form action="/search" method="get"
      hx-get="/search"
      hx-target="#results"
      hx-push-url="true">
  <input name="q" type="search">
  <button type="submit">Search</button>
</form>
```

### 2. Use Semantic Elements

```html
<!-- GOOD: Semantic + HTMX -->
<nav>
  <a href="/page" hx-get="/page" hx-target="main">Page</a>
</nav>

<!-- AVOID: Div soup -->
<div onclick="load()">Page</div>
```

### 3. Server Returns HTML, Not JSON

```python
# GOOD: Return HTML fragment
@app.get("/users/{id}")
async def get_user(id: int):
    user = await db.get_user(id)
    return f"<div class='user'>{user.name}</div>"

# AVOID: Return JSON for HTMX to process
@app.get("/users/{id}")
async def get_user(id: int):
    return {"name": user.name}  # HTMX can't use this directly
```

### 4. Co-locate hx-target with hx-swap

```html
<!-- GOOD: Clear where response goes -->
<button hx-get="/data" hx-target="#output" hx-swap="innerHTML">Load</button>

<!-- CONFUSING: Target inherited from parent, swap unclear -->
<div hx-target="#output">
  <button hx-get="/data">Load</button>  <!-- Where does it go? -->
</div>
```

## Additional Resources

- [semantic-html.md](semantic-html.md) - Complete semantic HTML reference
- [htmx-http-patterns.md](htmx-http-patterns.md) - HTTP request/response patterns
- [patterns.md](patterns.md) - Common HTMX UI patterns

## Related Skills

- **[js-alpine](../js-alpine/SKILL.md)** - Client-side state complementing HTMX server communication
- **[fasthtml](../fasthtml/SKILL.md)** - Python framework using HTMX patterns
- **[monsterui](../monsterui/SKILL.md)** - Components with HTMX attributes

## Foundation

This skill has no prerequisites. It is a foundational pattern.

## UX Consistency

**CRITICAL:** Before writing HTML structure, review:
- [ux-consistency-checklist.md](../ux-consistency-checklist.md) - Pre-commit UX verification

**Key Rules:**
1. Use semantic HTML elements
2. Ensure accessibility (ARIA, keyboard nav)
3. HTMX updates use proper target/swap patterns
4. Progressive enhancement (works without JS)

## See Also

- HTMX Docs: https://htmx.org/docs/
- Hypermedia Systems Book: https://hypermedia.systems/
