---
name: fasthtml
description: Expert guide for FastHTML - Python's server-rendered hypermedia framework. Use when building HTML-first web apps, creating routes with decorators, working with FastTags (FT components), handling forms, integrating HTMX, using fastlite database, or when the user mentions FastHTML, fast_app, FT components, or server-rendered HTML.
allowed-tools: Read, Grep, Glob
---

# FastHTML: Server-Rendered Hypermedia Framework

## Core Philosophy

> "HTML-first, Python-native, zero JavaScript frameworks"

FastHTML combines Starlette, Uvicorn, HTMX, and fastcore's FastTags into a server-rendered hypermedia framework. It is NOT FastAPI - it's designed for HTML apps, not API services.

**Key Principles:**
- Server returns HTML fragments, not JSON
- Python objects generate HTML (FastTags)
- HTMX for dynamic updates without full page reloads
- Compatible with vanilla JS, NOT React/Vue/Svelte
- Use `serve()` - no `if __name__ == "__main__"` needed

## Minimal App

```python
from fasthtml.common import *

app, rt = fast_app()

@rt
def index():
    return Titled("My App", P("Hello, World!"))

serve()
```

Run with: `python main.py` (access via localhost:5001)

## FastTags (FT Components)

FTs are m-expressions: positional params = children, named params = attributes.

```python
# Basic tags
H1("Title")                           # <h1>Title</h1>
P("Text", cls="intro")                # <p class="intro">Text</p>
A("Link", href="/page")               # <a href="/page">Link</a>

# Reserved word aliases
Label("Name", _for="name")            # 'for' → '_for' or 'fr'
Div(cls="container")                  # 'class' → 'cls'

# Boolean attributes
Option("One", selected=True)          # selected renders as attribute
Option("Two", selected=False)         # selected omitted

# Special characters in attributes
Div(**{'@click': "alert('hi')"})      # Dict unpacking for special chars
```

### Composing Components

```python
def Hero(title, statement):
    return Div(H1(title), P(statement), cls="hero")

def Card(title, *children, footer=None):
    return Div(
        Div(H2(title), *children, cls="card-body"),
        Div(footer, cls="card-footer") if footer else None,
        cls="card"
    )
```

### Custom Tags

```python
# Auto-created from fasthtml.components
from fasthtml.components import Custom_tag
Custom_tag()  # <custom-tag></custom-tag>

# Manual definition
from fasthtml.common import ft_hx
def My_component(*c, **kwargs):
    return ft_hx('my-component', *c, **kwargs)
```

### Rendering Classes

```python
class Person:
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def __ft__(self):
        return Div(H3(self.name), P(f"Age: {self.age}"))

# Now Person instances auto-render in FT trees
person = Person("Alice", 30)
page = Div(person)  # Uses __ft__ method
```

## Routing

### Basic Routes

```python
# Function name = route path
@rt
def index(): return Titled("Home")          # GET /

@rt
def about(): return Titled("About")         # GET /about

# Explicit path
@rt("/custom/path")
def handler(): return "Response"

# HTTP methods
@app.get("/users")
def get_users(): ...

@app.post("/users")
def create_user(): ...
```

### Parameters

```python
# Query parameters (SKUEL preferred pattern for APIs)
@rt("/api/users/get")
def get_user(user_id: int):  # ?user_id=123
    return f"User {user_id}"

# Query parameters (type-annotated)
@rt
def search(q: str, limit: int = 10):
    return f"Search: {q}, limit: {limit}"
# GET /search?q=hello&limit=5

# Path parameters (for UI/SEO-friendly routes only)
@app.get("/users/{user_id}")
def user_profile(user_id: int): return f"User {user_id}"

# Enum constraints
name = str_enum('names', 'Alice', 'Bob', 'Charlie')
@rt
def greet(nm: name): return f"Hello, {nm}!"
```

**SKUEL Convention:** API routes use query params (`?uid=...`), UI routes may use path params for SEO-friendly URLs. See [routing-patterns.md](routing-patterns.md) for details.

