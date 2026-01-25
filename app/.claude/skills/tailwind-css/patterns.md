# Tailwind CSS UI Patterns

This document shows UI patterns in both HTML and FastHTML (Python). For patterns, prefer **MonsterUI components first**, then DaisyUI, then raw Tailwind utilities.

**See:** [decision-guide.md](decision-guide.md) for when to use each layer.

---

## Navigation

### Simple Navbar

```html
<nav class="bg-white shadow">
  <div class="max-w-7xl mx-auto px-4">
    <div class="flex items-center justify-between h-16">
      <!-- Logo -->
      <a href="/" class="text-xl font-bold text-gray-900">Brand</a>

      <!-- Links -->
      <div class="hidden md:flex items-center gap-6">
        <a href="#" class="text-gray-600 hover:text-gray-900">Home</a>
        <a href="#" class="text-gray-600 hover:text-gray-900">Features</a>
        <a href="#" class="text-gray-600 hover:text-gray-900">Pricing</a>
        <a href="#" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
          Get Started
        </a>
      </div>

      <!-- Mobile menu button -->
      <button class="md:hidden p-2 rounded-lg hover:bg-gray-100">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
        </svg>
      </button>
    </div>
  </div>
</nav>
```

### Sidebar Navigation

```html
<aside class="w-64 bg-gray-900 text-white min-h-screen">
  <div class="p-4">
    <h1 class="text-xl font-bold mb-8">Dashboard</h1>
    <nav class="space-y-2">
      <a href="#" class="flex items-center gap-3 px-4 py-2 rounded-lg bg-gray-800 text-white">
        <svg class="w-5 h-5"><!-- icon --></svg>
        Home
      </a>
      <a href="#" class="flex items-center gap-3 px-4 py-2 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-white">
        <svg class="w-5 h-5"><!-- icon --></svg>
        Analytics
      </a>
      <a href="#" class="flex items-center gap-3 px-4 py-2 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-white">
        <svg class="w-5 h-5"><!-- icon --></svg>
        Settings
      </a>
    </nav>
  </div>
</aside>
```

## Cards

### Basic Card

```html
<div class="bg-white rounded-lg shadow-md p-6">
  <h3 class="text-lg font-semibold text-gray-900 mb-2">Card Title</h3>
  <p class="text-gray-600">Card description goes here with some explanatory text.</p>
</div>
```

### Card with Image

```html
<article class="bg-white rounded-xl shadow-md overflow-hidden">
  <img src="image.jpg" alt="" class="w-full h-48 object-cover">
  <div class="p-6">
    <span class="text-xs font-semibold text-blue-600 uppercase tracking-wide">Category</span>
    <h3 class="mt-2 text-xl font-semibold text-gray-900">Article Title</h3>
    <p class="mt-2 text-gray-600">Brief description of the article content...</p>
    <div class="mt-4 flex items-center">
      <img src="avatar.jpg" alt="" class="w-10 h-10 rounded-full">
      <div class="ml-3">
        <p class="text-sm font-medium text-gray-900">Author Name</p>
        <p class="text-sm text-gray-500">Jan 5, 2026</p>
      </div>
    </div>
  </div>
</article>
```

### Feature Card

```html
<div class="bg-white rounded-xl shadow-md p-6 hover:shadow-lg transition-shadow">
  <div class="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mb-4">
    <svg class="w-6 h-6 text-blue-600"><!-- icon --></svg>
  </div>
  <h3 class="text-lg font-semibold text-gray-900 mb-2">Feature Name</h3>
  <p class="text-gray-600">Explanation of what this feature does and why it matters.</p>
  <a href="#" class="mt-4 inline-flex items-center text-blue-600 hover:text-blue-700">
    Learn more
    <svg class="w-4 h-4 ml-1"><!-- arrow icon --></svg>
  </a>
</div>
```

## Forms

### Login Form

```html
<form class="max-w-md mx-auto bg-white rounded-xl shadow-md p-8">
  <h2 class="text-2xl font-bold text-center mb-6">Sign In</h2>

  <div class="space-y-4">
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
      <input type="email"
        class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
        placeholder="you@example.com">
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
      <input type="password"
        class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
        placeholder="Enter your password">
    </div>

    <div class="flex items-center justify-between">
      <label class="flex items-center">
        <input type="checkbox" class="w-4 h-4 text-blue-600 border-gray-300 rounded">
        <span class="ml-2 text-sm text-gray-600">Remember me</span>
      </label>
      <a href="#" class="text-sm text-blue-600 hover:text-blue-700">Forgot password?</a>
    </div>

    <button type="submit"
      class="w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition font-medium">
      Sign In
    </button>
  </div>
</form>
```

### Search Input

