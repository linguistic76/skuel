# HTMX HTTP Patterns Reference

## The HTTP Protocol in HTML

### Native HTML HTTP Support

| Element | Method | Trigger | Target |
|---------|--------|---------|--------|
| `<a href="">` | GET | click | Full page |
| `<form method="get">` | GET | submit | Full page |
| `<form method="post">` | POST | submit | Full page |

### HTMX HTTP Support

| Attribute | Method | Any Element | Any Trigger | Any Target |
|-----------|--------|-------------|-------------|------------|
| `hx-get` | GET | Yes | Yes | Yes |
| `hx-post` | POST | Yes | Yes | Yes |
| `hx-put` | PUT | Yes | Yes | Yes |
| `hx-patch` | PATCH | Yes | Yes | Yes |
| `hx-delete` | DELETE | Yes | Yes | Yes |

## HTTP Methods: Semantic Usage

### GET - Safe, Idempotent Read

**HTTP Semantics:** Retrieve representation without side effects. Cacheable.

```html
<!-- Navigation (replaces full page) -->
<a href="/products"
   hx-get="/products"
   hx-target="main"
   hx-push-url="true">
  Products
</a>

<!-- Load data fragment -->
<button hx-get="/api/stats" hx-target="#stats">
  Load Statistics
</button>

<!-- Lazy load on scroll -->
<div hx-get="/api/comments"
     hx-trigger="revealed"
     hx-swap="innerHTML">
  Loading comments...
</div>

<!-- Poll for updates -->
<div hx-get="/api/notifications"
     hx-trigger="every 30s"
     hx-swap="innerHTML">
</div>

<!-- Search with query string -->
<input type="search"
       name="q"
       hx-get="/search"
       hx-trigger="input changed delay:300ms"
       hx-target="#results"
       hx-push-url="true">
```

**Server Response:**
```python
@app.get("/api/stats")
async def get_stats():
    stats = await db.get_stats()
    return f"""
    <dl>
        <dt>Users</dt><dd>{stats.users}</dd>
        <dt>Orders</dt><dd>{stats.orders}</dd>
    </dl>
    """
```

### POST - Create New Resource

**HTTP Semantics:** Submit data to create new resource. Not idempotent.

```html
<!-- Form submission -->
<form hx-post="/api/users"
      hx-target="#user-list"
      hx-swap="beforeend">
  <input name="name" required>
  <input name="email" type="email" required>
  <button type="submit">Create User</button>
</form>

<!-- Quick action button -->
<button hx-post="/api/tasks"
        hx-vals='{"title": "Quick Task", "status": "pending"}'
        hx-target="#task-list"
        hx-swap="beforeend">
  Add Quick Task
</button>

<!-- File upload -->
<form hx-post="/api/upload"
      hx-encoding="multipart/form-data"
      hx-target="#upload-status">
  <input type="file" name="file">
  <button type="submit">Upload</button>
</form>
```

**Server Response:**
```python
@app.post("/api/users")
async def create_user(name: str, email: str):
    user = await db.create_user(name=name, email=email)
    # Return NEW element to be appended
    return f"""
    <tr id="user-{user.id}">
        <td>{user.name}</td>
        <td>{user.email}</td>
        <td>
            <button hx-delete="/api/users/{user.id}"
                    hx-target="closest tr"
                    hx-swap="outerHTML">Delete</button>
        </td>
    </tr>
    """
```

### PUT - Replace Entire Resource

**HTTP Semantics:** Replace resource entirely at URL. Idempotent.

```html
<!-- Full form update -->
<form hx-put="/api/users/123"
      hx-target="this"
      hx-swap="outerHTML">
  <input name="name" value="Current Name" required>
  <input name="email" value="current@email.com" required>
  <input name="phone" value="+1555555555">
  <button type="submit">Save All Changes</button>
  <button hx-get="/api/users/123" hx-target="closest form" hx-swap="outerHTML">
    Cancel
  </button>
</form>

<!-- Replace entire document section -->
<article hx-put="/api/posts/456"
         hx-trigger="submit from:form"
         hx-target="this"
         hx-swap="outerHTML">
  <form>
    <input name="title" value="Post Title">
    <textarea name="content">Post content...</textarea>
    <button type="submit">Update Post</button>
  </form>
</article>
```

