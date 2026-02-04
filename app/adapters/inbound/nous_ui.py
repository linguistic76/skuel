"""
Nous UI Routes - Worldview MOC Documentation Section

Serves content from the /nous directory powered by moc_nous.md.

Routes:
- /nous - Home (section grid)
- /nous/{section} - Section page (hierarchical topic list)
- /nous/{section}/{topic} - Topic detail page

Content Resolution:
- KU from Neo4j is THE content source
- UID convention: ku.{section}--{topic} (matches generate_nous_files.py format)
- If KU doesn't exist, show honest "content not written yet" status

Security:
- INTENTIONALLY PUBLIC (no authentication required)
- These are public-facing documentation/knowledge pages
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from starlette.requests import Request

from core.auth import get_current_user
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from core.utils.moc_parser import HeadingNode, MOCStructure, parse_moc_file
from ui.docs import (
    Breadcrumbs,
    ContentPending,
    DocsSection,
    EmptyTopics,
    HomeHero,
    SectionAccordionGrid,
    SectionHeader,
    TopicInfo,
    TopicList,
    create_docs_page,
)

if TYPE_CHECKING:
    from core.utils.services_bootstrap import Services

logger = get_logger("skuel.routes.nous")

# Path to the Nous MOC file
MOC_FILE_PATH = Path("/home/mike/0bsidian/skuel/nous/moc_nous.md")

# Path to nous content files
NOUS_PATH = Path("/home/mike/0bsidian/skuel/nous")

# Cached MOC structure (loaded once at startup)
_moc_cache: MOCStructure | None = None

# Cached section metadata
_section_metadata_cache: dict[str, dict[str, Any]] | None = None


def get_moc_structure() -> MOCStructure:
    """Get the cached MOC structure, loading if needed."""
    global _moc_cache
    if _moc_cache is None:
        _moc_cache = parse_moc_file(MOC_FILE_PATH)
        logger.info(f"Loaded Nous MOC: {_moc_cache.title} with {len(_moc_cache.sections)} sections")
    return _moc_cache


def load_section_metadata() -> dict[str, dict[str, Any]]:
    """Load section metadata from individual section files.

    Reads {section}.md files to get metadata for each H2 section.
    """
    global _section_metadata_cache
    if _section_metadata_cache is not None:
        return _section_metadata_cache

    _section_metadata_cache = {}
    moc = get_moc_structure()

    for section in moc.sections:
        section_file = NOUS_PATH / f"{section.slug}.md"
        if not section_file.exists():
            continue

        try:
            content = section_file.read_text(encoding="utf-8")

            # Parse YAML frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    markdown_content = parts[2].strip()

                    if frontmatter:
                        _section_metadata_cache[section.slug] = {
                            "title": frontmatter.get("title", section.title),
                            "description": frontmatter.get("description", ""),
                            "icon": frontmatter.get("icon", ""),
                            "image": frontmatter.get("image", ""),
                            "content": markdown_content,
                        }
                        logger.debug(f"Loaded section metadata: {section.slug}")
        except Exception as e:
            logger.warning(f"Failed to parse {section_file}: {e}")

    logger.info(f"Loaded {len(_section_metadata_cache)} section metadata files")
    return _section_metadata_cache


def get_section_metadata(slug: str) -> dict[str, Any] | None:
    """Get metadata for a specific section."""
    metadata = load_section_metadata()
    return metadata.get(slug)


def heading_to_topic_info(heading: HeadingNode, section_slug: str) -> TopicInfo:
    """Convert a HeadingNode to TopicInfo recursively."""
    children = [heading_to_topic_info(child, section_slug) for child in heading.children]

    return TopicInfo(
        slug=heading.slug,
        title=heading.title,
        section=section_slug,
        content=heading.content,
        description=heading.content[:100] if heading.content else "",
        level=heading.level,
        children=children,
        parent_slug=heading.parent_slug,
    )


def get_nous_sections() -> list[DocsSection]:
    """Get sections from the MOC file (H2 headings)."""
    moc = get_moc_structure()

    # Icon mapping for nous sections
    section_icons = {
        "stories": "📖",
        "environment-sustainability-weather": "🌍",
        "intelligence-education": "🧠",
        "investment": "📈",
        "words-meaning": "💬",
        "relationships-communication": "🤝",
        "social-awareness": "👥",
        "body-nervous-system": "🧬",
        "exercises-sm-metrics": "🏃",
        "self-management": "⚙️",
        "who-are-u-self-awareness": "🪞",
    }

    sections = []
    for heading in moc.sections:
        # Try to get metadata from section file
        metadata = get_section_metadata(heading.slug)

        if metadata:
            sections.append(
                DocsSection(
                    slug=heading.slug,
                    title=metadata.get("title", heading.title),
                    icon=metadata.get("icon", section_icons.get(heading.slug, "📄")),
                    description=metadata.get("description", ""),
                    image=metadata.get("image", ""),
                    content=metadata.get("content", ""),
                )
            )
        else:
            icon = section_icons.get(heading.slug, "📄")
            description = heading.content[:100] if heading.content else f"Explore {heading.title}"

            sections.append(
                DocsSection(
                    slug=heading.slug,
                    title=heading.title,
                    icon=icon,
                    description=description,
                )
            )

    return sections


def get_topics_for_section(section_slug: str) -> list[TopicInfo]:
    """Get hierarchical topics for a section from the MOC."""
    moc = get_moc_structure()

    section = moc.get_section(section_slug)
    if not section:
        return []

    # Convert children (H3, H4, etc.) to TopicInfo hierarchy
    return [heading_to_topic_info(child, section_slug) for child in section.children]


def find_topic_by_slug(topics: list[TopicInfo], slug: str) -> TopicInfo | None:
    """Recursively find a topic by slug in the hierarchy."""
    for topic in topics:
        if topic.slug == slug:
            return topic
        if topic.children:
            found = find_topic_by_slug(topic.children, slug)
            if found:
                return found
    return None


def get_section_by_slug(slug: str) -> DocsSection | None:
    """Get a section by its slug."""
    for section in get_nous_sections():
        if section.slug == slug:
            return section
    return None


def get_topic(section_slug: str, topic_slug: str) -> TopicInfo | None:
    """Get a specific topic by section and topic slug."""
    topics = get_topics_for_section(section_slug)
    return find_topic_by_slug(topics, topic_slug)


async def get_ku_content(
    services: "Services", section_slug: str, topic_slug: str
) -> tuple[str | None, str]:
    """
    Query KU from Neo4j by section and topic slug.

    Content Resolution: Uses ku.{section}--{topic} format matching generated files.

    Args:
        services: Services container with ku service
        section_slug: Section slug from MOC (e.g., "stories")
        topic_slug: Topic slug from MOC (e.g., "original-sin")

    Returns:
        Tuple of (content, source) where:
        - content: Markdown content if KU found, None otherwise
        - source: "neo4j" if from KU, "not_found" otherwise
    """
    if not services or not services.ku:
        logger.debug("KU service not available, skipping Neo4j query")
        return None, "service_unavailable"

    # Convention: section--topic format matching generate_nous_files.py
    ku_uid = f"ku.{section_slug}--{topic_slug}"

    try:
        result = await services.ku.get(ku_uid)  # type: ignore[union-attr]

        if result.is_ok and result.value:
            ku_dto = result.value
            content = ku_dto.content if ku_dto.content else None
            if content:
                logger.info(f"KU content found for {ku_uid}: {len(content)} chars")
                return content, "neo4j"
            else:
                logger.debug(f"KU {ku_uid} exists but has no content")
                return None, "empty_ku"
        else:
            logger.debug(f"KU not found: {ku_uid}")
            return None, "not_found"

    except Exception as e:
        logger.warning(f"Error querying KU {ku_uid}: {e}")
        return None, "error"


def create_nous_ui_routes(app: Any, rt: Any, ku_service: Any) -> list[Any]:
    """
    Create nous UI routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        ku_service: KU service for Neo4j queries

    Returns:
        List of created routes
    """
    routes: list[Any] = []

    # Create a simple services-like object for backward compatibility
    class ServicesLike:
        def __init__(self, ku) -> None:
            self.ku = ku

    services = ServicesLike(ku_service)

    async def nous_home_impl(_request: Request) -> Any:
        """Nous home - accordion section grid with expandable topics."""
        from fasthtml.common import H2, Div

        logger.info("Nous home page accessed")

        sections = get_nous_sections()

        # Build sections data with topics for accordion display
        sections_data = []
        for s in sections:
            topics = get_topics_for_section(s.slug)
            sections_data.append(
                {
                    "slug": s.slug,
                    "title": s.title,
                    "icon": s.icon,
                    "description": s.description,
                    "topics": topics,  # Include child topics for accordion
                }
            )

        content = Div(
            HomeHero(),
            H2(
                "Explore Topics", cls="text-2xl font-semibold tracking-tight text-base-content mb-6"
            ),
            SectionAccordionGrid(sections_data, base_path="/nous"),
        )

        return create_docs_page(
            title="Nous - Worldview",
            content=content,
            active_section="",
            sections=sections,
            base_path="/nous",
            request=_request,
        )

    # Register both routes separately to avoid stacked decorator issues
    @rt("/nous")
    async def nous_home(_request: Request) -> Any:
        return await nous_home_impl(_request)

    @rt("/nous/")
    async def nous_home_slash(_request: Request) -> Any:
        return await nous_home_impl(_request)

    @rt("/nous/{section}")
    async def nous_section(_request: Request, section: str) -> Any:
        """Section page - hierarchical topic list."""
        from fasthtml.common import H2, A, Div, Img, NotStr, P

        logger.info(f"Nous section accessed: {section}")

        sections = get_nous_sections()
        section_info = get_section_by_slug(section)

        if not section_info:
            content = Div(
                Div(
                    P("Section not found.", cls="text-error"),
                    cls="bg-error/10 border border-error/20 rounded-lg p-4 mb-4",
                ),
                A(
                    "Back to Nous",
                    href="/nous",
                    cls="inline-flex px-4 py-2 bg-primary text-white rounded-lg",
                ),
            )
            return create_docs_page(
                title="Section Not Found",
                content=content,
                active_section="",
                sections=sections,
                base_path="/nous",
                request=_request,
            )

        topics = get_topics_for_section(section)

        breadcrumbs = [
            ("Nous", "/nous"),
            (section_info.title, ""),
        ]

        # Render section content if available
        section_content_html = None
        if section_info.content:
            html_content, _ = render_markdown_with_toc(section_info.content)
            section_content_html = Div(
                NotStr(html_content),
                cls="prose prose-lg max-w-none mb-8",
            )

        # Section image if specified
        section_image = None
        if section_info.image:
            section_image = Div(
                Img(
                    src=f"/data/{section_info.image}",
                    alt=section_info.title,
                    cls="rounded-lg shadow-lg max-h-64 object-cover",
                ),
                cls="mb-6",
            )

        content = Div(
            SectionHeader(
                title=section_info.title,
                description=section_info.description,
                icon=section_info.icon,
                breadcrumbs=breadcrumbs,
            ),
            section_image,
            section_content_html,
            H2("Topics", cls="text-2xl font-semibold tracking-tight text-base-content mb-4"),
            TopicList(topics, section_info.title) if topics else EmptyTopics(),
        )

        return create_docs_page(
            title=section_info.title,
            content=content,
            active_section=section,
            sections=sections,
            base_path="/nous",
            request=_request,
        )

    @rt("/nous/{section}/{topic}")
    async def nous_topic(_request: Request, section: str, topic: str) -> Any:
        """Topic detail page."""
        from fasthtml.common import H3, A, Div, NotStr, P

        logger.info(f"Nous topic accessed: {section}/{topic}")

        sections = get_nous_sections()
        section_info = get_section_by_slug(section)
        topic_info = get_topic(section, topic)

        if not section_info or not topic_info:
            content = Div(
                Div(
                    P("Topic not found.", cls="text-error"),
                    cls="bg-error/10 border border-error/20 rounded-lg p-4 mb-4",
                ),
                A(
                    "Back to Nous",
                    href="/nous",
                    cls="inline-flex px-4 py-2 bg-primary text-white rounded-lg",
                ),
            )
            return create_docs_page(
                title="Topic Not Found",
                content=content,
                active_section=section if section_info else "",
                sections=sections,
                base_path="/nous",
                request=_request,
            )

        breadcrumbs = [
            ("Nous", "/nous"),
            (section_info.title, f"/nous/{section}"),
            (topic_info.title, ""),
        ]

        # KU is THE content source
        ku_uid = f"ku.{section}--{topic}"
        ku_content, source = await get_ku_content(services, section, topic)

        # Track user view for pedagogical search (if logged in and content exists)
        user_uid = get_current_user(_request)
        ku_service = services.ku
        # KuService.interaction is always initialized - no hasattr() needed
        if user_uid and ku_content and ku_service and ku_service.interaction:  # type: ignore[union-attr]
            try:
                await ku_service.interaction.record_view(user_uid, ku_uid)  # type: ignore[union-attr]
                logger.debug(f"Recorded view: user={user_uid}, ku={ku_uid}")
            except Exception as e:
                # Non-blocking - don't fail the page if tracking fails
                logger.warning(f"Failed to record view: {e}")

        toc_html = ""
        if ku_content:
            html_content, toc_html = render_markdown_with_toc(ku_content)
            rendered_content = NotStr(html_content)
            logger.debug(f"Rendered KU content for {ku_uid} (source: {source})")
        else:
            rendered_content = ContentPending(topic_info.title, ku_uid)
            logger.debug(f"No KU content for {ku_uid} (source: {source})")

        # Show children if this topic has subtopics
        children_section = None
        if topic_info.has_children:
            children_section = Div(
                H3(
                    f"Subtopics in {topic_info.title}",
                    cls="text-lg font-semibold text-base-content mb-3",
                ),
                TopicList(topic_info.children, section_info.title),
                cls="mt-8 p-4 bg-base-200 rounded-lg",
            )

        content = Div(
            Breadcrumbs(breadcrumbs),
            Div(
                Div(
                    topic_info.title, cls="text-4xl font-bold tracking-tight text-base-content mb-2"
                ),
                P(topic_info.description, cls="text-xl text-base-content/70")
                if topic_info.description
                else None,
                cls="mb-8",
            ),
            Div(rendered_content, cls="prose prose-lg max-w-none"),
            children_section,
            Div(
                H3("Related Topics", cls="text-lg font-semibold text-base-content mb-4"),
                P("Related topics coming soon...", cls="text-base-content/50 italic"),
                cls="mt-12 pt-8 border-t border-base-300",
            ),
        )

        return create_docs_page(
            title=topic_info.title,
            content=content,
            active_section=section,
            active_topic=topic,
            toc_html=toc_html,
            sections=sections,
            base_path="/nous",
            request=_request,
        )

    # Collect all routes
    routes.extend([
        nous_home,
        nous_home_slash,
        nous_section,
        nous_topic,
    ])

    # Log startup info
    moc = get_moc_structure()
    logger.info(f"Nous UI routes registered: {len(routes)} endpoints")
    logger.info(f"   - MOC: {moc.title}")
    logger.info(f"   - Sections: {len(moc.sections)}")
    logger.info(f"   - Total headings: {len(moc.get_all_headings())}")

    return routes


__all__ = ["create_nous_ui_routes"]
