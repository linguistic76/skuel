"""Documentation UI components using the new design system."""

from ui.docs.components import (
    Breadcrumbs,
    ContentPending,
    DocsSection,
    EmptyTopics,
    HomeHero,
    SectionAccordionCard,
    SectionAccordionGrid,
    SectionCard,
    SectionGrid,
    SectionHeader,
    # StubContent DELETED January 2026 - use ContentPending
    TopicContent,
    TopicInfo,
    TopicList,
)
from ui.docs.layout import DocsLayout, create_docs_page

__all__ = [
    "Breadcrumbs",
    "ContentPending",
    # Layout
    "DocsLayout",
    # Data classes
    "DocsSection",
    "EmptyTopics",
    "HomeHero",
    "SectionAccordionCard",
    "SectionAccordionGrid",
    # Components
    "SectionCard",
    "SectionGrid",
    "SectionHeader",
    # StubContent DELETED January 2026 - use ContentPending
    "TopicContent",
    "TopicInfo",
    "TopicList",
    "create_docs_page",
]
