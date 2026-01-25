# Sidebar/Drawer Patterns

Complete reference for sidebar and drawer navigation patterns using DaisyUI.

## DaisyUI Drawer Architecture

The drawer pattern uses a **CSS-only toggle** based on a hidden checkbox:

```
┌─────────────────────────────────────────────┐
│ drawer                                       │
│  ├─ drawer-toggle (hidden checkbox)         │
│  ├─ drawer-content (main content area)      │
│  │   ├─ navbar (mobile only)                │
│  │   └─ main content                        │
│  └─ drawer-side (sidebar)                   │
│      ├─ drawer-overlay (click-to-close)     │
│      └─ menu (navigation links)             │
└─────────────────────────────────────────────┘
```

## Basic Drawer HTML

```html
<div class="drawer lg:drawer-open">
    <!-- Hidden checkbox for toggle state -->
    <input id="my-drawer" type="checkbox" class="drawer-toggle" />

    <!-- Main content area -->
    <div class="drawer-content flex flex-col">
        <!-- Mobile navbar with hamburger -->
        <div class="navbar bg-base-200 lg:hidden">
            <div class="flex-none">
                <label for="my-drawer" class="btn btn-square btn-ghost drawer-button">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M4 6h16M4 12h16M4 18h16" />
                    </svg>
                </label>
            </div>
            <div class="flex-1">
                <span class="text-xl font-bold">Page Title</span>
            </div>
        </div>

        <!-- Page content -->
        <main class="flex-1 p-6 lg:p-8 bg-base-100">
            <!-- Your content here -->
        </main>
    </div>

    <!-- Sidebar -->
    <div class="drawer-side">
        <label for="my-drawer" aria-label="close sidebar" class="drawer-overlay"></label>
        <div class="menu p-4 w-80 min-h-full bg-base-200 text-base-content">
            <!-- Sidebar header -->
            <div class="mb-6">
                <h2 class="text-2xl font-bold text-primary">Navigation</h2>
                <p class="text-sm text-base-content/70">Subtitle here</p>
            </div>

            <!-- Menu items -->
            <ul class="menu space-y-1">
                <li><a href="/overview" class="active">Overview</a></li>
                <li><a href="/section-1">Section 1</a></li>
                <li><a href="/section-2">Section 2</a></li>
            </ul>
        </div>
    </div>
</div>
```

## Key CSS Classes

| Class | Purpose |
|-------|---------|
| `drawer` | Container for drawer pattern |
| `drawer-toggle` | Hidden checkbox controlling state |
| `drawer-content` | Main content area |
| `drawer-side` | Sidebar container |
| `drawer-overlay` | Clickable overlay to close sidebar |
| `drawer-button` | Button that opens drawer (via label) |
| `lg:drawer-open` | Sidebar always visible on lg+ screens |

## MenuItem Configuration

### Dataclass

```python
@dataclass
class MenuItem:
    """Menu item for drawer sidebar."""
    title: str
    href: str
    slug: str           # For active state matching
    description: str = ""
    icon: str = ""
```

### Configuration Example

```python
menu_items = [
    MenuItem("Overview", "/sel", "overview", "Introduction to SEL"),
    MenuItem("Self Awareness", "/sel/self-awareness", "self-awareness", "Understanding emotions"),
    MenuItem("Self Management", "/sel/self-management", "self-management", "Managing reactions"),
    MenuItem("Social Awareness", "/sel/social-awareness", "social-awareness", "Empathy skills"),
]
```

## DrawerLayout Class

### Definition

```python
from dataclasses import dataclass
from typing import Any
from fasthtml.common import NotStr

@dataclass
class DrawerLayout:
    """DaisyUI Drawer layout component."""

    drawer_id: str           # Unique ID for checkbox toggle
    title: str               # Sidebar header title
    menu_items: list[MenuItem]
    active_page: str = ""    # Slug of currently active page
    subtitle: str = ""
    content_id: str = "drawer-content"
    sidebar_width: str = "w-80"
    show_footer: bool = False
    footer_content: str = ""

    def render(self, content: Any) -> NotStr:
        """Render the drawer layout with main content."""
        menu_html = self._build_menu_html()
        header_html = self._build_header_html()
        footer_html = self._build_footer_html() if self.show_footer else ""

        drawer_html = f"""
        <div class="drawer lg:drawer-open">
            <input id="{self.drawer_id}" type="checkbox" class="drawer-toggle" />

            <div class="drawer-content flex flex-col" id="{self.content_id}">
                <div class="navbar bg-base-200 lg:hidden">
                    <div class="flex-none">
                        <label for="{self.drawer_id}" class="btn btn-square btn-ghost drawer-button">
                            <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M4 6h16M4 12h16M4 18h16" />
                            </svg>
                        </label>
                    </div>
                    <div class="flex-1">
                        <span class="text-xl font-bold">{self.title}</span>
                    </div>
                </div>

                <div class="flex-1 p-6 lg:p-8 bg-base-100">
                    {content}
                </div>
            </div>

            <div class="drawer-side">
                <label for="{self.drawer_id}" aria-label="close sidebar" class="drawer-overlay"></label>
                <div class="menu p-4 {self.sidebar_width} min-h-full bg-base-200 text-base-content">
                    {header_html}
                    <ul class="menu space-y-1">
                        {menu_html}
                    </ul>
                    {footer_html}
                </div>
            </div>
        </div>
        """
        return NotStr(drawer_html)
```

