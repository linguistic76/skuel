# FastHTML Components Reference

## FastTags (FT) Fundamentals

FastTags are m-expressions: positional arguments become children, named arguments become HTML attributes.

```python
from fasthtml.common import *

# Basic structure
Tag(child1, child2, attr1="value", attr2="value")

# Example
Div(
    H1("Title"),
    P("Content"),
    cls="container",
    id="main"
)
# <div class="container" id="main">
#   <h1>Title</h1>
#   <p>Content</p>
# </div>
```

## Attribute Handling

### Reserved Word Aliases

```python
# 'class' → 'cls'
Div(cls="container")           # <div class="container">

# 'for' → '_for' or 'fr'
Label("Name", _for="name")     # <label for="name">Name</label>
Label("Email", fr="email")     # <label for="email">Email</label>
```

### Boolean Attributes

```python
# True renders attribute name only
Input(type="checkbox", checked=True)   # <input type="checkbox" checked>
Option("One", selected=True)           # <option selected>One</option>

# False omits attribute entirely
Input(type="checkbox", checked=False)  # <input type="checkbox">
Option("Two", selected=False)          # <option>Two</option>

# Disabled, readonly, required, etc.
Input(disabled=True, readonly=True, required=True)
```

### Special Characters in Attributes

```python
# Use dict unpacking for special characters
Div(**{'@click': "handleClick()"})     # Alpine.js
Div(**{'x-data': "{open: false}"})     # Alpine.js
Div(**{'hx-on:click': "alert('hi')"})  # HTMX events
Div(**{'data-value': "123"})           # Data attributes
```

### Dynamic Attributes

```python
# Conditional attributes
attrs = {"disabled": True} if is_disabled else {}
Button("Submit", **attrs)

# Building attribute dict
def make_attrs(id, classes=None, data=None):
    attrs = {"id": id}
    if classes:
        attrs["cls"] = " ".join(classes)
    if data:
        for k, v in data.items():
            attrs[f"data-{k}"] = v
    return attrs

Div("Content", **make_attrs("main", ["container", "wide"]))
```

## Common HTML Tags

### Document Structure

```python
Html(Head(...), Body(...))
Head(Title("Page"), Meta(charset="utf-8"), Link(...), Script(...))
Body(Header(...), Main(...), Footer(...))
```

### Sectioning

```python
Header(Nav(...), H1("Site Title"))
Nav(Ul(Li(A("Home", href="/")), Li(A("About", href="/about"))))
Main(Article(...), Aside(...))
Article(H2("Title"), P("Content"), Footer("Author"))
Section(H2("Section"), P("Content"))
Aside(H3("Related"), Ul(...))
Footer(P("Copyright"))
```

### Text Content

```python
H1("Heading 1")
H2("Heading 2")
# ... through H6

P("Paragraph text")
Blockquote("Quote", cite="source")
Pre(Code("def foo(): pass"))
Hr()
Br()
```

### Inline Text

```python
Strong("Bold text")
Em("Emphasized")
Mark("Highlighted")
Small("Fine print")
Del("Deleted")
Ins("Inserted")
Sub("subscript")
Sup("superscript")
Code("inline code")
Kbd("keyboard input")
Abbr("HTML", title="HyperText Markup Language")
```

### Lists

```python
Ul(Li("Item 1"), Li("Item 2"), Li("Item 3"))
Ol(Li("First"), Li("Second"), Li("Third"))

# Definition list
Dl(
    Dt("Term"),
    Dd("Definition"),
    Dt("Another term"),
    Dd("Another definition")
)
```

### Links and Media

```python
A("Link text", href="/path", target="_blank")
Img(src="/image.jpg", alt="Description", width="200")
Video(src="/video.mp4", controls=True)
Audio(src="/audio.mp3", controls=True)
```

### Tables

**Prefer `TableFromDicts`** from `ui/data.py` for data-driven tables:

```python
from ui.data import TableFromDicts, TableT

TableFromDicts(
    header_data=["Name", "Age", "City"],
    body_data=[
        {"Name": "Alice", "Age": "30", "City": "NYC"},
        {"Name": "Bob", "Age": "25", "City": "LA"},
    ],
    body_cell_render=lambda k, v: Td(v, cls="font-bold" if k == "Name" else ""),
    cls=(TableT.striped, TableT.sm),
)
```

Manual `Table(Thead(...), Tbody(...))` is only needed for non-data-driven layouts (hardcoded rows, dynamic column counts, headerless tables).

## Form Elements

### Basic Form

```python
Form(
    Input(name="username", type="text", placeholder="Username"),
    Input(name="email", type="email", required=True),
    Input(name="password", type="password"),
    Button("Submit", type="submit"),
    action="/submit",
    method="post"
)
```

