"""Page layout components for full HTML documents.

These components provide the base HTML structure for SKUEL pages,
including proper head elements for Tailwind CSS and HTMX.
"""

from typing import Any

from fasthtml.common import (
    Body,
    Div,
    Head,
    Html,
    Link,
    Main,
    Meta,
    Script,
    Title,
)


def PageHead(title: str, description: str | None = None) -> Head:
    """HTML head with Tailwind CSS, fonts, and HTMX.

    Args:
        title: Page title
        description: Optional meta description

    Returns:
        A Head element with all required assets
    """
    elements = [
        Meta(charset="UTF-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
        Title(title),
        # Local compiled Tailwind CSS
        Link(rel="stylesheet", href="/static/css/output.css"),
        # Google Fonts - Inter and JetBrains Mono
        Link(rel="preconnect", href="https://fonts.googleapis.com"),
        Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
        Link(
            rel="stylesheet",
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap",
        ),
        # HTMX for interactivity
        Script(src="https://unpkg.com/htmx.org@1.9.6/dist/htmx.min.js"),
    ]

    if description:
        elements.insert(3, Meta(name="description", content=description))

    return Head(*elements)


def PageLayout(
    title: str,
    *children: Any,
    sidebar: Any = None,
    description: str | None = None,
    dark_mode: bool = False,
    **kwargs: Any,
) -> Html:
    """Full page layout with optional sidebar.

    Args:
        title: Page title (shown in browser tab)
        *children: Main content elements
        sidebar: Optional sidebar content (rendered on the left)
        description: Optional meta description
        dark_mode: If True, applies dark mode class to body
        **kwargs: Additional attributes passed to Body

    Returns:
        A complete Html document

    Example:
        PageLayout(
            "Tasks | SKUEL",
            Container(
                PageTitle("Tasks"),
                TaskList(tasks),
            ),
            sidebar=NavigationSidebar(),
        )
    """
    full_title = f"{title} | SKUEL"
    main_cls = "flex-1 min-w-0" if sidebar else ""

    body_content = []
    if sidebar:
        body_content.append(Div(sidebar, cls="w-64 flex-shrink-0 border-r border-base-300"))
    body_content.append(Main(*children, cls=f"p-6 lg:p-8 {main_cls}".strip()))

    body_cls = "bg-base-100 text-base-content"
    if dark_mode:
        body_cls += " dark"

    # Merge with kwargs cls
    extra_cls = kwargs.pop("cls", "")
    if extra_cls:
        body_cls = f"{body_cls} {extra_cls}"

    return Html(
        PageHead(full_title, description),
        Body(
            Div(*body_content, cls="flex min-h-screen"),
            cls=body_cls,
            **kwargs,
        ),
    )


def SimplePageLayout(
    title: str,
    *children: Any,
    description: str | None = None,
    dark_mode: bool = False,
    **kwargs: Any,
) -> Html:
    """Simple page layout without sidebar.

    A convenience wrapper around PageLayout for pages that don't need
    a sidebar.

    Args:
        title: Page title (shown in browser tab)
        *children: Main content elements
        description: Optional meta description
        dark_mode: If True, applies dark mode class to body
        **kwargs: Additional attributes passed to Body

    Returns:
        A complete Html document
    """
    return PageLayout(
        title,
        *children,
        sidebar=None,
        description=description,
        dark_mode=dark_mode,
        **kwargs,
    )
