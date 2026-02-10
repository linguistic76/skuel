"""
KuDTOMixin - Conditional Ownership for Unified Ku DTOs
======================================================

Like ActivityDTOMixin but with conditional user_uid validation based on KuType:

    CURRICULUM:       user_uid must be None (shared content, admin-created)
    ASSIGNMENT:       user_uid required (student submission)
    AI_REPORT:        user_uid required (AI-derived, owned by student)
    FEEDBACK_REPORT:  user_uid required (teacher-owned feedback)

UID generation:
    CURRICULUM: ku_{slug}_{random}  (semantic UID from title)
    Others:     {userid}_ku_{type}_{random}  (user-namespaced)

The mixin handles:
- user_uid conditional validation (fail-fast per KuType)
- UID generation with correct format per KuType
- created_at/updated_at timestamp defaults

See: ActivityDTOMixin for the Activity Domain equivalent.
"""

from datetime import datetime
from typing import Any, ClassVar, Self

from core.models.enums.ku_enums import KuType


class KuDTOMixin:
    """
    Mixin providing factory methods for unified Ku DTOs with conditional ownership.

    CURRICULUM Ku are shared (no owner), all others require user_uid.

    Class Variables:
        _uid_prefix: Default prefix for generated UIDs (always "ku")
    """

    _uid_prefix: ClassVar[str] = "ku"

    @classmethod
    def _validate_ku_ownership(cls, ku_type: KuType, user_uid: str | None) -> None:
        """
        Validate user_uid based on KuType (fail-fast philosophy).

        CURRICULUM must have user_uid=None (shared content).
        All other types require user_uid (user-owned content).

        Raises:
            ValueError: If ownership doesn't match KuType requirements.
        """
        if ku_type == KuType.CURRICULUM:
            if user_uid is not None:
                raise ValueError(
                    "CURRICULUM Ku must have user_uid=None (shared content, admin-created)"
                )
        elif not user_uid:
            raise ValueError(
                f"{ku_type.value.upper()} Ku requires user_uid (user-owned content)"
            )

    @classmethod
    def _generate_ku_uid(cls, ku_type: KuType, user_uid: str | None, title: str | None = None) -> str:
        """
        Generate UID with correct format per KuType.

        CURRICULUM:  ku_{slug}_{random}  (semantic UID from title)
        Others:      {userid}_ku_{type}_{random}  (user-namespaced)

        Args:
            ku_type: Type of Ku being created
            user_uid: Owner UID (None for curriculum)
            title: Title for semantic slug (curriculum only)

        Returns:
            Generated UID string
        """
        from core.utils.uid_generator import UIDGenerator

        if ku_type == KuType.CURRICULUM:
            # Admin-created curriculum: ku_{slug}_{random}
            if title:
                return UIDGenerator.generate_knowledge_uid(title)
            return UIDGenerator.generate_random_uid("ku")

        # User-owned: {userid}_ku_{type}_{random}
        # Strip "user_" prefix if present for cleaner UIDs
        user_id = user_uid.replace("user_", "") if user_uid else "unknown"
        type_suffix = ku_type.value  # e.g., "assignment", "ai_report", "feedback_report"
        return UIDGenerator.generate_random_uid(f"{user_id}_ku_{type_suffix}")

    @classmethod
    def _create_ku_dto(
        cls,
        ku_type: KuType,
        title: str,
        user_uid: str | None = None,
        **kwargs: Any,
    ) -> Self:
        """
        Factory helper for creating Ku DTOs with conditional ownership.

        This method:
        1. Validates user_uid against ku_type (fail-fast)
        2. Generates a UID if not provided in kwargs
        3. Sets created_at/updated_at to now if not provided

        Args:
            ku_type: Type of Ku (CURRICULUM, ASSIGNMENT, AI_REPORT, FEEDBACK_REPORT)
            title: Ku title (required)
            user_uid: Owner UID (None for CURRICULUM, required for others)
            **kwargs: All other fields for the DTO

        Returns:
            New DTO instance

        Raises:
            ValueError: If ownership doesn't match KuType requirements

        Example:
            ```python
            @classmethod
            def create_curriculum(cls, title: str, domain: Domain, **kwargs) -> "KuDTO":
                return cls._create_ku_dto(
                    ku_type=KuType.CURRICULUM,
                    title=title,
                    domain=domain,
                    **kwargs,
                )

            @classmethod
            def create_assignment(cls, user_uid: str, title: str, **kwargs) -> "KuDTO":
                return cls._create_ku_dto(
                    ku_type=KuType.ASSIGNMENT,
                    title=title,
                    user_uid=user_uid,
                    **kwargs,
                )
            ```
        """
        # Validate ownership
        cls._validate_ku_ownership(ku_type, user_uid)

        # Generate UID if not provided
        uid = kwargs.pop("uid", None)
        if not uid:
            uid = cls._generate_ku_uid(ku_type, user_uid, title)

        # Set timestamps if not provided
        now = datetime.now()
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)

        return cls(  # type: ignore[call-arg]
            uid=uid,
            title=title,
            ku_type=ku_type,
            user_uid=user_uid,
            **kwargs,
        )
