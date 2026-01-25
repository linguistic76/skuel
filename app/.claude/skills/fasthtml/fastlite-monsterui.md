# Fastlite Database & MonsterUI Components

## Fastlite (SQLite Database)

Fastlite is a CRUD-oriented API for SQLite, built on the MiniDataAPI specification. Uses APSW for optimized connections.

### Setup

```python
from fastlite import *

# In-memory (testing)
db = database(':memory:')

# File-based (production)
db = database('data/app.db')
```

### Table Definition

```python
# Define with class and type hints
class User:
    id: int
    name: str
    email: str
    active: bool = True  # Default value

# Create table (transform=True updates schema on field changes)
users = db.create(User, pk='id', transform=True)

# Custom primary key
class Book:
    isbn: str
    title: str
    pages: int

books = db.create(Book, pk='isbn', transform=True)
```

### CRUD Operations

#### Create

```python
# Insert returns the full record
user = users.insert(name='Alice', email='alice@ex.com')
# User(id=1, name='Alice', email='alice@ex.com', active=1)

# Insert with defaults
user = users.insert(name='Bob', email='bob@ex.com', active=False)
```

#### Read

```python
# List all records
all_users = users()
# [User(id=1, ...), User(id=2, ...)]

# Get by primary key
user = users[1]  # Raises NotFoundError if not exists

# Check existence
if 1 in users:
    print("User exists")

# Filter with where clause
active_users = users(where="active=1")

# Parameterized queries (safe from injection)
users("name=?", ('Alice',))
users("email LIKE ?", ('%@example.com',))

# Ordering and pagination
users(order_by='name')
users(order_by='created_at DESC')
users(limit=10, offset=20)

# Combined
users(where="active=1", order_by='name', limit=5)
```

#### Update

```python
# Modify and update
user = users[1]
user.name = 'Alice Smith'
user.active = True
users.update(user)  # Returns updated record

# Update returns the record
updated = users.update(user)
```

#### Delete

```python
# Delete by primary key
users.delete(1)  # Returns the table

# NotFoundError if not exists
try:
    users.delete(999)
except NotFoundError:
    print("User not found")
```

### Query Constraints

```python
# xtra() constrains all subsequent queries
users.xtra(active=True)

# Now all operations are filtered
active = users()  # Only active users
users.insert(name='Charlie')  # active=True automatically

# Clear constraint
users.xtra()  # Remove constraint
```

### Foreign Keys & Relationships

```python
class Author:
    id: int
    name: str

class Book:
    id: int
    title: str
    author_id: int

authors = db.create(Author, transform=True)
books = db.create(Book, transform=True)

# Manual joins via where clause
author = authors[1]
author_books = books(where=f"author_id={author.id}")

# Or with session filtering
books.xtra(author_id=author.id)
author_books = books()
```

### Session Integration Pattern

```python
from fasthtml.common import *
from fastlite import *

db = database('data/app.db')

class Todo:
    id: int
    session_id: str
    title: str
    done: bool = False

todos = db.create(Todo, transform=True)

@rt
def index(session):
    if 'id' not in session:
        session['id'] = str(uuid.uuid4())

    # Filter by session
    user_todos = todos(where=f"session_id='{session['id']}'")
    return Titled("Todos", Ul(*[Li(t.title) for t in user_todos]))

@app.post("/add")
def add_todo(session, title: str):
    todos.insert(session_id=session['id'], title=title)
    return RedirectResponse('/', status_code=303)
```

## MonsterUI Component Library

MonsterUI is a shadcn-like component library for FastHTML, combining FrankenUI, DaisyUI, and Tailwind.

### Setup

```python
from fasthtml.common import *
from monsterui.all import *

# Apply theme in headers
app, rt = fast_app(hdrs=Theme.blue.headers(highlightjs=True))
```

### Available Themes

