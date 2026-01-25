"""
ActivityDTOMixin - Shared factory methods for Activity Domain DTOs
==================================================================

Provides common `create()` factory method behavior without forcing field order
(which dataclass inheritance would require).

Why Mixin over Base Class:
--------------------------
Dataclass inheritance has field ordering complexities - fields with defaults
must come after fields without defaults. A mixin shares methods without
forcing field order constraints.

Usage:
------
```python
@dataclass
class TaskDTO(ActivityDTOMixin):
    _uid_prefix: ClassVar[str] = "task"

    uid: str
    user_uid: str
    title: str
    # ... other fields

    @classmethod
    def create(cls, user_uid: str, title: str, **kwargs) -> "TaskDTO":
        return cls._create_activity_dto(
            user_uid=user_uid,
            title=title,
            **kwargs,
        )
```

The mixin handles:
- user_uid validation (fail-fast)
- UID generation if not provided
- created_at/updated_at timestamp defaults
"""

from datetime import datetime
from typing import Any, ClassVar, Self


class ActivityDTOMixin:
    """
    Mixin providing shared factory method behavior for Activity Domain DTOs.

    Handles the common pattern of:
    1. Validating user_uid (fail-fast philosophy)
    2. Generating UID if not provided
    3. Setting created_at/updated_at timestamps

    Class Variables:
        _uid_prefix: The prefix for generated UIDs (e.g., "task", "goal", "habit")
    """

    _uid_prefix: ClassVar[str] = "entity"

    @classmethod
    def _validate_user_uid(cls, user_uid: str) -> None:
        """
        Validate that user_uid is provided (fail-fast philosophy).

        Args:
            user_uid: The user UID to validate

        Raises:
            ValueError: If user_uid is empty or None
        """
        if not user_uid:
            raise ValueError(f"user_uid is REQUIRED for {cls.__name__} creation (fail-fast)")

    @classmethod
    def _create_activity_dto(
        cls,
        user_uid: str,
        uid_prefix: str | None = None,
        **kwargs: Any,
    ) -> Self:
        """
        Factory helper for creating Activity Domain DTOs with common defaults.

        This method:
        1. Validates user_uid (fail-fast)
        2. Generates a UID if not provided in kwargs
        3. Sets created_at/updated_at to now if not provided

        Args:
            user_uid: User UID (REQUIRED)
            uid_prefix: Override for UID prefix (defaults to cls._uid_prefix)
            **kwargs: All other fields for the DTO

        Returns:
            New DTO instance

        Example:
            ```python
            @classmethod
            def create(cls, user_uid: str, title: str, **kwargs) -> "TaskDTO":
                return cls._create_activity_dto(
                    user_uid=user_uid,
                    title=title,
                    **kwargs,
                )
            ```
        """
        from core.utils.uid_generator import UIDGenerator

        # Validate user_uid (fail-fast)
        cls._validate_user_uid(user_uid)

        # Generate UID if not provided
        uid = kwargs.pop("uid", None)
        if not uid:
            prefix = uid_prefix or getattr(cls, "_uid_prefix", "entity")
            uid = UIDGenerator.generate_random_uid(prefix)

        # Set timestamps if not provided
        now = datetime.now()
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)

        return cls(uid=uid, user_uid=user_uid, **kwargs)  # type: ignore[call-arg]