### Input Types

```python
Input(type="text", name="name")
Input(type="email", name="email")
Input(type="password", name="pass")
Input(type="number", name="age", min="0", max="120")
Input(type="date", name="date")
Input(type="time", name="time")
Input(type="datetime-local", name="datetime")
Input(type="tel", name="phone")
Input(type="url", name="website")
Input(type="search", name="q")
Input(type="color", name="color")
Input(type="range", name="volume", min="0", max="100")
Input(type="file", name="file")
Input(type="hidden", name="token", value="abc123")
```

### Checkbox and Radio

```python
# Checkbox
Label(
    Input(type="checkbox", name="agree", value="yes"),
    "I agree to terms"
)

# Radio group
Fieldset(
    Legend("Choose one:"),
    Label(Input(type="radio", name="color", value="red"), "Red"),
    Label(Input(type="radio", name="color", value="blue"), "Blue"),
    Label(Input(type="radio", name="color", value="green"), "Green"),
)
```

### Select

```python
Select(
    Option("Choose...", value="", disabled=True, selected=True),
    Option("Option 1", value="1"),
    Option("Option 2", value="2"),
    Option("Option 3", value="3"),
    name="choice"
)

# Optgroup
Select(
    Optgroup(
        Option("Sedan", value="sedan"),
        Option("SUV", value="suv"),
        label="Cars"
    ),
    Optgroup(
        Option("Sport", value="sport"),
        Option("Cruiser", value="cruiser"),
        label="Motorcycles"
    ),
    name="vehicle"
)
```

### Textarea

```python
Textarea(
    "Default content",
    name="message",
    rows="5",
    cols="40",
    placeholder="Enter message..."
)
```

### Form with Labels

```python
Form(
    Div(
        Label("Username", _for="username"),
        Input(id="username", name="username", required=True)
    ),
    Div(
        Label("Email", _for="email"),
        Input(id="email", name="email", type="email", required=True)
    ),
    Button("Submit", type="submit"),
    action="/register",
    method="post"
)
```

## HTMX Attributes

### Request Triggers

```python
# GET request
Button("Load", hx_get="/data", hx_target="#result")

# POST request
Button("Submit", hx_post="/submit", hx_target="#result")

# PUT, PATCH, DELETE
Button("Update", hx_put="/item/1")
Button("Patch", hx_patch="/item/1")
Button("Delete", hx_delete="/item/1")
```

### Targeting and Swapping

```python
# Target by ID
Button("Load", hx_get="/data", hx_target="#result")

# Target relative elements
Button("Load", hx_get="/data", hx_target="closest div")
Button("Load", hx_get="/data", hx_target="next .preview")
Button("Load", hx_get="/data", hx_target="previous p")

# Swap modes
Div(hx_get="/data", hx_swap="innerHTML")      # Replace contents (default)
Div(hx_get="/data", hx_swap="outerHTML")      # Replace element
Div(hx_get="/data", hx_swap="beforebegin")    # Before element
Div(hx_get="/data", hx_swap="afterbegin")     # First child
Div(hx_get="/data", hx_swap="beforeend")      # Last child
Div(hx_get="/data", hx_swap="afterend")       # After element
Div(hx_get="/data", hx_swap="delete")         # Remove target
Div(hx_get="/data", hx_swap="none")           # No swap
```

### Triggers

```python
# Default triggers
Button(hx_get="/data")                        # click (default for button)
Form(hx_post="/submit")                       # submit (default for form)
Input(hx_get="/search")                       # change (default for input)

# Explicit triggers
Div(hx_get="/data", hx_trigger="load")        # On page load
Div(hx_get="/data", hx_trigger="revealed")    # When scrolled into view
Div(hx_get="/data", hx_trigger="every 5s")    # Polling

# Trigger modifiers
Input(hx_get="/search", hx_trigger="keyup changed delay:300ms")
Button(hx_get="/data", hx_trigger="click once")
Form(hx_post="/save", hx_trigger="submit throttle:1s")
```

### Additional HTMX Features

```python
# Loading indicator
Button("Load", hx_get="/data", hx_indicator="#spinner")
Span("Loading...", id="spinner", cls="htmx-indicator")

# Disable during request
Button("Save", hx_post="/save", hx_disabled_elt="this")

# Include other values
Div(
    Input(name="search"),
    Button("Search", hx_get="/search", hx_include="[name='search']")
)

# Add values
Button("Like", hx_post="/like", hx_vals='{"id": 123}')

# Confirmation
Button("Delete", hx_delete="/item/1", hx_confirm="Are you sure?")

# Push URL to history
A("Page", hx_get="/page", hx_push_url="true")
```

