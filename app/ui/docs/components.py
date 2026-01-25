"""Documentation UI components using raw Tailwind CSS.

These components replace the DaisyUI-based docs_components.py with
components built on our typography-first design system.
"""

from dataclasses import dataclass, field
from typing import Any

from fasthtml.common import H1, H2, H3, A, Details, Div, Li, P, Span, Summary, Ul

from ui.primitives.card import CardLink
from ui.primitives.layout import Grid, Row


@dataclass
class DocsSection:
    """Navigation section for documentation."""

    slug: str
    title: str
    icon: str = ""
    description: str = ""
    image: str = ""  # Image filename (relative to /data/)
    content: str = ""  # Markdown content for section page


@dataclass
class TopicInfo:
    """Topic information for rendering."""

    slug: str
    title: str
    section: str
    content: str = ""
    description: str = ""
    level: int = 4  # Heading level (2=section, 3=category, 4=topic, 5=subtopic, 6=detail)
    children: list["TopicInfo"] = field(default_factory=list)
    parent_slug: str | None = None

    @property
    def has_children(self) -> bool:
        return len(self.children) > 0


def SectionCard(
    title: str,
    slug: str,
    icon: str = "",
    description: str = "",
) -> A:
    """Card for a documentation section.

    Args:
        title: Section title
        slug: URL slug
        icon: Optional emoji icon
        description: Optional description

    Returns:
        A CardLink component
    """
    return CardLink(
        Div(icon, cls="text-4xl mb-3") if icon else None,
        H2(title, cls="text-xl font-semibold text-primary mb-2 truncate-1"),
        P(description, cls="text-sm text-base-content/70 truncate-2") if description else None,
        href=f"/docs/{slug}",
        cls="hover:border-primary",
    )


def SectionGrid(sections: list[dict[str, Any]]) -> Div:
    """Grid of section cards for the docs home page.

    Args:
        sections: List of section dicts with slug, title, icon, description

    Returns:
        A Grid of SectionCard components
    """
    cards = [
        SectionCard(
            title=s.get("title", "Section"),
            slug=s.get("slug", ""),
            icon=s.get("icon", ""),
            description=s.get("description", ""),
        )
        for s in sections
    ]
    return Grid(*cards, cols=3, gap=4)


# Section-specific color schemes for accordion cards
SECTION_COLORS: dict[str, tuple[str, str]] = {
    "stories": ("bg-amber-50", "hover:bg-amber-100"),
    "environment-sustainability-weather": ("bg-green-50", "hover:bg-green-100"),
    "intelligence-education": ("bg-blue-50", "hover:bg-blue-100"),
    "investment": ("bg-emerald-50", "hover:bg-emerald-100"),
    "words-meaning": ("bg-purple-50", "hover:bg-purple-100"),
    "relationships-communication": ("bg-pink-50", "hover:bg-pink-100"),
    "social-awareness": ("bg-cyan-50", "hover:bg-cyan-100"),
    "body-nervous-system": ("bg-red-50", "hover:bg-red-100"),
    "exercises-sm-metrics": ("bg-orange-50", "hover:bg-orange-100"),
    "self-management": ("bg-indigo-50", "hover:bg-indigo-100"),
    "who-are-u-self-awareness": ("bg-violet-50", "hover:bg-violet-100"),
}


