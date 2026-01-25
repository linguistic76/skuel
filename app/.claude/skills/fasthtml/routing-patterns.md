# FastHTML Routing Patterns

## SKUEL API Conventions (January 2026)

**SKUEL uses query parameters for all API routes**, following FastHTML's "query parameters preferred" pattern:

```python
# ✅ SKUEL Pattern - Query params for API routes
@rt("/api/tasks/get")
async def get_task(request, uid: str):  # uid from ?uid=...
    return await service.get(uid)

@rt("/api/tasks/complete", methods=["POST"])
async def complete_task(request, uid: str):  # uid from ?uid=...
    return await service.complete(uid)

# ❌ Avoid path params in API routes
@rt("/api/tasks/{uid}")  # Don't do this
async def get_task(uid: str):
    ...
```

**Why query params for APIs:**
- Type hints provide automatic parameter extraction
- Cleaner route definitions (no `request.path_params["uid"]`)
- Consistent pattern across all 130+ API routes
- Better alignment with FastHTML's philosophy

**When path params ARE appropriate:**
- UI routes for SEO-friendly URLs: `/tasks/task_123`
- Static file routes: `/{fname:path}.{ext:static}`
- User-facing navigation: `/profile/{username}`

## Route Decorator Behavior

### Basic Routing

```python
from fasthtml.common import *
app, rt = fast_app()

# Function name becomes route path
@rt
def index(): ...          # GET, POST /

@rt
def about(): ...          # GET, POST /about

@rt
def users(): ...          # GET, POST /users

# Explicit path override
@rt("/custom/path")
def handler(): ...        # GET, POST /custom/path
```

### HTTP Method Specificity

```python
# Specific methods
@app.get("/users")
def list_users(): ...

@app.post("/users")
def create_user(): ...

@app.put("/users/{id}")
def update_user(id: int): ...

@app.delete("/users/{id}")
def delete_user(id: int): ...

@app.patch("/users/{id}")
def patch_user(id: int): ...

# Multiple methods
@app.route("/", methods=['get', 'post'])
def handle_both(): ...
```

### Function Name Conventions

```python
# When function name matches HTTP verb, that method is used
@rt
def get(): ...            # GET /get
def post(): ...           # POST /post
def put(): ...            # PUT /put
def delete(): ...         # DELETE /delete
```

## Path Parameters

### Type Conversion

```python
# Basic types
@app.get("/users/{user_id}")
def get_user(user_id: int):          # Auto-converts to int
    return f"User {user_id}"

@app.get("/items/{price}")
def get_item(price: float):          # Auto-converts to float
    return f"Price: ${price}"

# Path type (captures slashes)
@app.get("/files/{filepath:path}")
def get_file(filepath: str):
    return FileResponse(filepath)

# Static file pattern
@rt("/{fname:path}.{ext:static}")
async def static(fname: str, ext: str):
    return FileResponse(f'{fname}.{ext}')
```

### Starlette Path Converters

| Converter | Description | Example |
|-----------|-------------|---------|
| `str` | Default, any string | `/users/{name}` |
| `int` | Integer only | `/users/{id:int}` |
| `float` | Float values | `/price/{amount:float}` |
| `path` | Path with slashes | `/files/{path:path}` |
| `uuid` | UUID format | `/items/{uuid:uuid}` |

## Query Parameters

### Basic Usage

```python
# Type-annotated params become query params
@rt
def search(q: str, limit: int = 10, offset: int = 0):
    return f"Query: {q}, limit: {limit}, offset: {offset}"
# GET /search?q=hello&limit=5

# Optional with defaults
@rt
def filter(status: str = "active", sort: str = "date"):
    return f"Status: {status}, Sort: {sort}"
# GET /filter → uses defaults
# GET /filter?status=pending → overrides status
```

### Type Coercion

```python
# Boolean parameters
@rt
def toggle(enabled: bool = True):
    return "Enabled" if enabled else "Disabled"
# GET /toggle?enabled=true
# GET /toggle?enabled=false
# GET /toggle?enabled=1
# GET /toggle?enabled=0

# List parameters
@rt
def multi(tags: list[str] = None):
    return f"Tags: {tags}"
# GET /multi?tags=a&tags=b&tags=c

# Date parsing
from fasthtml.common import parsed_date
@rt
def by_date(d: parsed_date):
    return f"Date: {d}"
# GET /by_date?d=2024-01-15
```

### Enum Constraints

```python
from fasthtml.common import str_enum

# Define allowed values
Status = str_enum('Status', 'active', 'pending', 'archived')
Priority = str_enum('Priority', 'low', 'medium', 'high')

@rt
def tasks(status: Status, priority: Priority = None):
    return f"Status: {status}, Priority: {priority}"
# GET /tasks?status=active
# GET /tasks?status=invalid → 404

# Combined with path params
@app.get("/items/{category}")
def items(category: str_enum('Cat', 'books', 'electronics', 'clothing')):
    return f"Category: {category}"
```