### Out-of-Band Updates

```python
# Server can return multiple elements to update different parts
@rt
def update():
    return (
        Div("Main content", id="main"),
        Div("Also update", id="sidebar", hx_swap_oob="true"),
        Div("And this", id="footer", hx_swap_oob="true"),
    )
```

## Custom Component Patterns

### Simple Wrapper

```python
def Card(title, *children, footer=None):
    return Div(
        Div(H3(title), cls="card-header"),
        Div(*children, cls="card-body"),
        Div(footer, cls="card-footer") if footer else None,
        cls="card"
    )

# Usage
Card("Welcome", P("Hello!"), footer=A("Learn more", href="/about"))
```

### Composition

```python
def NavItem(text, href, active=False):
    return Li(
        A(text, href=href, cls="active" if active else ""),
        cls="nav-item"
    )

def Navbar(*items, brand="App"):
    return Nav(
        A(brand, href="/", cls="brand"),
        Ul(*items, cls="nav-menu"),
        cls="navbar"
    )

# Usage
Navbar(
    NavItem("Home", "/", active=True),
    NavItem("About", "/about"),
    NavItem("Contact", "/contact"),
)
```

### Using __ft__ Method

```python
class User:
    def __init__(self, name, email, avatar_url):
        self.name = name
        self.email = email
        self.avatar_url = avatar_url

    def __ft__(self):
        return Div(
            Img(src=self.avatar_url, cls="avatar"),
            Div(
                H4(self.name),
                P(self.email, cls="muted"),
            ),
            cls="user-card"
        )

# Now User instances auto-render
users = [User("Alice", "alice@ex.com", "/a.jpg")]
Ul(*[Li(user) for user in users])  # Uses __ft__ automatically
```

### Patching Existing Classes

```python
from fastcore.all import patch

@patch
def __ft__(self: User):
    return Div(H3(self.name), P(self.email))

# Or for third-party classes
@patch
def __ft__(self: datetime.date):
    return Span(self.strftime("%Y-%m-%d"), cls="date")
```

## Creating Custom Tags

### Auto-Generated Tags

```python
from fasthtml.components import My_custom_tag
My_custom_tag("Content", cls="styled")
# <my-custom-tag class="styled">Content</my-custom-tag>

# Underscores become hyphens
from fasthtml.components import Web_component_name
Web_component_name()
# <web-component-name></web-component-name>
```

### Manual Tag Definition

```python
from fasthtml.common import ft_hx

def My_element(*children, variant="default", **kwargs):
    return ft_hx(
        'my-element',
        *children,
        data_variant=variant,
        **kwargs
    )

# Usage
My_element("Content", variant="primary", id="elem1")
# <my-element data-variant="primary" id="elem1">Content</my-element>
```

## Built-in Helpers

### Titled

```python
# Creates Title tag + H1 + wraps content in Container
@rt
def page():
    return Titled("Page Title", P("Content"))

# Equivalent to:
return Title("Page Title"), Main(H1("Page Title"), P("Content"), cls="container")
```

### NotStr / Safe

```python
# Raw HTML (not escaped)
from fasthtml.common import NotStr
Div(NotStr("<b>Bold</b>"))  # Renders as bold

# Safe alias
from fasthtml.common import Safe
Div(Safe("<script>alert('hi')</script>"))  # Danger: use carefully!

# Common use: embed HTML from external source
df_html = dataframe.to_html()
Div(NotStr(df_html))
```

### fill_form

```python
from fasthtml.common import fill_form
from dataclasses import dataclass

@dataclass
class Profile:
    name: str
    email: str
    bio: str

form = Form(
    Input(name="name"),
    Input(name="email", type="email"),
    Textarea(name="bio"),
    Button("Save")
)

profile = Profile("Alice", "alice@ex.com", "Developer")
filled = fill_form(form, profile)  # Inputs get value attributes
```

### Script and Style

```python
# External JS
Script(src="https://unpkg.com/htmx.org")

# Inline JS
Script("console.log('Hello');")

# External CSS
Link(rel="stylesheet", href="/styles.css")

# Inline CSS
Style("""
    .container { max-width: 800px; }
    .card { padding: 1rem; }
""")
```

### MarkdownJS and HighlightJS

```python
app, rt = fast_app(hdrs=(
    MarkdownJS(),  # Client-side markdown rendering
    HighlightJS(langs=['python', 'javascript', 'html']),
))

@rt
def docs():
    return Titled("Docs",
        Div("# Hello\n\nThis is **markdown**", cls="marked"),
        Pre(Code("def hello(): pass", cls="language-python"))
    )
```
