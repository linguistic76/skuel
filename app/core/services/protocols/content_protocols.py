"""
Content Protocols
=================

Defines clear protocol interfaces for content objects used in learning services.
This eliminates the need for hasattr checks by ensuring all content conforms to these protocols.
"""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ContentItem(Protocol):
    """Protocol for any content item in the learning system."""

    uid: str
    title: str
    content_type: str
    tags: list[str]
    difficulty: str  # "beginner", "intermediate", "advanced"
    estimated_time: int  # minutes
    prerequisites: list[str]  # UIDs of prerequisite content

    def __str__(self) -> str:
        """String representation of content."""
        ...


@dataclass
class ContentAdapter:
    """
    Adapter to ensure any content object conforms to ContentItem protocol.

    This provides safe defaults for missing attributes using getattr,
    which is the proper way to check for attributes dynamically.
    """

    def __init__(self, content: Any) -> None:
        """Wrap any content object with safe access."""
        self._content = content

    @property
    def uid(self) -> str:
        """Get UID with fallback."""
        return getattr(self._content, "uid", str(self._content))

    @property
    def title(self) -> str:
        """Get title with fallback."""
        title = getattr(self._content, "title", None)
        if title is not None:
            return title
        name = getattr(self._content, "name", None)
        if name is not None:
            return name
        return str(self._content)

    @property
    def content_type(self) -> str:
        """Get content type with fallback."""
        ctype = getattr(self._content, "content_type", None)
        if ctype is not None:
            return ctype
        type_val = getattr(self._content, "type", None)
        if type_val is not None:
            return type_val
        return "unknown"

    @property
    def tags(self) -> list[str]:
        """Get tags with fallback."""
        tags = getattr(self._content, "tags", None)
        return tags if tags else []

    @property
    def difficulty(self) -> str:
        """Get difficulty with fallback."""
        difficulty = getattr(self._content, "difficulty", None)
        if difficulty is not None:
            return difficulty

        level = getattr(self._content, "level", None)
        if level is not None:
            if isinstance(level, int | float):
                if level <= 2:
                    return "beginner"
                elif level <= 4:
                    return "intermediate"
                else:
                    return "advanced"
            return str(level).lower()
        return "intermediate"

    @property
    def estimated_time(self) -> int:
        """Get estimated time with fallback."""
        est_time = getattr(self._content, "estimated_time", None)
        if est_time is not None:
            return est_time

        est_time_min = getattr(self._content, "estimated_time_minutes", None)
        if est_time_min is not None:
            return est_time_min

        duration = getattr(self._content, "duration", None)
        if duration is not None:
            return duration

        return 30  # Default 30 minutes

    @property
    def prerequisites(self) -> list[str]:
        """Get prerequisites with fallback."""
        prereqs = getattr(self._content, "prerequisites", None)
        if prereqs:
            return prereqs

        prereq_uids = getattr(self._content, "prerequisite_uids", None)
        if prereq_uids:
            return prereq_uids

        return []

    def __str__(self) -> str:
        """String representation."""
        return self.title


def ensure_content_protocol(content: Any) -> ContentAdapter:
    """
    Ensure any content object conforms to ContentItem protocol.

    This is the recommended way to handle unknown content objects
    instead of using hasattr checks throughout the code.

    Args:
        content: Any content object

    Returns:
        ContentAdapter that conforms to ContentItem protocol
    """
    if isinstance(content, ContentAdapter):
        return content
    return ContentAdapter(content)


# Type alias for clarity
ContentItemLike = ContentItem | ContentAdapter | Any
