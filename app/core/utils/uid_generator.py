"""
UID Generation Utilities
========================

Hierarchical UID generation for knowledge units and domains.
UIDs follow a semantic structure: prefix.domain.parent.slug

Examples:
- ku.yoga.meditation       (Knowledge Unit)
- dom.technology          (Domain)
- path.beginner.python    (Learning Path)
"""

__version__ = "1.0"


import re
import uuid
from typing import Any


class UIDGenerator:
    """
    Generate hierarchical UIDs for knowledge entities.

    UIDs follow patterns that make relationships clear:
    - ku.domain.topic.subtopic
    - dom.domain.subdomain
    - path.level.subject
    """

    # Prefixes for different entity types
    KNOWLEDGE_PREFIX = "ku"
    DOMAIN_PREFIX = "dom"
    PATH_PREFIX = "path"
    CONTENT_PREFIX = "content"

    @staticmethod
    def slugify(text: str) -> str:
        """
        Convert text to a URL-safe slug.

        Args:
            text: Input text

        Returns:
            Slugified version
        """
        # Convert to lowercase
        text = text.lower()

        # Replace spaces and special chars with hyphens
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[-\s]+", "-", text)

        # Remove leading/trailing hyphens
        return text.strip("-")

    @classmethod
    def generate_knowledge_uid(
        cls, title: str, parent_uid: str | None = None, domain_uid: str | None = None
    ) -> str:
        """
        Generate a knowledge unit UID.

        Args:
            title: Knowledge unit title,
            parent_uid: Parent unit's UID (for hierarchy),
            domain_uid: Domain UID (for categorization)

        Returns:
            Hierarchical UID,

        Examples:
            - ku.yoga.meditation-basics
            - ku.tech.python.functions
        """
        slug = cls.slugify(title)

        # Build hierarchical UID
        parts = [cls.KNOWLEDGE_PREFIX]

        # Add domain if provided
        if domain_uid:
            # Extract domain part (remove 'dom.' prefix)
            domain_part = domain_uid.replace(f"{cls.DOMAIN_PREFIX}.", "")
            parts.append(domain_part)

        # Add parent hierarchy if provided
        if parent_uid:
            # Extract parent parts (remove prefix)
            parent_parts = parent_uid.split(".")[1:]  # Skip prefix
            # Don't duplicate domain if already added
            if domain_uid and parent_parts and parent_parts[0] == domain_part:
                parent_parts = parent_parts[1:]
            if parent_parts:
                parts.extend(parent_parts)

        # Add the slug
        parts.append(slug)

        return ".".join(parts)

    @classmethod
    def generate_domain_uid(cls, name: str, parent_domain_uid: str | None = None) -> str:
        """
        Generate a domain UID.

        Args:
            name: Domain name,
            parent_domain_uid: Parent domain's UID

        Returns:
            Domain UID,

        Examples:
            - dom.technology
            - dom.technology.programming
        """
        slug = cls.slugify(name)

        if parent_domain_uid:
            # Append to parent hierarchy
            return f"{parent_domain_uid}.{slug}"
        else:
            # Root domain
            return f"{cls.DOMAIN_PREFIX}.{slug}"

    @classmethod
    def generate_content_uid(cls, unit_uid: str) -> str:
        """
        Generate a content UID for a knowledge unit.

        Args:
            unit_uid: The knowledge unit's UID

        Returns:
            Content UID
        """
        # Replace ku. prefix with content.
        if unit_uid.startswith(cls.KNOWLEDGE_PREFIX + "."):
            return unit_uid.replace(cls.KNOWLEDGE_PREFIX + ".", cls.CONTENT_PREFIX + ".")
        return f"{cls.CONTENT_PREFIX}.{unit_uid}"

    @classmethod
    def generate_path_uid(cls, name: str, level: str | None = None) -> str:
        """
        Generate a learning path UID.

        Args:
            name: Path name,
            level: Skill level (beginner, intermediate, advanced)

        Returns:
            Path UID,

        Examples:
            - path.beginner.python-basics
            - path.advanced.machine-learning
        """
        slug = cls.slugify(name)

        if level:
            return f"{cls.PATH_PREFIX}.{level}.{slug}"
        return f"{cls.PATH_PREFIX}.{slug}"

    @classmethod
    def generate_random_uid(cls, prefix: str = "ku") -> str:
        """
        Generate a random UID when hierarchy isn't important.

        Args:
            prefix: Entity type prefix

        Returns:
            Random UID with prefix
        """
        random_part = uuid.uuid4().hex[:8]
        return f"{prefix}.{random_part}"

    @staticmethod
    def extract_parts(uid: str) -> dict[str, Any]:
        """
        Extract parts from a UID.

        Args:
            uid: The UID to parse

        Returns:
            Dictionary with prefix, domain, hierarchy parts

        Example:
            'ku.yoga.meditation.basics' -> {
                'prefix': 'ku',
                'domain': 'yoga',
                'hierarchy': ['meditation'],
                'slug': 'basics'
            }
        """
        parts = uid.split(".")

        if len(parts) < 2:
            return {"prefix": uid, "domain": None, "hierarchy": [], "slug": None}

        result: dict[str, Any] = {"prefix": parts[0], "domain": None, "hierarchy": [], "slug": None}

        if len(parts) >= 2:
            result["slug"] = parts[-1]

        if len(parts) >= 3:
            result["domain"] = parts[1]

        if len(parts) > 3:
            result["hierarchy"] = parts[2:-1]

        return result

    @staticmethod
    def get_parent_uid(uid: str) -> str | None:
        """
        Get the parent UID from a hierarchical UID.

        Args:
            uid: The child UID

        Returns:
            Parent UID or None if root

        Example:
            'ku.yoga.meditation.basics' -> 'ku.yoga.meditation'
        """
        parts = uid.split(".")

        if len(parts) <= 2:
            return None

        return ".".join(parts[:-1])

    @staticmethod
    def get_domain_from_uid(uid: str) -> str | None:
        """
        Extract domain UID from a knowledge UID.

        Args:
            uid: Knowledge unit UID

        Returns:
            Domain UID

        Example:
            'ku.yoga.meditation.basics' -> 'dom.yoga'
        """
        parts = UIDGenerator.extract_parts(uid)

        if parts["domain"]:
            return f"{UIDGenerator.DOMAIN_PREFIX}.{parts['domain']}"

        return None

    @classmethod
    def generate_uid(cls, entity_type: str, name: str | None = None) -> str:
        """
        General UID generation for any entity type.

        Args:
            entity_type: Type of entity (task, event, habit, etc.)
            name: Optional name for semantic UIDs

        Returns:
            Generated UID,

        Examples:
            - generate_uid("task") -> "task_a1b2c3d4"
            - generate_uid("task", "implement auth") -> "task_implement-auth_a1b2"
        """
        # Generate short random suffix
        random_suffix = uuid.uuid4().hex[:8]

        if name:
            # Create semantic UID with slugified name
            slug = cls.slugify(name)
            return f"{entity_type}_{slug}_{random_suffix}"
        else:
            # Simple random UID
            return f"{entity_type}_{random_suffix}"
