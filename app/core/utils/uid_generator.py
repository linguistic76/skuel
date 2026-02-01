"""
UID Generation Utilities
========================

UID generation for SKUEL entities with consistent naming conventions.

UID Format Rules (2026-01-30 Universal Hierarchical Pattern):
- ALL domains: {type}_{identifier}_{random} (underscore separator)
- Hierarchy stored in graph relationships, NEVER in UIDs

Examples:
- task_implement-auth_a1b2c3d4    (Task - flat UID)
- goal_complete-project_x7y8z9w0  (Goal - flat UID)
- ku_meditation-basics_def45678   (Knowledge Unit - NOW FLAT!)
- habit_daily-exercise_abc12345   (Habit - flat UID)
- user_mike                        (User - no random suffix for named entities)

See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
See: /docs/migrations/UNIVERSAL_HIERARCHICAL_IMPLEMENTATION_2026-01-30.md
"""

__version__ = "1.0"


import re
import uuid


class UIDGenerator:
    """
    Generate flat UIDs for all SKUEL entities.

    Universal Hierarchical Pattern (2026-01-30):
    - All UIDs are FLAT: {type}_{name}_{random}
    - Hierarchy stored in graph relationships, NOT UIDs
    - Identity independent of location/organization

    See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
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
    def generate_knowledge_uid(cls, title: str) -> str:
        """
        Generate a flat knowledge unit UID.

        Universal Hierarchical Pattern: UIDs are FLAT, hierarchy is in
        ORGANIZES relationships. Identity is independent of location.

        Args:
            title: Knowledge unit title

        Returns:
            Flat UID with format: ku_{slug}_{random}

        Examples:
            >>> generate_knowledge_uid("Meditation Basics")
            'ku_meditation-basics_a1b2c3d4'
            >>> generate_knowledge_uid("Python Functions")
            'ku_python-functions_x7y8z9w0'

        Note:
            - Hierarchy stored in (ku)-[:ORGANIZES]->(ku) relationships
            - Use KuCoreService.organize_ku() to create parent-child relationships
            - See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
        """
        slug = cls.slugify(title)
        random_suffix = uuid.uuid4().hex[:8]
        return f"{cls.KNOWLEDGE_PREFIX}_{slug}_{random_suffix}"

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
        Generate a random UID for non-hierarchical entities.

        Uses underscore notation for activity domains and infrastructure entities.
        Curriculum entities (ku, dom, path, ls) should use their specialized
        generators (generate_knowledge_uid, generate_domain_uid, generate_path_uid).

        Args:
            prefix: Entity type prefix (task, goal, habit, user, askesis, etc.)

        Returns:
            Random UID with underscore separator: {prefix}_{random}

        Examples:
            >>> UIDGenerator.generate_random_uid("task")
            'task_a1b2c3d4'
            >>> UIDGenerator.generate_random_uid("goal")
            'goal_x7y8z9w0'

        Note:
            Changed from dot (.) to underscore (_) notation as of 2026-01-30.
            See: /docs/migrations/UID_STANDARDIZATION_MIGRATION_2026-01-30.md
        """
        random_part = uuid.uuid4().hex[:8]
        return f"{prefix}_{random_part}"

    # REMOVED (2026-01-30 Universal Hierarchical Pattern):
    # - extract_parts() - No longer needed (UIDs are flat, not hierarchical)
    # - get_parent_uid() - No longer needed (parent via ORGANIZES relationship)
    # - get_domain_from_uid() - No longer needed (domain not encoded in UID)
    #
    # Hierarchy is now stored in graph relationships:
    # - (parent:Ku)-[:ORGANIZES {order}]->(child:Ku)
    # - Use KuCoreService.get_parent_kus() to find parents
    # - Use KuCoreService.get_ku_hierarchy() for full hierarchy context
    #
    # See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md

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
