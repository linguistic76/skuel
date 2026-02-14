"""
KuDTOMixin - Conditional Ownership for Unified Ku DTOs
======================================================

Handles conditional user_uid validation based on KuType:

    Shared (user_uid must be None):
        CURRICULUM, MOC, LEARNING_STEP, LEARNING_PATH

    User-owned (user_uid required):
        ASSIGNMENT, AI_REPORT, FEEDBACK_REPORT,
        TASK, GOAL, HABIT, EVENT, CHOICE, PRINCIPLE, LIFE_PATH

UID generation per KuType:
    CURRICULUM/MOC:     ku_{slug}_{random}  (semantic UID from title)
    LEARNING_STEP:      ls_{random}
    LEARNING_PATH:      lp_{random}
    ASSIGNMENT/AI/FB:   {userid}_ku_{type}_{random}  (user-namespaced)
    Activity domains:   {type}_{slug}_{random}  (semantic UID)
    LIFE_PATH:          lp_{random}  (LP with life path designation)

Factory classmethods for each KuType (10 new + original 4 on KuDTO):
    create_task, create_goal, create_habit, create_event,
    create_choice, create_principle, create_moc,
    create_learning_step, create_learning_path, create_life_path

See: ActivityDTOMixin for the Activity Domain equivalent (to be removed in Phase 4).
"""

from datetime import datetime
from typing import Any, ClassVar, Self

from core.models.enums.ku_enums import KuStatus, KuType
from core.models.enums.metadata_enums import Visibility

# Shared types: no user_uid (admin-created or system content)
_SHARED_KU_TYPES = frozenset(
    {
        KuType.CURRICULUM,
        KuType.MOC,
        KuType.LEARNING_STEP,
        KuType.LEARNING_PATH,
    }
)