def SectionAccordionCard(
    title: str,
    slug: str,
    icon: str = "",
    description: str = "",
    topics: list[TopicInfo] | None = None,
    base_path: str = "/nous",
) -> Details:
    """Accordion card for a documentation section with expandable topics.

    Following the finance expense categories pattern - simple text in Summary,
    let browser handle native disclosure triangle.

    Args:
        title: Section title
        slug: URL slug
        icon: Optional emoji icon
        description: Optional description
        topics: List of child topics (H3/H4 headings)
        base_path: Base URL path for links

    Returns:
        A Details element with accordion behavior
    """
    # Get color scheme for this section
    bg_color, hover_color = SECTION_COLORS.get(slug, ("bg-gray-50", "hover:bg-gray-100"))

    # Build topic links
    topic_links = []
    if topics:
        for topic in topics:
            # Create link for each topic
            topic_links.append(
                A(
                    topic.title,
                    href=f"{base_path}/{slug}/{topic.slug}",
                    cls="block w-full text-left p-2 ml-4 hover:bg-white/50 rounded transition-colors text-base-content/70 hover:text-base-content",
                )
            )
            # Also show children (H4/H5) if any
            if topic.children:
                for child in topic.children[:5]:  # Limit to first 5 children
                    topic_links.append(
                        A(
                            f"  • {child.title}",
                            href=f"{base_path}/{slug}/{child.slug}",
                            cls="block w-full text-left p-2 ml-8 hover:bg-white/50 rounded transition-colors text-sm text-base-content/50 hover:text-base-content/70",
                        )
                    )

    # Section link at the bottom
    section_link = A(
        f"View all {title} →",
        href=f"{base_path}/{slug}",
        cls="block w-full text-center p-3 mt-2 bg-white/50 hover:bg-white rounded-lg font-medium text-primary hover:text-primary-focus transition-colors",
    )

    # Simple text for Summary - matches finance pattern
    # Browser handles native disclosure triangle naturally
    summary_text = f"{icon} {title}" if icon else title

    return Details(
        Summary(
            summary_text,
            cls=f"w-full text-left p-4 {bg_color} {hover_color} rounded-lg font-semibold cursor-pointer transition-colors",
        ),
        Div(
            *topic_links,
            section_link,
            cls="mt-2 space-y-1",
        )
        if topic_links
        else Div(
            P("No topics yet", cls="text-base-content/50 italic p-4"),
            section_link,
            cls="mt-2",
        ),
        cls="mb-4",
    )


def SectionAccordionGrid(
    sections: list[dict[str, Any]],
    base_path: str = "/nous",
) -> Div:
    """Grid of accordion section cards for the nous home page.

    Args:
        sections: List of section dicts with slug, title, icon, description, topics
        base_path: Base URL path for links

    Returns:
        A Grid of SectionAccordionCard components
    """
    cards = [
        SectionAccordionCard(
            title=s.get("title", "Section"),
            slug=s.get("slug", ""),
            icon=s.get("icon", ""),
            description=s.get("description", ""),
            topics=s.get("topics", []),
            base_path=base_path,
        )
        for s in sections
    ]
    # Use a 2-column grid for better accordion display
    return Div(*cards, cls="grid grid-cols-1 md:grid-cols-2 gap-4")


def TopicList(topics: list[TopicInfo], section_title: str = "") -> Div:
    """List of topics within a section.

    Args:
        topics: List of TopicInfo objects
        section_title: Title of the section (for context)

    Returns:
        A Ul element with topic links
    """
    if not topics:
        return EmptyTopics()

    items = [
        Li(
            A(
                Row(
                    Span("", cls="text-primary"),
                    Div(
                        Div(topic.title, cls="font-medium text-base-content"),
                        Div(topic.description, cls="text-sm text-base-content/50")
                        if topic.description
                        else None,
                    ),
                    gap=3,
                ),
                href=f"/docs/{topic.section}/{topic.slug}",
                cls="flex items-center gap-3 p-3 rounded-lg hover:bg-base-200 transition-colors",
            )
        )
        for topic in topics
    ]

    return Ul(*items, cls="space-y-1")


def TopicContent(
    topic: TopicInfo,
    rendered_html: str,
    breadcrumbs: list[tuple[str, str]] | None = None,
) -> Div:
    """Full topic page content.

    Args:
        topic: TopicInfo object
        rendered_html: Pre-rendered markdown HTML
        breadcrumbs: Optional breadcrumb path

    Returns:
        A Div with the topic content
    """
    content = []

    if breadcrumbs:
        content.append(Breadcrumbs(breadcrumbs))

    # Header
    header_content = [
        H1(topic.title, cls="text-4xl font-bold tracking-tight text-base-content mb-2")
    ]
    if topic.description:
        header_content.append(P(topic.description, cls="text-xl text-base-content/70"))
    content.append(Div(*header_content, cls="mb-8"))

    # Rendered markdown content
    from fasthtml.common import NotStr

    content.append(Div(NotStr(rendered_html), cls="prose prose-lg max-w-none"))

    # Related topics placeholder
    content.append(
        Div(
            H3("Related Topics", cls="text-lg font-semibold text-base-content mb-4"),
            P("Related topics coming soon...", cls="text-base-content/50 italic"),
            cls="mt-12 pt-8 border-t border-base-300",
        )
    )

    return Div(*content)


