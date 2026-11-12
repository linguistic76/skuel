"""
User Models Module
==================

Domain entity models for users (User, UserDTO, the boundary schemas).

Note: UserContext is a service-layer component.
Import from core.services.user for UserContext, UserContextBuilder, etc.
See ADR-030 for details.
"""

from .user import User, UserPreferences, create_user
from .user_dto import UserDTO, UserPreferencesDTO
from .user_request import DisplayNameUpdateRequest

__all__ = [
    "DisplayNameUpdateRequest",
    "User",
    "UserDTO",
    "UserPreferences",
    "UserPreferencesDTO",
    "create_user",
]