class KuDTOMixin:
    """
    Mixin providing factory methods for unified Ku DTOs with conditional ownership.

    Shared types (CURRICULUM, MOC, LS, LP) have no owner.
    All other types require user_uid.

    Class Variables:
        _uid_prefix: Default prefix for generated UIDs (always "ku")
    """

    _uid_prefix: ClassVar[str] = "ku"

    @classmethod
    def _validate_ku_ownership(cls, ku_type: KuType, user_uid: str | None) -> None:
        """
        Validate user_uid based on KuType (fail-fast philosophy).

        Shared types must have user_uid=None.
        All other types require user_uid.

        Raises:
            ValueError: If ownership doesn't match KuType requirements.
        """
        if ku_type in _SHARED_KU_TYPES:
            if user_uid is not None:
                raise ValueError(
                    f"{ku_type.value.upper()} Ku must have user_uid=None (shared content)"
                )
        elif not user_uid:
            raise ValueError(f"{ku_type.value.upper()} Ku requires user_uid (user-owned content)")

    @classmethod
    def _generate_ku_uid(
        cls, ku_type: KuType, user_uid: str | None, title: str | None = None
    ) -> str:
        """
        Generate UID with correct format per KuType.

        CURRICULUM/MOC:  ku_{slug}_{random}  (semantic UID from title)
        LEARNING_STEP:   ls_{random}
        LEARNING_PATH:   lp_{random}
        Activity types:  {type}_{slug}_{random}  (semantic UID)
        Content types:   {userid}_ku_{type}_{random}  (user-namespaced)
        LIFE_PATH:       lp_{random}

        Args:
            ku_type: Type of Ku being created
            user_uid: Owner UID (None for shared types)
            title: Title for semantic slug

        Returns:
            Generated UID string
        """
        from core.utils.uid_generator import UIDGenerator

        # Shared knowledge: semantic UID from title
        if ku_type in {KuType.CURRICULUM, KuType.MOC}:
            if title:
                return UIDGenerator.generate_knowledge_uid(title)
            return UIDGenerator.generate_random_uid("ku")

        # Curriculum structure: type-specific prefix
        if ku_type == KuType.LEARNING_STEP:
            return UIDGenerator.generate_random_uid("ls")
        if ku_type in {KuType.LEARNING_PATH, KuType.LIFE_PATH}:
            return UIDGenerator.generate_random_uid("lp")

        # Activity domains: {type}_{slug}_{random}
        if ku_type in {
            KuType.TASK,
            KuType.GOAL,
            KuType.HABIT,
            KuType.EVENT,
            KuType.CHOICE,
            KuType.PRINCIPLE,
        }:
            prefix = ku_type.value  # "task", "goal", "habit", etc.
            if title:
                return UIDGenerator.generate_uid(prefix, title)
            return UIDGenerator.generate_random_uid(prefix)

        # Content processing (ASSIGNMENT, AI_REPORT, FEEDBACK_REPORT): user-namespaced
        user_id = user_uid.replace("user_", "") if user_uid else "unknown"
        type_suffix = ku_type.value
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
            ku_type: Type of Ku (one of 14 KuTypes)
            title: Ku title (required)
            user_uid: Owner UID (None for shared types, required for others)
            **kwargs: All other fields for the DTO

        Returns:
            New DTO instance

        Raises:
            ValueError: If ownership doesn't match KuType requirements
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

    # =========================================================================
    # ACTIVITY DOMAIN FACTORY METHODS
    # =========================================================================

    @classmethod
    def create_task(cls, user_uid: str, title: str, **kwargs: Any) -> Self:
        """Create a TASK Ku (knowledge about what needs doing).

        Requires user_uid. Status defaults to DRAFT.
        """
        kwargs.setdefault("status", KuStatus.DRAFT)
        return cls._create_ku_dto(
            ku_type=KuType.TASK,
            title=title,
            user_uid=user_uid,
            **kwargs,
        )

    @classmethod
    def create_goal(cls, user_uid: str, title: str, **kwargs: Any) -> Self:
        """Create a GOAL Ku (knowledge about where you're heading).

        Requires user_uid. Status defaults to DRAFT.
        """
        kwargs.setdefault("status", KuStatus.DRAFT)
        return cls._create_ku_dto(
            ku_type=KuType.GOAL,
            title=title,
            user_uid=user_uid,
            **kwargs,
        )

    @classmethod
    def create_habit(cls, user_uid: str, title: str, **kwargs: Any) -> Self:
        """Create a HABIT Ku (knowledge about what you practice).

        Requires user_uid. Status defaults to ACTIVE.
        """
        kwargs.setdefault("status", KuStatus.ACTIVE)
        return cls._create_ku_dto(
            ku_type=KuType.HABIT,
            title=title,
            user_uid=user_uid,
            **kwargs,
        )

    @classmethod
    def create_event(cls, user_uid: str, title: str, **kwargs: Any) -> Self:
        """Create an EVENT Ku (knowledge about what you attend).

        Requires user_uid. Status defaults to SCHEDULED.
        """
        kwargs.setdefault("status", KuStatus.SCHEDULED)
        return cls._create_ku_dto(
            ku_type=KuType.EVENT,
            title=title,
            user_uid=user_uid,
            **kwargs,
        )

    @classmethod
    def create_choice(cls, user_uid: str, title: str, **kwargs: Any) -> Self:
        """Create a CHOICE Ku (knowledge about decisions you make).

        Requires user_uid. Status defaults to DRAFT.
        """
        kwargs.setdefault("status", KuStatus.DRAFT)
        return cls._create_ku_dto(
            ku_type=KuType.CHOICE,
            title=title,
            user_uid=user_uid,
            **kwargs,
        )

    @classmethod
    def create_principle(cls, user_uid: str, title: str, **kwargs: Any) -> Self:
        """Create a PRINCIPLE Ku (knowledge about what you believe).

        Requires user_uid. Status defaults to ACTIVE.
        """
        kwargs.setdefault("status", KuStatus.ACTIVE)
        return cls._create_ku_dto(
            ku_type=KuType.PRINCIPLE,
            title=title,
            user_uid=user_uid,
            **kwargs,
        )

    # =========================================================================
    # SHARED / CURRICULUM FACTORY METHODS
    # =========================================================================

    @classmethod
    def create_moc(cls, title: str, **kwargs: Any) -> Self:
        """Create a MOC Ku (Map of Content — KU organizing KUs).

        No user_uid — MOC is shared content.
        Status defaults to COMPLETED, visibility to PUBLIC.
        """
        kwargs.pop("user_uid", None)
        kwargs.setdefault("status", KuStatus.COMPLETED)
        kwargs.setdefault("visibility", Visibility.PUBLIC)
        return cls._create_ku_dto(
            ku_type=KuType.MOC,
            title=title,
            user_uid=None,
            **kwargs,
        )

    @classmethod
    def create_learning_step(cls, title: str, **kwargs: Any) -> Self:
        """Create a LEARNING_STEP Ku (step in a learning path).

        No user_uid — curriculum structure is shared content.
        Status defaults to DRAFT, visibility to PUBLIC.
        """
        kwargs.pop("user_uid", None)
        kwargs.setdefault("status", KuStatus.DRAFT)
        kwargs.setdefault("visibility", Visibility.PUBLIC)
        return cls._create_ku_dto(
            ku_type=KuType.LEARNING_STEP,
            title=title,
            user_uid=None,
            **kwargs,
        )

    @classmethod
    def create_learning_path(cls, title: str, **kwargs: Any) -> Self:
        """Create a LEARNING_PATH Ku (ordered sequence of steps).

        No user_uid — curriculum structure is shared content.
        Status defaults to DRAFT, visibility to PUBLIC.
        """
        kwargs.pop("user_uid", None)
        kwargs.setdefault("status", KuStatus.DRAFT)
        kwargs.setdefault("visibility", Visibility.PUBLIC)
        return cls._create_ku_dto(
            ku_type=KuType.LEARNING_PATH,
            title=title,
            user_uid=None,
            **kwargs,
        )

    # =========================================================================
    # DESTINATION FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_life_path(cls, user_uid: str, title: str, **kwargs: Any) -> Self:
        """Create a LIFE_PATH Ku (knowledge about your life direction).

        Requires user_uid. Status defaults to ACTIVE.
        """
        kwargs.setdefault("status", KuStatus.ACTIVE)
        return cls._create_ku_dto(
            ku_type=KuType.LIFE_PATH,
            title=title,
            user_uid=user_uid,
            **kwargs,
        )