**Server Response:**
```python
@app.put("/api/users/{id}")
async def replace_user(id: int, name: str, email: str, phone: str):
    user = await db.replace_user(id, name=name, email=email, phone=phone)
    # Return COMPLETE updated element
    return f"""
    <form hx-put="/api/users/{id}" hx-target="this" hx-swap="outerHTML">
        <input name="name" value="{user.name}" required>
        <input name="email" value="{user.email}" required>
        <input name="phone" value="{user.phone}">
        <button type="submit">Save All Changes</button>
    </form>
    """
```

### PATCH - Partial Update

**HTTP Semantics:** Modify part of resource. May or may not be idempotent.

```html
<!-- Toggle single field -->
<button hx-patch="/api/tasks/789"
        hx-vals='{"completed": true}'
        hx-target="closest li"
        hx-swap="outerHTML">
  Complete Task
</button>

<!-- Inline edit single field -->
<span hx-patch="/api/users/123"
      hx-trigger="blur"
      hx-target="this"
      hx-swap="outerHTML"
      hx-vals="js:{name: this.innerText}"
      contenteditable>
  John Doe
</span>

<!-- Update status only -->
<select name="status"
        hx-patch="/api/orders/456"
        hx-trigger="change"
        hx-target="closest tr"
        hx-swap="outerHTML">
  <option value="pending">Pending</option>
  <option value="processing" selected>Processing</option>
  <option value="shipped">Shipped</option>
</select>

<!-- Increment counter -->
<button hx-patch="/api/posts/123/like"
        hx-swap="outerHTML">
  Like (42)
</button>
```

**Server Response:**
```python
@app.patch("/api/tasks/{id}")
async def patch_task(id: int, completed: bool = None, title: str = None):
    # Only update provided fields
    updates = {}
    if completed is not None:
        updates["completed"] = completed
    if title is not None:
        updates["title"] = title

    task = await db.patch_task(id, **updates)
    return render_task_item(task)
```

### DELETE - Remove Resource

**HTTP Semantics:** Remove resource at URL. Idempotent.

```html
<!-- Delete with confirmation -->
<button hx-delete="/api/users/123"
        hx-confirm="Are you sure you want to delete this user?"
        hx-target="closest tr"
        hx-swap="outerHTML swap:500ms">
  Delete
</button>

<!-- Self-removing element -->
<div class="notification"
     hx-delete="/api/notifications/456"
     hx-trigger="click"
     hx-swap="outerHTML swap:300ms">
  Click to dismiss
</div>

<!-- Delete with undo -->
<tr id="item-789">
  <td>Item Name</td>
  <td>
    <button hx-delete="/api/items/789"
            hx-target="closest tr"
            hx-swap="outerHTML">
      Delete
    </button>
  </td>
</tr>
```

**Server Response:**
```python
@app.delete("/api/users/{id}")
async def delete_user(id: int):
    await db.delete_user(id)
    # Option 1: Return empty (element removed via hx-swap="outerHTML")
    return ""

    # Option 2: Return undo message
    return f"""
    <tr class="deleted">
        <td colspan="3">
            User deleted.
            <button hx-post="/api/users/{id}/restore"
                    hx-target="closest tr"
                    hx-swap="outerHTML">Undo</button>
        </td>
    </tr>
    """
```

## HTTP Headers

### Request Headers (Client → Server)

HTMX automatically includes these headers:

| Header | Value | Purpose |
|--------|-------|---------|
| `HX-Request` | `true` | Identifies HTMX request |
| `HX-Target` | Element ID | Target element |
| `HX-Trigger` | Element ID | Element that triggered request |
| `HX-Trigger-Name` | Element name | Name attribute of trigger |
| `HX-Current-URL` | URL | Current page URL |
| `HX-Prompt` | User input | Response from `hx-prompt` |
| `HX-Boosted` | `true` | Request was boosted |

**Server detection pattern:**
```python
from fastapi import Request

@app.get("/products")
async def get_products(request: Request):
    is_htmx = request.headers.get("HX-Request") == "true"

    if is_htmx:
        # Return HTML fragment
        return render_template("products_list.html", products=products)
    else:
        # Return full page
        return render_template("products_page.html", products=products)
```

**Adding custom headers:**
```html
<button hx-get="/api/data"
        hx-headers='{"X-Custom-Header": "value", "Authorization": "Bearer token"}'>
  Load
</button>
```

### Response Headers (Server → Client)

