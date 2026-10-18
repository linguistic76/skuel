"""
UID Generation Utilities
========================

Mints the generated uids of SKUEL's entities, in the uid grammar's generated shape
``{prefix}_{opaque}`` (``core/utils/uid_grammar.py``).

- Hierarchy lives in graph relationships, never in uids.
- Curriculum is never generated: a Ku, PathStep or LearningPath uid is authored in
  the content vault (``ku.{ns}.{slug}``), and no caller passes a curriculum prefix.
- ``generate_uid(prefix, name)`` still mints the named shape
  ``{prefix}_{slug}_{8 hex}`` — a ``uid_grammar.UID_EXEMPTIONS`` entry
  (``named_generated``) until the uid arc migrates it.

Examples:
- task_a1b2c3d4                 (generate_random_uid / generate_uid without a name)
- task_implement-auth_a1b2c3d4  (generate_uid with a name)

See: /docs/decisions/ADR-013-ku-uid-flat-identity.md
See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

__version__ = "1.0"


import uuid

from core.models.type_hints import EntityUID
from core.utils import uid_grammar


class UIDGenerator:
    """Generate flat uids for SKUEL's generated entities."""

    @classmethod
    def generate_random_uid(cls, prefix: str) -> EntityUID:
        """
        Generate a random uid: ``{prefix}_{8 hex}``.

        Args:
            prefix: Entity type prefix (task, goal, habit, user, askesis, etc.)

        Raises:
            ValueError: when ``prefix`` is not a lowercase word.

        Examples:
            >>> UIDGenerator.generate_random_uid("task")
            'task_a1b2c3d4'
        """
        return EntityUID(uid_grammar.generated_uid(prefix, uuid.uuid4().hex[:8]))

    @classmethod
    def generate_uid(cls, prefix: str, name: str | None = None) -> EntityUID:
        """
        General uid generation for any entity type.

        Args:
            prefix: UID prefix (e.g., "task", "er", "fs", "notif")
            name: Optional name; its slug joins the uid between prefix and suffix

        Returns:
            ``{prefix}_{8 hex}``, or ``{prefix}_{slug}_{8 hex}`` when ``name``
            slugs to anything.

        Raises:
            ValueError: when ``prefix`` is not a lowercase word.

        Examples:
            - generate_uid("task") -> "task_a1b2c3d4"
            - generate_uid("task", "implement auth") -> "task_implement-auth_a1b2c3d4"
        """
        base = uid_grammar.generated_uid(prefix, uuid.uuid4().hex[:8])
        slug = uid_grammar.slugify(name) if name else ""
        if not slug:
            return EntityUID(base)
        _, suffix = base.split("_", 1)
        return EntityUID(f"{prefix}_{slug}_{suffix}")