### Menu Item Rendering

```python
def _build_menu_html(self) -> str:
    """Build HTML for menu items."""
    menu_items_html = []

    for item in self.menu_items:
        is_active = item.slug == self.active_page
        active_class = "active" if is_active else ""

        icon_html = f'<span class="text-xl mr-2">{item.icon}</span>' if item.icon else ""
        desc_html = f'<div class="menu-desc">{item.description}</div>' if item.description else ""

        menu_items_html.append(f"""
            <li>
                <a href="{item.href}" class="drawer-menu-item {active_class}">
                    <div class="flex items-center">
                        {icon_html}
                        <div>
                            <div class="menu-title">{item.title}</div>
                            {desc_html}
                        </div>
                    </div>
                </a>
            </li>
        """)

    return "".join(menu_items_html)
```

### Header and Footer

```python
def _build_header_html(self) -> str:
    """Build sidebar header."""
    subtitle_html = (
        f'<p class="text-sm text-base-content/70">{self.subtitle}</p>'
        if self.subtitle else ""
    )
    return f"""
        <div class="mb-6">
            <h2 class="text-2xl font-bold text-primary mb-1">{self.title}</h2>
            {subtitle_html}
        </div>
    """

def _build_footer_html(self) -> str:
    """Build sidebar footer."""
    if self.footer_content:
        return f"""
            <div class="mt-auto pt-6 border-t border-base-300">
                {self.footer_content}
            </div>
        """
    return ""
```

## Convenience Function

```python
def create_drawer_layout(
    drawer_id: str,
    title: str,
    menu_items: list[tuple[str, str, str, str]],  # (title, href, slug, description)
    active_page: str,
    content: Any,
    subtitle: str = "",
    show_footer: bool = False,
    footer_content: str = "",
) -> NotStr:
    """Create a drawer layout with minimal configuration."""
    items = [MenuItem(title=t, href=h, slug=s, description=d) for t, h, s, d in menu_items]

    layout = DrawerLayout(
        drawer_id=drawer_id,
        title=title,
        menu_items=items,
        active_page=active_page,
        subtitle=subtitle,
        show_footer=show_footer,
        footer_content=footer_content,
    )

    return layout.render(content)
```

## Custom CSS for Menu Items

```css
/* Active menu item styling */
.drawer-menu-item {
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    cursor: pointer;
    transition: all 0.2s;
    display: block;
    text-decoration: none;
    color: inherit;
}

.drawer-menu-item:hover {
    background-color: hsl(var(--b3));
}

.drawer-menu-item.active {
    background-color: hsl(var(--p) / 0.1);
    border-left: 3px solid hsl(var(--p));
    font-weight: 600;
}

.drawer-menu-item .menu-title {
    font-weight: 600;
    margin-bottom: 0.25rem;
}

.drawer-menu-item .menu-desc {
    font-size: 0.75rem;
    opacity: 0.7;
    line-height: 1.4;
}

.drawer-menu-item.active .menu-desc {
    opacity: 0.9;
}
```

## Usage in Routes

```python
from components.drawer_layout import create_drawer_layout

@rt("/sel")
async def sel_page(request):
    menu_items = [
        ("Overview", "/sel", "overview", "Introduction to SEL"),
        ("Self Awareness", "/sel/self-awareness", "self-awareness", "Understanding emotions"),
        ("Self Management", "/sel/self-management", "self-management", "Managing reactions"),
    ]

    content = Div(
        H1("Social Emotional Learning"),
        P("Welcome to the SEL section..."),
    )

    return Titled(
        "SEL",
        create_drawer_layout(
            drawer_id="sel-drawer",
            title="SEL Navigation",
            subtitle="Social Emotional Learning",
            menu_items=menu_items,
            active_page="overview",
            content=content,
        ),
    )
```

## Responsive Behavior

### lg:drawer-open

| Screen Size | Sidebar Behavior |
|-------------|------------------|
| Mobile (< lg) | Hidden, overlay when open |
| Desktop (lg+) | Always visible, inline |

### Override Always-Open

To keep sidebar toggleable on all screens:

```html
<!-- Remove lg:drawer-open for always-toggleable -->
<div class="drawer">
```

## HTMX Integration

### Content Updates Only

Update main content without touching sidebar:

```html
<div class="drawer-content" id="main-content">
    <!-- HTMX targets this area -->
</div>

<a href="/page"
   hx-get="/page"
   hx-target="#main-content"
   hx-push-url="true">
    Page Link
</a>
```

### Updating Sidebar Active State

Server returns updated sidebar HTML:

```python
@rt("/sel/{section}")
async def sel_section(request, section: str):
    # If HTMX request, return fragment
    if request.headers.get("HX-Request"):
        return create_drawer_layout(..., active_page=section, content=content)

    # Full page for direct navigation
    return full_page(...)
```

## Benefits Over Custom Implementation

| DaisyUI Drawer | Custom CSS/JS |
|----------------|---------------|
| ~90 lines | ~280 lines |
| CSS-only toggle | JavaScript required |
| Built-in responsive | Custom breakpoint logic |
| Built-in overlay | Custom overlay implementation |
| Theme-aware | Manual color management |