```html
<div class="relative">
  <input type="search"
    class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
    placeholder="Search...">
  <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400">
    <!-- search icon -->
  </svg>
</div>
```

## Lists

### Simple List

```html
<ul class="divide-y divide-gray-200 bg-white rounded-lg shadow">
  <li class="px-4 py-3 hover:bg-gray-50">
    <div class="flex items-center justify-between">
      <span class="text-gray-900">List Item 1</span>
      <span class="text-gray-500 text-sm">Detail</span>
    </div>
  </li>
  <li class="px-4 py-3 hover:bg-gray-50">
    <div class="flex items-center justify-between">
      <span class="text-gray-900">List Item 2</span>
      <span class="text-gray-500 text-sm">Detail</span>
    </div>
  </li>
</ul>
```

### Avatar List

```html
<ul class="space-y-3">
  <li class="flex items-center gap-3 p-3 bg-white rounded-lg shadow-sm">
    <img src="avatar.jpg" alt="" class="w-10 h-10 rounded-full">
    <div class="flex-1 min-w-0">
      <p class="text-sm font-medium text-gray-900 truncate">User Name</p>
      <p class="text-sm text-gray-500 truncate">user@email.com</p>
    </div>
    <button class="text-blue-600 text-sm hover:text-blue-700">View</button>
  </li>
</ul>
```

## Modals

### Modal Dialog

```html
<!-- Backdrop -->
<div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
  <!-- Modal -->
  <div class="bg-white rounded-xl shadow-xl max-w-md w-full">
    <!-- Header -->
    <div class="flex items-center justify-between p-4 border-b">
      <h3 class="text-lg font-semibold">Modal Title</h3>
      <button class="p-1 hover:bg-gray-100 rounded">
        <svg class="w-5 h-5 text-gray-500"><!-- close icon --></svg>
      </button>
    </div>

    <!-- Body -->
    <div class="p-4">
      <p class="text-gray-600">Modal content goes here...</p>
    </div>

    <!-- Footer -->
    <div class="flex justify-end gap-3 p-4 border-t bg-gray-50 rounded-b-xl">
      <button class="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg">Cancel</button>
      <button class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Confirm</button>
    </div>
  </div>
</div>
```

## Alerts

### Alert Messages

```html
<!-- Success -->
<div class="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-lg">
  <svg class="w-5 h-5 text-green-600"><!-- check icon --></svg>
  <p class="text-green-800">Success! Your changes have been saved.</p>
</div>

<!-- Warning -->
<div class="flex items-center gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
  <svg class="w-5 h-5 text-amber-600"><!-- warning icon --></svg>
  <p class="text-amber-800">Warning: This action cannot be undone.</p>
</div>

<!-- Error -->
<div class="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
  <svg class="w-5 h-5 text-red-600"><!-- error icon --></svg>
  <p class="text-red-800">Error: Something went wrong. Please try again.</p>
</div>

<!-- Info -->
<div class="flex items-center gap-3 p-4 bg-blue-50 border border-blue-200 rounded-lg">
  <svg class="w-5 h-5 text-blue-600"><!-- info icon --></svg>
  <p class="text-blue-800">Info: New features are available.</p>
</div>
```

## Badges & Tags

```html
<!-- Status badges -->
<span class="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full">Active</span>
<span class="px-2 py-1 text-xs font-medium bg-amber-100 text-amber-800 rounded-full">Pending</span>
<span class="px-2 py-1 text-xs font-medium bg-red-100 text-red-800 rounded-full">Inactive</span>

<!-- Tags -->
<div class="flex flex-wrap gap-2">
  <span class="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-full">JavaScript</span>
  <span class="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-full">React</span>
  <span class="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-full">Tailwind</span>
</div>
```

## Loading States

### Spinner

```html
<div class="flex items-center justify-center">
  <div class="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
</div>
```

### Skeleton Loading

```html
<div class="animate-pulse">
  <div class="h-4 bg-gray-200 rounded w-3/4 mb-4"></div>
  <div class="h-4 bg-gray-200 rounded w-1/2 mb-4"></div>
  <div class="h-4 bg-gray-200 rounded w-5/6"></div>
</div>
```

### Button Loading

```html
<button class="flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg" disabled>
  <svg class="w-5 h-5 animate-spin" viewBox="0 0 24 24">
    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/>
    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
  </svg>
  Loading...
</button>
```

## Tables

### Simple Table