### Route References

```python
@rt
def profile(email: str): return fill_form(form, data)

# Use route function in attributes
form = Form(action=profile)(
    Input(name="email"),
    Button("Submit")
)

# Generate paths with parameters
path = profile.to(email="user@example.com")  # '/profile?email=user%40example.com'
```

## APIRouter (Multi-File Routes)

`APIRouter` lets you organize routes across multiple files:

```python
# products.py
from fasthtml.common import *

ar = APIRouter(prefix="/products")

@ar("/all")
def all_products(req):
    return Div(
        "Welcome to Products!",
        Button("Details",
               hx_get=req.url_for("details", pid=42),
               hx_target="#products_list",
               hx_swap="outerHTML"),
        id="products_list"
    )

@ar("/details/{pid}")
def details(pid: int):
    return f"Product details for ID: {pid}"
```

```python
# main.py
from fasthtml.common import *
from products import ar

app, rt = fast_app()

ar.to_app(app)  # Register all routes from products.py

@rt
def index():
    return Div(
        "Click for products",
        hx_get=ar.rt_funcs.all_products,  # Reference routes via rt_funcs
        hx_swap="outerHTML"
    )

serve()
```

**Key Features:**
- `prefix` argument adds path prefix to all routes
- `ar.to_app(app)` registers routes with the FastHTML app
- `ar.rt_funcs.{function_name}` references routes for HTMX attributes

## Request & Response

### Special Parameters

```python
@rt
def handler(req):              # Starlette Request object
    ip = req.client.host
    headers = req.headers
    return f"IP: {ip}"

@rt
def with_session(session):     # Session dict (auto-managed)
    visits = session.get('visits', 0) + 1
    session['visits'] = visits
    return f"Visit #{visits}"

@rt
def with_htmx(htmx):           # HtmxHeaders object
    if htmx: return P("HTMX request")
    return Titled("Full page")
```

### Response Types

```python
# FT components → HTML
@rt
def page(): return H1("Hello"), P("World")

# Tuples → Title + content
@rt
def titled(): return Title("Page"), H1("Content")

# Starlette responses
@rt
def file(): return FileResponse("file.pdf")

@rt
def redirect(): return RedirectResponse("/new-path")

# HTMX-specific headers
@rt
def htmx_redirect():
    return HtmxResponseHeaders(location="/dashboard")
```

## Form Handling

### Basic Forms

```python
@rt
def form_page():
    return Form(
        Input(name="username", type="text"),
        Input(name="email", type="email"),
        Button("Submit", type="submit"),
        action="/submit", method="post"
    )

@app.post("/submit")
def handle_form(username: str, email: str):
    return P(f"Got: {username}, {email}")
```

### Dataclass Binding

```python
from dataclasses import dataclass

@dataclass
class User:
    name: str
    email: str
    age: int

@app.post("/create")
def create_user(user: User):
    # Form fields auto-unpack to dataclass
    return P(f"Created: {user.name}")
```

### fill_form Helper

```python
@dataclass
class Profile:
    email: str
    name: str

profiles = {"john@ex.com": Profile("john@ex.com", "John")}

@rt
def edit(email: str):
    return fill_form(profile_form, profiles[email])

profile_form = Form(
    Input(name="email"),
    Input(name="name"),
    Button("Save"),
    action="/save", method="post"
)
```

## HTMX Integration

### Dynamic Updates

```python
@rt
def counter():
    return Div(
        P("Count: 0", id="count"),
        Button("Increment",
               hx_post="/increment",
               hx_target="#count",
               hx_swap="innerHTML")
    )

@app.post("/increment")
def increment():
    # Returns HTML fragment, replaces #count content
    return "Count: 1"
```

### HTMX Attributes in FastHTML

