"""
Documentation Components - DaisyUI + Tailwind.

Pure semantic HTML components for documentation pages.
No FrankenUI imports.
"""

from dataclasses import dataclass, field


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


class DocsComponents:
    """Documentation UI components using DaisyUI + Tailwind."""

    @staticmethod
    def render_section_grid(sections: list[dict]) -> str:
        """
        Render grid of section cards for /docs home page.

        Args:
            sections: List of section dicts with slug, title, icon, description

        Returns:
            HTML string
        """
        cards = ""
        for section in sections:
            icon = section.get("icon", "📄")
            title = section.get("title", "Section")
            slug = section.get("slug", "")
            description = section.get("description", "")

            cards += f"""
            <a href="/docs/{slug}" class="card bg-base-200 hover:bg-base-300 transition-colors cursor-pointer">
                <div class="card-body">
                    <div class="text-4xl mb-2">{icon}</div>
                    <h2 class="card-title">{title}</h2>
                    <p class="text-base-content/70">{description}</p>
                </div>
            </a>
            """

        return f"""
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {cards}
        </div>
        """

    @staticmethod
    def render_topic_list(topics: list[TopicInfo], section_title: str) -> str:
        """
        Render list of topics within a section.

        Args:
            topics: List of TopicInfo objects
            section_title: Title of the section

        Returns:
            HTML string
        """
        if not topics:
            return """
            <div class="alert alert-info">
                <span>No topics available in this section yet.</span>
            </div>
            """

        items = ""
        for topic in topics:
            items += f"""
            <li>
                <a href="/docs/{topic.section}/{topic.slug}"
                   class="flex items-center gap-3 p-3 rounded-lg hover:bg-base-200 transition-colors">
                    <span class="text-primary">📄</span>
                    <div>
                        <div class="font-medium">{topic.title}</div>
                        {f'<div class="text-sm text-base-content/60">{topic.description}</div>' if topic.description else ""}
                    </div>
                </a>
            </li>
            """

        return f"""
        <ul class="space-y-1">
            {items}
        </ul>
        """

    @staticmethod
    def render_hierarchical_topics(topics: list[TopicInfo], section_slug: str) -> str:
        """
        Render hierarchical topic navigation with nested structure.

        Shows H3->H4->H5->H6 hierarchy using collapsible sections.

        Args:
            topics: List of TopicInfo with nested children
            section_slug: Section slug for URL building

        Returns:
            HTML string with nested topic structure
        """
        if not topics:
            return """
            <div class="alert alert-info">
                <span>No topics available in this section yet.</span>
            </div>
            """

        def render_topic_item(topic: TopicInfo, depth: int = 0) -> str:
            """Recursively render a topic and its children."""
            indent_class = f"ml-{depth * 4}" if depth > 0 else ""

            # Icon based on level
            level_icons = {3: "📁", 4: "📄", 5: "📝", 6: "•"}
            icon = level_icons.get(topic.level, "📄")

            # If has children, render as collapsible
            if topic.has_children:
                children_html = "".join(
                    render_topic_item(child, depth + 1) for child in topic.children
                )

                return f"""
                <div class="collapse collapse-arrow bg-base-100 border border-base-300 mb-1 {indent_class}">
                    <input type="checkbox" class="peer" />
                    <div class="collapse-title font-medium flex items-center gap-2 py-2 min-h-0">
                        <span>{icon}</span>
                        <span>{topic.title}</span>
                        <span class="badge badge-sm badge-ghost">{len(topic.children)}</span>
                    </div>
                    <div class="collapse-content px-2">
                        {children_html}
                    </div>
                </div>
                """
            else:
                # Leaf node - render as link
                return f"""
                <div class="{indent_class} mb-1">
                    <a href="/docs/{section_slug}/{topic.slug}"
                       class="flex items-center gap-2 p-2 rounded hover:bg-base-200 transition-colors">
                        <span class="text-base-content/60">{icon}</span>
                        <span>{topic.title}</span>
                    </a>
                </div>
                """

        # Render all top-level topics
        items = "".join(render_topic_item(topic) for topic in topics)

        return f"""
        <div class="space-y-1">
            {items}
        </div>
        """

    @staticmethod
    def render_topic_accordion(topics_by_group: dict[str, list[TopicInfo]]) -> str:
        """
        Render topics grouped in accordion/collapse components.

        Args:
            topics_by_group: Dict mapping group name to list of topics

        Returns:
            HTML string
        """
        if not topics_by_group:
            return """
            <div class="alert alert-info">
                <span>No topics available yet.</span>
            </div>
            """

        accordions = ""
        for idx, (group_name, topics) in enumerate(topics_by_group.items()):
            topic_links = ""
            for topic in topics:
                topic_links += f"""
                <li>
                    <a href="/docs/{topic.section}/{topic.slug}"
                       class="block p-2 pl-4 hover:bg-base-200 rounded transition-colors">
                        {topic.title}
                    </a>
                </li>
                """

            # First item open by default
            checked = 'checked="checked"' if idx == 0 else ""

            accordions += f"""
            <div class="collapse collapse-arrow bg-base-200 mb-2">
                <input type="radio" name="topics-accordion" {checked} />
                <div class="collapse-title font-medium">
                    {group_name}
                    <span class="badge badge-sm badge-ghost ml-2">{len(topics)}</span>
                </div>
                <div class="collapse-content">
                    <ul class="space-y-1">
                        {topic_links}
                    </ul>
                </div>
            </div>
            """

        return accordions

    @staticmethod
    def render_breadcrumbs(path: list[tuple[str, str]]) -> str:
        """
        Render breadcrumb navigation.

        Args:
            path: List of (label, href) tuples

        Returns:
            HTML string
        """
        if not path:
            return ""

        items = ""
        for label, href in path:
            if href:
                items += f'<li><a href="{href}">{label}</a></li>'
            else:
                items += f"<li>{label}</li>"

        return f"""
        <div class="breadcrumbs text-sm mb-6">
            <ul>
                {items}
            </ul>
        </div>
        """

    @staticmethod
    def render_topic_content(
        topic: TopicInfo,
        rendered_html: str,
        breadcrumbs: list[tuple[str, str]] | None = None,
    ) -> str:
        """
        Render full topic page content.

        Args:
            topic: TopicInfo object
            rendered_html: Pre-rendered markdown HTML
            breadcrumbs: Optional breadcrumb path

        Returns:
            HTML string
        """
        breadcrumbs_html = DocsComponents.render_breadcrumbs(breadcrumbs) if breadcrumbs else ""

        return f"""
        {breadcrumbs_html}

        <header class="mb-8">
            <h1 class="text-4xl font-bold mb-2">{topic.title}</h1>
            {f'<p class="text-xl text-base-content/70">{topic.description}</p>' if topic.description else ""}
        </header>

        <div class="prose prose-lg max-w-none">
            {rendered_html}
        </div>

        <!-- Related Topics Stub -->
        <div class="mt-12 pt-8 border-t border-base-300">
            <h3 class="text-lg font-semibold mb-4">Related Topics</h3>
            <p class="text-base-content/60 italic">Related topics coming soon...</p>
        </div>
        """

    @staticmethod
    def render_section_header(
        title: str,
        description: str = "",
        icon: str = "",
        breadcrumbs: list[tuple[str, str]] | None = None,
    ) -> str:
        """
        Render section header with title and description.

        Args:
            title: Section title
            description: Section description
            icon: Optional emoji icon
            breadcrumbs: Optional breadcrumb path

        Returns:
            HTML string
        """
        breadcrumbs_html = DocsComponents.render_breadcrumbs(breadcrumbs) if breadcrumbs else ""
        icon_html = f'<span class="text-5xl mr-4">{icon}</span>' if icon else ""

        return f"""
        {breadcrumbs_html}

        <header class="mb-8">
            <div class="flex items-center mb-2">
                {icon_html}
                <h1 class="text-4xl font-bold">{title}</h1>
            </div>
            {f'<p class="text-xl text-base-content/70">{description}</p>' if description else ""}
        </header>
        """

    @staticmethod
    def render_home_hero() -> str:
        """Render the documentation home page hero section."""
        return """
        <div class="hero bg-base-200 rounded-box mb-8">
            <div class="hero-content text-center py-12">
                <div class="max-w-2xl">
                    <h1 class="text-5xl font-bold">Worldview Documentation</h1>
                    <p class="py-6 text-lg">
                        Explore topics that form the basis of content and worldview.
                        From foundational stories to self-awareness practices.
                    </p>
                </div>
            </div>
        </div>
        """

    @staticmethod
    def render_stub_content(title: str, section: str) -> str:
        """
        Render placeholder content for topics not yet written.

        Args:
            title: Topic title
            section: Section slug

        Returns:
            HTML string with placeholder content
        """
        return f"""
        <div class="alert alert-warning mb-6">
            <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>This topic is a placeholder. Content coming soon.</span>
        </div>

        <p>
            This is a stub for <strong>{title}</strong> in the <strong>{section}</strong> section.
        </p>

        <h2>What This Topic Covers</h2>
        <p>
            Content for this topic will explore key concepts, practical applications,
            and connections to other areas of the worldview.
        </p>

        <h2>Coming Soon</h2>
        <ul>
            <li>Detailed explanations</li>
            <li>Practical exercises</li>
            <li>Related knowledge units</li>
            <li>Further reading</li>
        </ul>
        """


__all__ = ["DocsComponents", "TopicInfo"]
