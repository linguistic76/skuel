"""Admin UI view model types.

Frozen dataclasses for admin dashboard components.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.user.user import User


@dataclass(frozen=True)
class UserCardData:
    """User card data for admin user management."""

    uid: str
    username: str
    email: str
    role: str
    is_active: bool
    display_name: str = ""
    is_verified: bool = False
    created_at: str | None = None
    last_login_at: str = "Never"

    @classmethod
    def from_user(cls, user: User) -> UserCardData:
        """The view model of a ``User`` — one projection for every admin surface."""
        return cls(
            uid=user.uid,
            username=user.title,
            email=user.email,
            display_name=user.display_name or "",
            role=user.role.value,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at.isoformat() if user.created_at else None,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else "Never",
        )