```python
# All hx-* attributes use underscores
Button("Load",
       hx_get="/data",           # hx-get
       hx_target="#result",      # hx-target
       hx_swap="outerHTML",      # hx-swap
       hx_trigger="click",       # hx-trigger
       hx_indicator="#spinner")  # hx-indicator

# Out-of-band updates
def notification():
    return Div("Updated!", id="notify", hx_swap_oob="true")
```

### WebSockets

```python
app = FastHTML(exts='ws')

@rt
def chat():
    return Div(
        Div(id='messages'),
        Form(Input(id='msg'), id='form', ws_send=True),
        hx_ext='ws', ws_connect='/ws'
    )

@app.ws('/ws')
async def ws(msg: str, send):
    await send(Div(f"You: {msg}", id="messages"))
    return Div("Response", id="messages")
```

### WebSockets with setup_ws (Simplified)

The `setup_ws` function simplifies WebSocket handling:

```python
app = FastHTML(exts='ws')
rt = app.route
msgs = []

@rt('/')
def home():
    return Div(hx_ext='ws', ws_connect='/ws')(
        Div(Ul(*[Li(m) for m in msgs], id='msg-list')),
        Form(Input(id='msg'), id='form', ws_send=True)
    )

async def ws(msg: str):
    msgs.append(msg)
    await send(Ul(*[Li(m) for m in msgs], id='msg-list'))

send = setup_ws(app, ws)  # Returns send function, wires up WebSocket
```

### WebSocket Connection Events

```python
async def on_connect(send):
    await send(Div('Hello, you have connected', id="notifications"))

async def on_disconnect(ws):
    print('Disconnected!')

@app.ws('/ws', conn=on_connect, disconn=on_disconnect)
async def ws(msg: str, send):
    await send(Div('Hello ' + msg, id="notifications"))
    return Div('Goodbye ' + msg, id="notifications")
```

### Server-Sent Events

```python
hdrs = (Script(src="https://unpkg.com/htmx-ext-sse@2.2.3/sse.js"),)
app, rt = fast_app(hdrs=hdrs)

@rt
def stream():
    return Div(hx_ext="sse", sse_connect="/events", sse_swap="message")

@rt
async def events():
    async def generate():
        while True:
            yield sse_message(P("Update!"))
            await asyncio.sleep(1)
    return EventStream(generate())
```

## Headers and Static Files

### fast_app Configuration

```python
app, rt = fast_app(
    pico=False,  # Disable default Pico CSS
    hdrs=(
        Link(rel='stylesheet', href='styles.css'),
        Script(src="app.js"),
        MarkdownJS(),
        HighlightJS(langs=['python', 'javascript']),
    )
)
```

### Static Files

```python
# Default: static extensions served from app directory
# Customize with static_path='public'

# Explicit static routes
@rt("/{fname:path}.{ext:static}")
async def serve_static(fname: str, ext: str):
    return FileResponse(f'public/{fname}.{ext}')
```

## Sessions & Cookies

```python
# Cookies
@rt
def set_cookie():
    return P("Cookie set"), cookie('user', 'alice')

@rt
def get_cookie(user: str):  # Auto-extracted from cookies
    return f"Hello, {user}"

# Sessions (requires secret_key in fast_app)
@rt
def with_session(session):
    session['user_id'] = 123
    return P("Logged in")
```

## Authentication (Beforeware)

```python
def auth_before(req, sess):
    auth = req.scope['auth'] = sess.get('auth')
    if not auth:
        return RedirectResponse('/login', status_code=303)

beforeware = Beforeware(
    auth_before,
    skip=[r'/login', r'/static/.*', r'/favicon\.ico']
)

app, rt = fast_app(before=beforeware)
```

## File Uploads

```python
@rt
def upload_form():
    return Form(
        Input(type="file", name="file"),
        Button("Upload"),
        hx_post="/upload", hx_target="#result"
    ), Div(id="result")

@rt
async def upload(file: UploadFile):
    content = await file.read()
    Path(f"uploads/{file.filename}").write_bytes(content)
    return P(f"Uploaded: {file.filename} ({file.size} bytes)")

# Multiple files
@rt
async def upload_many(files: list[UploadFile]):
    return Ul(*[Li(f.filename) for f in files])
```

