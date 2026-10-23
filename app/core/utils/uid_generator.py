"""
UID Generation Utilities
========================

Mints the random generated uids of SKUEL's entities, in the uid grammar's one
generated shape ``{prefix}_{16 hex}`` (``core/utils/uid_grammar.py``).

- Hierarchy lives in graph relationships, never in uids.
- Curriculum is never generated: a Ku, PathStep or LearningPath uid is authored in
  the content vault (``ku.{ns}.{slug}``), and no caller passes a curriculum prefix.
- A uid derived from the parts that identify its node is ``uid_grammar.hashed_uid``;
  the same shape, with a hash where this one has random hex.

Example: ``task_3f9a0c41d2e87b65``

See: /docs/decisions/ADR-013-ku-uid-flat-identity.md
See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

__version__ = "2.0"


import secrets

from core.models.type_hints import EntityUID
from core.utils import uid_grammar


class UIDGenerator:
    """Generate random uids for SKUEL's generated entities."""

    @classmethod
    def generate_random_uid(cls, prefix: str) -> EntityUID:
        """
        Generate a random uid: ``{prefix}_{16 hex}``, 64 random bits.

        Args:
            prefix: Entity type prefix (task, goal, habit, auth, session, etc.)

        Raises:
            ValueError: when ``prefix`` is not a lowercase word.

        Examples:
            >>> UIDGenerator.generate_random_uid("task")  # doctest: +SKIP
            'task_3f9a0c41d2e87b65'
        """
        opaque = secrets.token_hex(uid_grammar.OPAQUE_HEX // 2)
        return EntityUID(uid_grammar.generated_uid(prefix, opaque))