## Parameter Sources

FastHTML searches for parameters in order:
1. Path parameters
2. Query parameters
3. Cookies
4. Headers
5. Session
6. Form data

```python
@rt
def handler(
    path_id: int,          # From path if defined
    query_param: str,      # From query string
    cookie_val: str,       # From cookie named 'cookie_val'
    session,               # Starlette session
    req,                   # Starlette request
):
    ...
```

## Route References & URL Generation

### Using Routes in Attributes

```python
@rt
def profile(email: str):
    return P(f"Profile: {email}")

@rt
def users():
    return Ul(
        Li(A("Alice", href=profile.to(email="alice@ex.com"))),
        Li(A("Bob", href=profile.to(email="bob@ex.com"))),
    )

# Forms with route references
form = Form(
    Input(name="email"),
    Button("Submit"),
    action=profile,      # Route function as action
    method="post"
)
```

### HTMX with Route References

```python
@rt
def load_data(category: str): ...

@rt
def page():
    return Button(
        "Load Electronics",
        hx_get=load_data.to(category="electronics"),
        hx_target="#result"
    )
```

## APIRouter (Modular Routes)

### Separate Route Files

```python
# products.py
from fasthtml.common import APIRouter

ar = APIRouter()

@ar
def list_products():
    return Ul(*[Li(p.name) for p in products])

@ar
def product_detail(id: int):
    return Div(f"Product {id}")

@ar
def create_product():
    return Form(...)
```

```python
# main.py
from fasthtml.common import *
from products import ar

app, rt = fast_app()
ar.to_app(app)  # Attach router to app

@rt
def index():
    return Titled("Home",
        A("Products", href=ar.rt_funcs['list_products']))
```

### Router with Prefix

```python
# api/users.py
ar = APIRouter(prefix="/api/users")

@ar
def list():              # GET /api/users/list
    ...

@ar
def get(id: int):        # GET /api/users/get?id=123
    ...

@ar
def create():            # POST /api/users/create
    ...
```

## Request Object Access

```python
@rt
def handler(req):
    # Request properties
    method = req.method
    url = req.url
    path = req.url.path
    query = req.query_params

    # Headers
    user_agent = req.headers.get('user-agent')
    content_type = req.headers.get('content-type')

    # Client info
    ip = req.client.host
    port = req.client.port

    # URL generation
    url = req.url_for('profile', email='test@ex.com')

    return P(f"IP: {ip}")
```

## Exception Handlers

```python
def not_found(req, exc):
    return Titled("404", P("Page not found"))

def server_error(req, exc):
    return Titled("500", P("Something went wrong"))

exception_handlers = {
    404: not_found,
    500: server_error,
}

app, rt = fast_app(exception_handlers=exception_handlers)
```

## Async Routes

```python
# Sync (fine for CPU-bound)
@rt
def sync_handler():
    return compute_result()

# Async (required for I/O)
@rt
async def async_handler():
    data = await fetch_from_db()
    file = await read_file()
    return P(data)

# File uploads require async
@rt
async def upload(file: UploadFile):
    content = await file.read()
    return P(f"Size: {len(content)}")
```

## Middleware & Beforeware

### Beforeware (Pre-route Processing)

```python
def log_request(req, sess):
    print(f"{req.method} {req.url.path}")
    # Return None to continue, or Response to short-circuit

def require_auth(req, sess):
    if 'user' not in sess:
        return RedirectResponse('/login', status_code=303)

beforeware = Beforeware(
    require_auth,
    skip=[
        r'/login',
        r'/register',
        r'/static/.*',
        r'/favicon\.ico',
    ]
)

app, rt = fast_app(before=beforeware)
```

### Multiple Beforeware

```python
def first_check(req, sess): ...
def second_check(req, sess): ...

# Chain multiple
app, rt = fast_app(before=[
    Beforeware(first_check, skip=[r'/public/.*']),
    Beforeware(second_check, skip=[r'/api/.*']),
])
```

## Common Patterns

### Redirect After POST

```python
@app.post("/submit")
def submit_form(data: str):
    save_to_db(data)
    return RedirectResponse('/success', status_code=303)
```

### Conditional HTMX Response

```python
@rt
def page(req):
    content = Div(P("Page content"), id="content")

    if req.headers.get("HX-Request"):
        return content  # Fragment for HTMX

    return Titled("Full Page", content)  # Full page for browser
```

### Dynamic Route Registration

```python
app, rt = fast_app()

# Routes can be added dynamically
def make_handler(name):
    def handler():
        return P(f"Hello from {name}")
    handler.__name__ = name
    return handler

for name in ['alice', 'bob', 'charlie']:
    app.get(f"/{name}")(make_handler(name))
```
