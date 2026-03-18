"""Admin UI view model types.

Frozen dataclasses for admin dashboard components.
"""

from dataclasses import dataclass


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