| Header | Purpose | Example |
|--------|---------|---------|
| `HX-Location` | Client-side redirect with options | `{"path": "/new", "target": "#main"}` |
| `HX-Push-Url` | Push URL to browser history | `/products/123` or `false` |
| `HX-Redirect` | Full page redirect | `/login` |
| `HX-Refresh` | Full page refresh | `true` |
| `HX-Replace-Url` | Replace current URL | `/products/123` |
| `HX-Reswap` | Override swap method | `innerHTML` |
| `HX-Retarget` | Override target element | `#other-element` |
| `HX-Reselect` | Select subset of response | `.items` |
| `HX-Trigger` | Trigger client events | `myEvent` or `{"event": {"data": 1}}` |
| `HX-Trigger-After-Settle` | Trigger after settle | Same as HX-Trigger |
| `HX-Trigger-After-Swap` | Trigger after swap | Same as HX-Trigger |

**Redirect after action:**
```python
from fastapi import Response

@app.post("/login")
async def login(response: Response, email: str, password: str):
    if authenticate(email, password):
        response.headers["HX-Redirect"] = "/dashboard"
        return ""
    else:
        return "<p class='error'>Invalid credentials</p>"
```

**Trigger client event:**
```python
@app.post("/api/save")
async def save(response: Response):
    await db.save(...)
    response.headers["HX-Trigger"] = "dataSaved"
    return "<p>Saved!</p>"
```

```html
<!-- Listen for server-triggered event -->
<body hx-on:dataSaved="showToast('Data saved successfully')">
```

**Multiple events with data:**
```python
response.headers["HX-Trigger"] = json.dumps({
    "itemCreated": {"id": 123, "name": "New Item"},
    "statsUpdated": None
})
```

## HTTP Status Codes

### Success Codes

| Code | HTMX Behavior | Use Case |
|------|---------------|----------|
| `200 OK` | Swap response | Normal response |
| `201 Created` | Swap response | Resource created |
| `204 No Content` | No swap (empty) | Action completed, no UI change |

### Redirect Codes

| Code | HTMX Behavior | Use Case |
|------|---------------|----------|
| `301/302/303/307/308` | Follow redirect via AJAX | Server redirects |

### Client Error Codes

| Code | HTMX Behavior | Use Case |
|------|---------------|----------|
| `400 Bad Request` | Triggers `htmx:responseError` | Validation error |
| `401 Unauthorized` | Triggers `htmx:responseError` | Not logged in |
| `403 Forbidden` | Triggers `htmx:responseError` | Permission denied |
| `404 Not Found` | Triggers `htmx:responseError` | Resource not found |
| `422 Unprocessable Entity` | **Swaps by default** | Validation with UI |

**422 pattern (validation errors as HTML):**
```python
@app.post("/api/users")
async def create_user(response: Response, name: str):
    if not name:
        response.status_code = 422
        return '<input name="name" class="error"><span class="error">Name required</span>'

    user = await db.create_user(name)
    return render_user(user)
```

### Server Error Codes

| Code | HTMX Behavior | Use Case |
|------|---------------|----------|
| `500 Internal Server Error` | Triggers `htmx:responseError` | Server error |
| `503 Service Unavailable` | Triggers `htmx:responseError` | Maintenance |

**Error handling:**
```html
<body hx-on:htmx:responseError="showError(event.detail.xhr.status)">
```

## Content Types

### Request Content Type

HTMX uses form encoding by default:

| Scenario | Content-Type | Behavior |
|----------|--------------|----------|
| Form data | `application/x-www-form-urlencoded` | Default |
| File upload | `multipart/form-data` | Via `hx-encoding` |
| JSON (custom) | `application/json` | Via `hx-ext="json-enc"` |

```html
<!-- Form encoded (default) -->
<form hx-post="/api/users">
  <input name="name">
  <!-- Sends: name=value -->
</form>

<!-- File upload -->
<form hx-post="/api/upload" hx-encoding="multipart/form-data">
  <input type="file" name="file">
</form>

<!-- JSON encoding (requires extension) -->
<form hx-post="/api/data" hx-ext="json-enc">
  <input name="name">
  <!-- Sends: {"name": "value"} -->
</form>
```

### Response Content Type

Server should return `text/html`:

```python
from fastapi import Response

@app.get("/api/users")
async def get_users():
    return Response(
        content="<ul><li>User 1</li></ul>",
        media_type="text/html"
    )
```

## Caching

### Cache-Control Headers

```python
from fastapi import Response

@app.get("/api/static-content")
async def get_static(response: Response):
    response.headers["Cache-Control"] = "max-age=3600"
    return "<div>Cached for 1 hour</div>"

@app.get("/api/dynamic-content")
async def get_dynamic(response: Response):
    response.headers["Cache-Control"] = "no-cache"
    return "<div>Always fresh</div>"
```