```html
<div class="overflow-x-auto rounded-lg border border-gray-200">
  <table class="min-w-full divide-y divide-gray-200">
    <thead class="bg-gray-50">
      <tr>
        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
        <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
      </tr>
    </thead>
    <tbody class="bg-white divide-y divide-gray-200">
      <tr class="hover:bg-gray-50">
        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">Item Name</td>
        <td class="px-6 py-4 whitespace-nowrap">
          <span class="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full">Active</span>
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">Jan 5, 2026</td>
        <td class="px-6 py-4 whitespace-nowrap text-right text-sm">
          <button class="text-blue-600 hover:text-blue-700">Edit</button>
        </td>
      </tr>
    </tbody>
  </table>
</div>
```

## Hero Sections

### Centered Hero

```html
<section class="bg-gradient-to-b from-blue-50 to-white py-20">
  <div class="max-w-4xl mx-auto px-4 text-center">
    <h1 class="text-4xl md:text-5xl font-bold text-gray-900 mb-6">
      Build Better Products Faster
    </h1>
    <p class="text-xl text-gray-600 mb-8 max-w-2xl mx-auto">
      A powerful platform that helps teams collaborate, ship, and iterate on their ideas.
    </p>
    <div class="flex flex-col sm:flex-row gap-4 justify-center">
      <a href="#" class="bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition">
        Get Started Free
      </a>
      <a href="#" class="bg-white text-gray-700 px-6 py-3 rounded-lg font-medium border hover:bg-gray-50 transition">
        Learn More
      </a>
    </div>
  </div>
</section>
```

## Footer

```html
<footer class="bg-gray-900 text-gray-400 py-12">
  <div class="max-w-7xl mx-auto px-4">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-8">
      <div>
        <h3 class="text-white font-semibold mb-4">Product</h3>
        <ul class="space-y-2">
          <li><a href="#" class="hover:text-white transition">Features</a></li>
          <li><a href="#" class="hover:text-white transition">Pricing</a></li>
          <li><a href="#" class="hover:text-white transition">Security</a></li>
        </ul>
      </div>
      <div>
        <h3 class="text-white font-semibold mb-4">Company</h3>
        <ul class="space-y-2">
          <li><a href="#" class="hover:text-white transition">About</a></li>
          <li><a href="#" class="hover:text-white transition">Blog</a></li>
          <li><a href="#" class="hover:text-white transition">Careers</a></li>
        </ul>
      </div>
    </div>
    <div class="border-t border-gray-800 mt-8 pt-8 text-center">
      <p>&copy; 2026 Company. All rights reserved.</p>
    </div>
  </div>
</footer>
```

---

## FastHTML Equivalents

These examples show how to implement the above patterns using FastHTML and MonsterUI.

### Navbar (FastHTML)

```python
from fasthtml.common import *
from monsterui.all import *

def Navbar(brand: str, links: list[tuple[str, str]], cta: tuple[str, str] | None = None):
    """
    Responsive navbar with mobile menu.

    Args:
        brand: Brand name/logo text
        links: List of (text, href) tuples
        cta: Optional (text, href) for call-to-action button
    """
    return Nav(
        Div(
            # Logo
            A(brand, href="/", cls="text-xl font-bold text-gray-900 dark:text-white"),

            # Desktop links
            Div(
                *[A(text, href=href, cls="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors")
                  for text, href in links],
                Button(cta[0], cls=ButtonT.primary, onclick=f"location.href='{cta[1]}'") if cta else None,
                cls="hidden md:flex items-center gap-6"
            ),

            # Mobile menu button
            Button(
                UkIcon("menu", height=24),
                cls="md:hidden btn btn-ghost btn-square",
                **{"@click": "mobileOpen = !mobileOpen"}
            ),

            cls="flex items-center justify-between max-w-7xl mx-auto px-4 h-16"
        ),
        cls="bg-white dark:bg-gray-900 shadow-sm",
        **{"x-data": "{ mobileOpen: false }"}
    )

# Usage
Navbar(
    brand="SKUEL",
    links=[("Home", "/"), ("Features", "/features"), ("Pricing", "/pricing")],
    cta=("Get Started", "/signup")
)
```

### Card Grid (FastHTML)

```python
def CardGrid(items: list, cols: int = 3):
    """Responsive card grid using MonsterUI Grid."""
    return Grid(
        *[Card(
            H3(item.title, cls="font-semibold"),
            P(item.description, cls=TextPresets.muted_sm),
            footer=DivRAligned(
                Button("View", cls=ButtonT.outline, hx_get=f"/items/{item.id}")
            ),
            cls="hover:shadow-lg transition-shadow"
        ) for item in items],
        cols=cols,
        cls="gap-6"
    )
```

### Form with Validation (FastHTML)

