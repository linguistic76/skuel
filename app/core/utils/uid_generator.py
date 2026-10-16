"""
UID Generation Utilities
========================

UID generation for SKUEL entities with consistent naming conventions.

UID Format Rules (Universal Hierarchical Pattern):
- Generated UIDs: {type}_{identifier}_{random} or {type}_{random} (underscore separator)
- Hierarchy stored in graph relationships, NEVER in UIDs
- Curriculum is never generated: a Ku, PathStep or LearningPath uid is authored in
  the content vault (``ku.{ns}.{slug}``), and no caller passes a curriculum prefix

Examples:
- task_implement-auth_a1b2c3d4    (Task - flat UID)
- goal_complete-project_x7y8z9w0  (Goal - flat UID)
- habit_daily-exercise_abc12345   (Habit - flat UID)
- user_mike                        (User - no random suffix for named entities)

See: /docs/decisions/ADR-013-ku-uid-flat-identity.md
See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

__version__ = "1.0"


import re
import uuid

from core.models.type_hints import EntityUID


class UIDGenerator:
    """
    Generate flat UIDs for SKUEL's generated entities.

    Universal Hierarchical Pattern:
    - All generated UIDs are FLAT: {type}_{name}_{random}
    - Hierarchy stored in graph relationships, NOT UIDs
    - Identity independent of location/organization

    See: /docs/decisions/ADR-013-ku-uid-flat-identity.md
    """

    @staticmethod
    def slugify(text: str) -> str:
        """
        Convert text to a URL-safe slug.

        THE canonical slugify for UID generation. Markdown links are reduced to
        their link text before slugging, so ``[Foo](https://bar)`` slugs to
        ``foo`` rather than leaking URL characters into the slug.

        Args:
            text: Input text

        Returns:
            Slugified version
        """
        # Reduce markdown links to their link text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # Convert to lowercase
        text = text.lower()

        # Replace spaces, underscores, and special chars with hyphens.
        # Underscores fold into the hyphen collapse (not the drop class): the
        # separator grammar reserves `_` for generated-UID segment boundaries,
        # so a title's underscores must become hyphens, never survive into the
        # slug ("active_listening" → "active-listening").
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[-_\s]+", "-", text)

        # Remove leading/trailing hyphens
        return text.strip("-")

    @classmethod
    def generate_random_uid(cls, prefix: str) -> EntityUID:
        """
        Generate a random UID for non-hierarchical entities.

        Uses underscore notation for activity domains and infrastructure entities.

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
        return EntityUID(f"{prefix}_{random_part}")

    # REMOVED (2026-01-30 Universal Hierarchical Pattern):
    # - extract_parts() - No longer needed (UIDs are flat, not hierarchical)
    # - get_parent_uid() - No longer needed (parent via ORGANIZES relationship)
    # - get_domain_from_uid() - No longer needed (domain not encoded in UID)
    #
    # Hierarchy is now stored in graph relationships:
    # - (parent:Entity)-[:ORGANIZES {order}]->(child:Entity)
    # - PathStep subjects: PsService.find_organizers() / get_organized_children()
    # - UserEntry subjects: UserEntryService.get_organized_children()
    # - Other entity types: no dedicated reader; edges are authored by vault MOC
    #   ingestion or written with UnifiedRelationshipService.add_relationship()
    #
    # See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md

    @classmethod
    def generate_uid(cls, prefix: str, name: str | None = None) -> EntityUID:
        """
        General UID generation for any entity type.

        Args:
            prefix: UID prefix (e.g., "task", "er", "fs", "notif")
            name: Optional name for semantic UIDs

        Returns:
            Generated UID.

        Examples:
            - generate_uid("task") -> "task_a1b2c3d4"
            - generate_uid("task", "implement auth") -> "task_implement-auth_a1b2"
        """
        # Generate short random suffix
        random_suffix = uuid.uuid4().hex[:8]

        if name:
            # Create semantic UID with slugified name
            slug = cls.slugify(name)
            return EntityUID(f"{prefix}_{slug}_{random_suffix}")
        else:
            # Simple random UID
            return EntityUID(f"{prefix}_{random_suffix}")