### Client-Side Caching

```html
<!-- Disable caching for specific request -->
<button hx-get="/api/data" hx-headers='{"Cache-Control": "no-cache"}'>
  Fresh Data
</button>
```

## Request Lifecycle Events

```
Event Sequence:
1. htmx:configRequest    - Configure request (modify headers, params)
2. htmx:beforeRequest    - Before request sent
3. htmx:beforeSend       - Just before XHR send
4. htmx:afterRequest     - After request completes
5. htmx:beforeSwap       - Before DOM update
6. htmx:afterSwap        - After DOM update
7. htmx:afterSettle      - After CSS transitions complete
```

**Modify request:**
```html
<div hx-on:htmx:configRequest="event.detail.headers['X-Request-Id'] = generateId()">
```

**Handle errors:**
```html
<div hx-on:htmx:afterRequest="
    if (!event.detail.successful) {
        console.error('Request failed:', event.detail.xhr.status);
    }
">
```

## REST Patterns with HTMX

### Collection Resource

```html
<!-- GET /tasks - List tasks -->
<div hx-get="/tasks" hx-trigger="load" hx-target="this">
  Loading tasks...
</div>

<!-- POST /tasks - Create task -->
<form hx-post="/tasks" hx-target="#task-list" hx-swap="beforeend">
  <input name="title" required>
  <button type="submit">Add Task</button>
</form>
```

### Item Resource

```html
<!-- GET /tasks/123 - Get single task -->
<button hx-get="/tasks/123" hx-target="#task-detail">View Task</button>

<!-- PUT /tasks/123 - Replace task -->
<form hx-put="/tasks/123" hx-target="this" hx-swap="outerHTML">
  <input name="title" value="Current Title">
  <input name="description" value="Current Description">
  <button type="submit">Save</button>
</form>

<!-- PATCH /tasks/123 - Update task partially -->
<input type="checkbox"
       hx-patch="/tasks/123"
       hx-vals='{"completed": true}'
       hx-target="closest li"
       hx-swap="outerHTML">

<!-- DELETE /tasks/123 - Delete task -->
<button hx-delete="/tasks/123"
        hx-target="closest li"
        hx-swap="outerHTML"
        hx-confirm="Delete this task?">
  Delete
</button>
```

### Sub-Resource

```html
<!-- GET /tasks/123/comments - Get task's comments -->
<div hx-get="/tasks/123/comments"
     hx-trigger="revealed"
     hx-swap="innerHTML">
  Loading comments...
</div>

<!-- POST /tasks/123/comments - Add comment to task -->
<form hx-post="/tasks/123/comments"
      hx-target="#comments"
      hx-swap="beforeend">
  <textarea name="content"></textarea>
  <button type="submit">Add Comment</button>
</form>
```

### Action Endpoints (RPC-style)

Some actions don't fit REST perfectly:

```html
<!-- POST /tasks/123/complete - Action endpoint -->
<button hx-post="/tasks/123/complete"
        hx-target="closest li"
        hx-swap="outerHTML">
  Complete
</button>

<!-- POST /tasks/123/archive -->
<button hx-post="/tasks/123/archive"
        hx-target="closest li"
        hx-swap="outerHTML">
  Archive
</button>

<!-- POST /cart/checkout -->
<button hx-post="/cart/checkout"
        hx-target="#checkout-result">
  Checkout
</button>
```

## Polling and Real-Time

### Polling

```html
<!-- Poll every 30 seconds -->
<div hx-get="/api/notifications"
     hx-trigger="every 30s"
     hx-swap="innerHTML">
</div>

<!-- Poll only when visible -->
<div hx-get="/api/status"
     hx-trigger="every 5s [isVisible()]"
     hx-swap="innerHTML">
</div>

<!-- Stop polling on condition -->
<div hx-get="/api/job/123/status"
     hx-trigger="every 2s"
     hx-swap="outerHTML">
  Processing...
</div>
<!-- Server returns element without hx-trigger when complete -->
```

### Server-Sent Events (SSE)

```html
<div hx-ext="sse" sse-connect="/events">
  <div sse-swap="message">Waiting for messages...</div>
  <div sse-swap="notification">No notifications</div>
</div>
```

### WebSockets

```html
<div hx-ext="ws" ws-connect="/chat">
  <div id="messages"></div>
  <form ws-send>
    <input name="message">
    <button type="submit">Send</button>
  </form>
</div>
```