## Toasts

```python
setup_toasts(app)

@rt
def action(session):
    add_toast(session, "Success!", "success")
    add_toast(session, "Warning!", "warning")
    return Titled("Action Complete")
```

## Testing

```python
from starlette.testclient import TestClient

client = TestClient(app)

# Regular request (full page)
response = client.get("/")
assert "<html>" in response.text

# HTMX request (fragment only)
response = client.get("/", headers={"HX-Request": "1"})
assert "<html>" not in response.text
```

## Live Reload (Development)

```python
# Method 1: FastHTMLWithLiveReload
from fasthtml.common import *
app = FastHTMLWithLiveReload()
# Run: uvicorn main:app --reload

# Method 2: fast_app with live=True
app, rt = fast_app(live=True)
serve()
# Run: python main.py
```

## Fastlite Database

Fastlite is FastHTML's CRUD-oriented SQLite library.

### Basic Setup

```python
from fastlite import *

db = database(':memory:')  # or database('data/app.db')

# Define tables with classes
class Book:
    isbn: str
    title: str
    pages: int
    userid: int

class User:
    id: int
    name: str
    active: bool = True

# Create tables (transform=True updates schema when fields change)
books = db.create(Book, pk='isbn', transform=True)
users = db.create(User, transform=True)  # id is default pk
```

### CRUD Operations

```python
# Insert - returns the created row
user = users.insert(name='Alex', active=False)

# Query by primary key
user = users[1]  # Get by pk

# List all
all_users = users()

# Query with conditions
users(where="active = ?", where_args=[True])

# Update
user.name = 'Lauren'
user.active = True
users.update(user)

# Delete
users.delete(user.id)
```

### NotFoundError Handling

```python
from fastlite import NotFoundError

try:
    user = users['nonexistent']
except NotFoundError:
    print('User not found')

# Common pattern in routes
@app.post("/login")
def login(name: str, pwd: str, sess):
    try:
        u = users[name]
    except NotFoundError:
        # User doesn't exist - redirect to signup
        return RedirectResponse('/signup')
    # Continue with login...
```

### xtra() Query Constraints

`.xtra()` automatically constrains subsequent queries, updates, and inserts:

```python
# Constrain all queries to active users
users.xtra(active=True)

# Now users() only returns active users
active_users = users()  # Only active=True

# Multi-tenant pattern
def get_user_books(userid: int):
    books.xtra(userid=userid)  # Constrain to this user's books
    return books()  # Only this user's books
```

### Foreign Key Integration

```python
class Book:
    isbn: str
    title: str
    userid: int  # Foreign key to User.id

# Query user's books
def get_books_for_user(user_id: int):
    return books(where="userid = ?", where_args=[user_id])
```

## Additional Resources

- [routing-patterns.md](routing-patterns.md) - Advanced routing patterns
- [components-reference.md](components-reference.md) - Complete FT component reference
- [fastlite-monsterui.md](fastlite-monsterui.md) - Database and UI components

## Related Skills

- **[html-htmx](../html-htmx/SKILL.md)** - HTMX patterns FastHTML uses for dynamic updates
- **[js-alpine](../js-alpine/SKILL.md)** - Alpine.js for client-side state in FastHTML apps
- **[monsterui](../monsterui/SKILL.md)** - MonsterUI components for FastHTML
- **[pydantic](../pydantic/SKILL.md)** - Request/response validation in FastHTML routes

## Foundation

- **[html-htmx](../html-htmx/SKILL.md)** - Understanding hypermedia architecture
- **[monsterui](../monsterui/SKILL.md)** - Pre-styled component library

## See Also

- `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` - Route registration patterns
- `/docs/decisions/ADR-020-fasthtml-route-registration-pattern.md` - Route registration ADR
- FastHTML Docs: https://fastht.ml
- GitHub: https://github.com/answerdotai/fasthtml