```python
Theme.blue      # Blue primary
Theme.green     # Green primary
Theme.orange    # Orange primary
Theme.purple    # Purple primary
Theme.red       # Red primary
Theme.zinc      # Neutral gray
# Each has .headers() for hdrs param
```

### Button Styles

```python
# Use ButtonT presets for consistency
Button("Primary", cls=ButtonT.primary)
Button("Secondary", cls=ButtonT.secondary)
Button("Destructive", cls=ButtonT.destructive)
Button("Outline", cls=ButtonT.outline)
Button("Ghost", cls=ButtonT.ghost)
Button("Link", cls=ButtonT.link)

# Sizes
Button("Small", cls=(ButtonT.primary, "btn-sm"))
Button("Large", cls=(ButtonT.primary, "btn-lg"))
```

### Form Components

#### LabelInput (Labeled Input)

```python
# Creates label + input with proper linking
LabelInput("Email", type="email", id="email", required=True)

# Renders:
# <label for="email">Email</label>
# <input type="email" id="email" required>
```

#### Other Label* Components

```python
LabelRange("Volume", id="volume", min="0", max="100")
LabelCheckboxX("Accept terms", id="terms")
LabelTextarea("Bio", id="bio", rows="4")
```

### Layout Components

#### Flex Layouts

```python
# Left-aligned horizontal
DivLAligned(Span("Left"), Span("Also left"))

# Right-aligned
DivRAligned(Button("Action"))

# Centered
DivCentered(H1("Centered Title"))

# Fully spaced (between)
DivFullySpaced(
    Span("Left side"),
    Span("Right side")
)

# Horizontal stack
DivHStacked(Icon("star"), Span("Rating"))

# Vertical stack
DivVStacked(P("Line 1"), P("Line 2"))
```

#### Grid

```python
Grid(
    LabelInput("First Name"),
    LabelInput("Last Name"),
    cols=2  # 2-column grid
)

Grid(
    *[Card(...) for card in cards],
    cols=3,
    cls="gap-4"
)
```

### Cards

```python
Card(
    H3("Card Title"),
    P("Card content goes here"),
    footer=DivFullySpaced(
        Span("Footer left"),
        Button("Action", cls=ButtonT.primary)
    )
)
```

### Icons (UkIcon)

```python
UkIcon("home", height=24)
UkIcon("search", height=16)
UkIcon("user", height=20)

# As link
UkIconLink("github", href="https://github.com/...", height=20)

# Common icons: home, search, user, settings, mail, phone,
# calendar, clock, check, x, plus, minus, edit, trash,
# star, heart, bookmark, share, download, upload, etc.
```

### Avatars

```python
# DiceBear avatar (generates from name)
DiceBearAvatar("Alice Smith", h=48, w=48)
DiceBearAvatar("Bob Jones", h=24, w=24)
```

### Text Presets

```python
P("Normal text")
P("Muted small text", cls=TextPresets.muted_sm)
P("Muted text", cls=TextPresets.muted)
P("Lead text", cls=TextPresets.lead)
H1("Large heading", cls=TextPresets.h1)
```

### Markdown Rendering

```python
# Render markdown with styling
render_md("""
# Heading

This is **bold** and *italic*.

- List item 1
- List item 2

```python
def hello():
    print("world")
```
""")

# Code highlighting requires highlightjs=True in headers
app, rt = fast_app(hdrs=Theme.blue.headers(highlightjs=True))
```

### Semantic Text

```python
Card(
    H1("MonsterUI Semantic Text"),
    P(
        Strong("MonsterUI"), " brings ",
        Em("beautiful styling"), " with ",
        Mark("zero configuration"), "."
    ),
    Blockquote(
        P("Write semantic HTML, get modern styling."),
        Cite("MonsterUI Team")
    ),
    footer=Small("Released 2025")
)
```

## Complete Example: Contact Form