def SectionHeader(
    title: str,
    description: str = "",
    icon: str = "",
    breadcrumbs: list[tuple[str, str]] | None = None,
) -> Div:
    """Section header with title, description, and optional breadcrumbs.

    Args:
        title: Section title
        description: Section description
        icon: Optional emoji icon
        breadcrumbs: Optional breadcrumb path

    Returns:
        A Div with the header content
    """
    content = []

    if breadcrumbs:
        content.append(Breadcrumbs(breadcrumbs))

    # Title row with optional icon
    title_content = []
    if icon:
        title_content.append(Span(icon, cls="text-5xl mr-4"))
    title_content.append(H1(title, cls="text-4xl font-bold tracking-tight text-base-content"))

    content.append(Row(*title_content, align="items-center", cls="mb-2"))

    if description:
        content.append(P(description, cls="text-xl text-base-content/70"))

    return Div(*content, cls="mb-8")


def HomeHero() -> Div:
    """Hero section for the documentation home page.

    Returns:
        A Div with the hero content
    """
    return Div(
        Div(
            Div(
                H1(
                    "Worldview Documentation",
                    cls="text-5xl font-bold tracking-tight text-base-content",
                ),
                P(
                    "Explore topics that form the basis of content and worldview. "
                    "From foundational stories to self-awareness practices.",
                    cls="py-6 text-lg text-base-content/70",
                ),
                cls="max-w-2xl",
            ),
            cls="text-center py-12",
        ),
        cls="bg-base-100 rounded-lg mb-8 border border-base-200",
    )


def Breadcrumbs(path: list[tuple[str, str]]) -> Div:
    """Breadcrumb navigation.

    Args:
        path: List of (label, href) tuples. Empty href means current page.

    Returns:
        A Div with breadcrumb links
    """
    if not path:
        return Div()

    items = []
    for i, (label, href) in enumerate(path):
        if i > 0:
            items.append(Span("/", cls="text-base-content/50 mx-2"))

        if href:
            items.append(A(label, href=href, cls="text-primary hover:underline"))
        else:
            items.append(Span(label, cls="text-base-content/50"))

    return Div(*items, cls="flex items-center text-sm mb-6")


def EmptyTopics() -> Div:
    """Empty state for when there are no topics.

    Returns:
        A Div with the empty message
    """
    return Div(
        Div(
            Span("", cls="text-4xl mb-4 block"),
            P("No topics available in this section yet.", cls="text-base-content/70"),
        ),
        cls="bg-info/10 border border-info/20 rounded-lg p-6 text-center",
    )


## StubContent DELETED (January 2026) - Per One Path Forward
# Use ContentPending instead for honest status reporting


def ContentPending(title: str, ku_uid: str) -> Div:
    """Honest status display when KU content has not been written yet.

    SKUEL Philosophy: One path forward, honest status reporting.
    KU is THE content source. If it doesn't exist, we say so clearly.

    Args:
        title: Topic title
        ku_uid: Expected KU uid (e.g., "ku:machine-learning")

    Returns:
        A Div with clear status and guidance for content creators
    """
    return Div(
        # Status banner - honest, not apologetic
        Div(
            Div(
                Span("Content not yet written", cls="font-medium"),
                cls="flex items-center",
            ),
            cls="bg-base-200 border border-base-300 rounded-lg p-4 mb-6",
        ),
        # Clear explanation
        P(
            "This topic exists in the navigation structure but the Knowledge Unit (KU) ",
            "content has not been created yet.",
            cls="text-base-content/70 mb-6",
        ),
        # For content creators
        Div(
            H3("For Content Creators", cls="text-lg font-semibold text-base-content mb-3"),
            P(
                "To add content for this topic, create a KU with uid: ",
                Span(ku_uid, cls="font-mono bg-base-300 px-2 py-1 rounded text-sm"),
                cls="text-base-content/70 mb-2",
            ),
            P(
                "The KU title should be: ",
                Span(title, cls="font-semibold"),
                cls="text-base-content/70",
            ),
            cls="bg-base-300/50 rounded-lg p-4",
        ),
    )
