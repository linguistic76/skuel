"""
User Models Module
==================

Domain entity models for users (User, UserDTO, UserRequest).

Note: UserContext is a service-layer component.
Import from core.services.user for UserContext, UserContextBuilder, etc.
See ADR-030 for details.
"""

from .user import User, UserPreferences, UserServiceContext, UserStatistics, create_user
from .user_dto import UserDTO, UserPreferencesDTO
from .user_request import (
    UserCreateSchema,
    UserSummaryView,
    UserUpdateSchema,
    UserView,
)

__all__ = [
    "User",
    "UserCreateSchema",
    "UserDTO",
    "UserPreferences",
    "UserPreferencesDTO",
    "UserServiceContext",
    "UserStatistics",
    "UserSummaryView",
    "UserUpdateSchema",
    "UserView",
    "create_user",
]