```python
def ContactForm():
    """Contact form with MonsterUI components."""
    return Form(
        Card(
            H2("Contact Us", cls="text-2xl font-bold text-center mb-6"),

            Div(
                LabelInput("Name", id="name", required=True),
                LabelInput("Email", type="email", id="email", required=True),
                LabelTextarea("Message", id="message", rows="4"),

                # Custom checkbox with DaisyUI
                Label(
                    Input(type="checkbox", cls="checkbox checkbox-primary mr-2"),
                    Span("Subscribe to newsletter", cls="text-sm"),
                    cls="flex items-center cursor-pointer mt-4"
                ),

                DivRAligned(
                    Button("Send Message", type="submit", cls=(ButtonT.primary, "w-full md:w-auto"))
                ),

                cls="space-y-4"
            ),

            cls="max-w-md mx-auto p-8"
        ),
        action="/contact",
        method="post",
        hx_post="/contact",
        hx_swap="outerHTML"
    )
```

### Alert Messages (FastHTML)

```python
def Alert(message: str, variant: str = "info"):
    """
    Alert component using DaisyUI.

    Args:
        message: Alert text
        variant: "info" | "success" | "warning" | "error"
    """
    icons = {
        "info": "info",
        "success": "check-circle",
        "warning": "alert-triangle",
        "error": "x-circle"
    }
    return Div(
        UkIcon(icons.get(variant, "info"), height=20),
        Span(message),
        cls=f"alert alert-{variant} flex items-center gap-3"
    )

# Usage
Alert("Your changes have been saved!", variant="success")
Alert("Please review before proceeding.", variant="warning")
```

### Modal Dialog (FastHTML + Alpine)

```python
def Modal(trigger_text: str, title: str, content, modal_id: str = "modal"):
    """Modal using DaisyUI + Alpine.js."""
    return Div(
        # Trigger button
        Button(trigger_text, cls=ButtonT.primary, **{"@click": "open = true"}),

        # Modal backdrop + content
        Div(
            Div(
                # Header
                DivFullySpaced(
                    H3(title, cls="text-lg font-bold"),
                    Button(
                        UkIcon("x", height=20),
                        cls="btn btn-ghost btn-sm btn-circle",
                        **{"@click": "open = false"}
                    )
                ),
                # Body
                Div(content, cls="py-4"),
                # Footer
                DivRAligned(
                    Button("Cancel", cls="btn btn-ghost", **{"@click": "open = false"}),
                    Button("Confirm", cls=ButtonT.primary)
                ),
                cls="modal-box"
            ),
            # Click outside to close
            Div(cls="modal-backdrop", **{"@click": "open = false"}),
            cls="modal",
            **{"x-bind:class": "open ? 'modal-open' : ''"}
        ),
        **{"x-data": "{ open: false }"}
    )
```

### Loading States (FastHTML)

```python
# Spinner
def Spinner(size: str = "md"):
    """DaisyUI loading spinner."""
    return Span(cls=f"loading loading-spinner loading-{size}")

# Skeleton loading
def SkeletonCard():
    """Skeleton placeholder for cards."""
    return Card(
        Div(
            Div(cls="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-4"),
            Div(cls="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2 mb-4"),
            Div(cls="h-4 bg-gray-200 dark:bg-gray-700 rounded w-5/6"),
            cls="animate-pulse"
        )
    )

# Button with loading state
def LoadingButton(text: str, loading_text: str = "Loading..."):
    """Button that shows loading state."""
    return Button(
        Span(text, **{"x-show": "!loading"}),
        Span(
            Spinner("sm"),
            loading_text,
            cls="flex items-center gap-2",
            **{"x-show": "loading"}
        ),
        cls=ButtonT.primary,
        **{
            "x-data": "{ loading: false }",
            "@click": "loading = true",
            "x-bind:disabled": "loading"
        }
    )
```

### Status Badges (FastHTML)

```python
def StatusBadge(status: str):
    """Status badge using DaisyUI."""
    colors = {
        "active": "badge-success",
        "pending": "badge-warning",
        "inactive": "badge-error",
        "draft": "badge-ghost"
    }
    return Span(
        status.capitalize(),
        cls=f"badge {colors.get(status, 'badge-ghost')}"
    )

# Usage in a list
def ItemRow(item):
    return Div(
        DivFullySpaced(
            DivHStacked(
                UkIcon("file", height=16),
                Span(item.name, cls="font-medium")
            ),
            StatusBadge(item.status)
        ),
        cls="p-4 border-b hover:bg-gray-50 dark:hover:bg-gray-800"
    )
```

---

## See Also

- [SKILL.md](SKILL.md) - Core Tailwind concepts
- [fasthtml-integration.md](fasthtml-integration.md) - Complete FastHTML patterns
- [decision-guide.md](decision-guide.md) - MonsterUI vs DaisyUI vs Tailwind
- [utilities-reference.md](utilities-reference.md) - Utility class reference