```python
from fasthtml.common import *
from monsterui.all import *

app, rt = fast_app(hdrs=Theme.blue.headers())

@rt
def index():
    relationship = ["Parent", "Sibling", "Friend", "Spouse", "Child", "Other"]

    return Titled("Emergency Contact",
        DivCentered(
            H3("Emergency Contact Form"),
            P("Please fill out completely", cls=TextPresets.muted_sm)
        ),
        Form(
            Grid(
                LabelInput("Name", id="name", required=True),
                LabelInput("Email", id="email", type="email", required=True),
                cols=2
            ),
            H4("Relationship"),
            Grid(*[LabelCheckboxX(r) for r in relationship], cols=3),
            DivCentered(
                Button("Submit", type="submit", cls=ButtonT.primary)
            ),
            action="/submit",
            method="post",
            cls="space-y-4"
        )
    )

serve()
```

## Complete Example: Team Cards

```python
from fasthtml.common import *
from monsterui.all import *

app, rt = fast_app(hdrs=Theme.blue.headers())

def TeamCard(name, role, location="Remote"):
    icons = ("mail", "linkedin", "github")
    return Card(
        DivLAligned(
            DiceBearAvatar(name, h=24, w=24),
            Div(
                H3(name),
                P(role, cls=TextPresets.muted_sm)
            )
        ),
        footer=DivFullySpaced(
            DivHStacked(
                UkIcon("map-pin", height=16),
                P(location, cls=TextPresets.muted_sm)
            ),
            DivHStacked(*[UkIconLink(i, height=16) for i in icons])
        )
    )

@rt
def index():
    team = [
        ("Alice Chen", "Engineering Lead", "San Francisco"),
        ("Bob Smith", "Product Manager", "New York"),
        ("Carol White", "Designer", "Remote"),
    ]

    return Titled("Our Team",
        Grid(*[TeamCard(*m) for m in team], cols=3, cls="gap-4")
    )

serve()
```

## Integration Patterns

### Fastlite + MonsterUI CRUD App

```python
from fasthtml.common import *
from fastlite import *
from monsterui.all import *

db = database('data/tasks.db')

class Task:
    id: int
    title: str
    done: bool = False

tasks = db.create(Task, transform=True)

app, rt = fast_app(hdrs=Theme.blue.headers())

def TaskItem(task):
    return Card(
        DivFullySpaced(
            P(task.title, cls="line-through" if task.done else ""),
            DivHStacked(
                Button("Toggle",
                       hx_post=f"/toggle/{task.id}",
                       hx_target="closest article",
                       hx_swap="outerHTML",
                       cls=ButtonT.ghost),
                Button("Delete",
                       hx_delete=f"/delete/{task.id}",
                       hx_target="closest article",
                       hx_swap="outerHTML",
                       cls=ButtonT.destructive)
            )
        ),
        id=f"task-{task.id}"
    )

@rt
def index():
    return Titled("Tasks",
        Form(
            DivHStacked(
                LabelInput("New Task", id="title", name="title"),
                Button("Add", type="submit", cls=ButtonT.primary)
            ),
            hx_post="/add",
            hx_target="#task-list",
            hx_swap="beforeend"
        ),
        Div(*[TaskItem(t) for t in tasks()], id="task-list")
    )

@app.post("/add")
def add(title: str):
    task = tasks.insert(title=title)
    return TaskItem(task)

@app.post("/toggle/{id}")
def toggle(id: int):
    task = tasks[id]
    task.done = not task.done
    tasks.update(task)
    return TaskItem(task)

@app.delete("/delete/{id}")
def delete(id: int):
    tasks.delete(id)
    return ""

serve()
```

### Session-Scoped Data

```python
from uuid import uuid4

@rt
def index(session):
    if 'user_id' not in session:
        session['user_id'] = str(uuid4())

    # Scope queries to session
    user_tasks = tasks(where=f"user_id='{session['user_id']}'")

    return Titled("My Tasks",
        Div(*[TaskItem(t) for t in user_tasks], id="task-list")
    )
```
