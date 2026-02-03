"""
Askesis Core Service - CRUD Operations
========================================

Handles basic CRUD operations for Askesis AI assistant instances.

Version: 1.0.0
- v1.0.0: Initial implementation for Priority 1.1 (November 18, 2025)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.askesis.askesis_dto import AskesisDTO
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.askesis.askesis import Askesis
    from core.models.askesis.askesis_request import (
        AskesisCreateRequest,
        AskesisUpdateRequest,
    )
    from core.services.protocols.base_protocols import BackendOperations
    from core.services.user.unified_user_context import UserContext


logger = get_logger("skuel.services.askesis.core")


def _dto_to_dict_filtered(dto: AskesisDTO) -> dict[str, Any]:
    """
    Convert DTO to dict, filtering out empty collections for Neo4j.

    Neo4j can't handle empty dicts/maps, so we filter them out.
    """
    from dataclasses import asdict

    data = asdict(dto)

    # Filter out empty collections (Neo4j doesn't like them)
    filtered = {}
    for key, value in data.items():
        if isinstance(value, dict) and not value:
            # Skip empty dicts
            continue
        if isinstance(value, list | tuple) and not value:
            # Skip empty lists/tuples
            continue
        filtered[key] = value

    return filtered


class AskesisCoreService:
    """
    Core CRUD operations for Askesis AI assistant instances.

    Responsibilities:
    - Create, read, update, delete Askesis instances
    - List instances (primarily for user's own instance)
    - One-to-one with User (each user has one Askesis instance)

    Architecture:
    - Uses protocol-based backend for storage (protocol-based dependency injection)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    def __init__(self, backend: BackendOperations, driver: "AsyncDriver") -> None:
        """
        Initialize Askesis core service.

        Args:
            backend: Backend implementing BackendOperations protocol
            driver: Neo4j driver for UserContextBuilder
        """
        self.backend = backend
        self.driver = driver
        self.logger = get_logger("skuel.services.askesis.core")

    async def build_user_context(self, user_uid: str) -> "Result[UserContext]":
        """
        Build user context for the given user.

        Encapsulates UserContextBuilder so routes don't hold a raw driver.

        See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
        """
        from core.services.user.user_context_builder import UserContextBuilder

        context_builder = UserContextBuilder(self.driver)
        return await context_builder.build(user_uid)

    async def get_or_create_for_user(
        self,
        user_uid: str,
    ) -> Result[Askesis]:
        """
        Get existing Askesis instance for user, or create if not exists.

        Each user has exactly ONE Askesis instance. This method ensures
        it exists.

        Args:
            user_uid: User UID

        Returns:
            Result containing Askesis instance
        """
        # Try to find existing instance for user
        result = await self.backend.find_by(user_uid=user_uid, limit=1)

        if result.is_error:
            return Result.fail(result.expect_error())

        instances = result.value
        if instances:
            # User already has an Askesis instance
            return Result.ok(instances[0])

        # No instance exists - create default one
        self.logger.info(f"Creating default Askesis instance for user {user_uid}")

        askesis_uid = UIDGenerator.generate_random_uid("askesis")
        dto = AskesisDTO(
            uid=askesis_uid,
            user_uid=user_uid,
            name="Askesis",
            version="1.0",
            created_at=datetime.now(),
        )

        create_result = await self.backend.create(dto)
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        self.logger.info(f"Created Askesis instance {askesis_uid} for user {user_uid}")
        return Result.ok(create_result.value)

    async def create_askesis(
        self,
        user_uid: str,
        create_request: AskesisCreateRequest,
    ) -> Result[Askesis]:
        """
        Create a new Askesis instance for a user.

        Note: Users should only have ONE Askesis instance.
        Use get_or_create_for_user() instead.

        Args:
            user_uid: User UID
            create_request: Askesis creation request

        Returns:
            Result containing created Askesis
        """
        # Check if user already has an instance
        existing_result = await self.backend.find_by(user_uid=user_uid, limit=1)
        if existing_result.is_error:
            return Result.fail(existing_result.expect_error())

        if existing_result.value:
            return Result.fail(
                Errors.validation(
                    message=f"User {user_uid} already has an Askesis instance",
                    field="user_uid",
                    value=user_uid,
                )
            )

        # Create new instance
        askesis_uid = UIDGenerator.generate_random_uid("askesis")
        dto = AskesisDTO(
            uid=askesis_uid,
            user_uid=user_uid,
            name=create_request.name,
            version=create_request.version,
            preferred_conversation_style=create_request.preferred_conversation_style,
            preferred_complexity_level=create_request.preferred_complexity_level,
            created_at=datetime.now(),
        )

        result = await self.backend.create(dto)
        if result.is_error:
            return Result.fail(result.expect_error())

        self.logger.info(f"Created Askesis instance {askesis_uid} for user {user_uid}")
        return Result.ok(result.value)

    async def get_askesis(self, askesis_uid: str) -> Result[Askesis]:
        """
        Get a specific Askesis instance by UID.

        Args:
            askesis_uid: Askesis UID

        Returns:
            Result containing Askesis
        """
        result = await self.backend.get(askesis_uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(
                Errors.not_found(
                    resource="Askesis",
                    identifier=askesis_uid,
                )
            )

        return Result.ok(result.value)

    async def get_user_askesis(self, user_uid: str) -> Result[Askesis]:
        """
        Get user's Askesis instance (or create if not exists).

        Args:
            user_uid: User UID

        Returns:
            Result containing Askesis
        """
        return await self.get_or_create_for_user(user_uid)

    async def update_askesis(
        self,
        askesis_uid: str,
        update_request: AskesisUpdateRequest,
    ) -> Result[Askesis]:
        """
        Update Askesis settings/preferences.

        Args:
            askesis_uid: Askesis UID
            update_request: Update request

        Returns:
            Result containing updated Askesis
        """
        # Get existing instance
        existing_result = await self.get_askesis(askesis_uid)
        if existing_result.is_error:
            return existing_result

        existing = existing_result.value

        # Convert to DTO for update
        dto = existing.to_dto()

        # Apply updates
        if update_request.name is not None:
            dto.name = update_request.name
        if update_request.version is not None:
            dto.version = update_request.version
        if update_request.preferred_conversation_style is not None:
            dto.preferred_conversation_style = update_request.preferred_conversation_style
        if update_request.preferred_complexity_level is not None:
            dto.preferred_complexity_level = update_request.preferred_complexity_level

        dto.last_interaction = datetime.now()

        # Update in backend (convert DTO to dict, filtering empty collections for Neo4j)
        update_result = await self.backend.update(askesis_uid, _dto_to_dict_filtered(dto))
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        self.logger.info(f"Updated Askesis instance {askesis_uid}")
        return Result.ok(update_result.value)

    async def delete_askesis(self, askesis_uid: str) -> Result[bool]:
        """
        Delete an Askesis instance.

        Args:
            askesis_uid: Askesis UID

        Returns:
            Result indicating success
        """
        result = await self.backend.delete(askesis_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        self.logger.info(f"Deleted Askesis instance {askesis_uid}")
        return Result.ok(True)

    async def list_user_instances(self, user_uid: str) -> Result[list[Askesis]]:
        """
        List all Askesis instances for a user.

        Note: Users should only have ONE instance, but this method
        supports querying multiple if they exist.

        Args:
            user_uid: User UID

        Returns:
            Result containing list of Askesis instances
        """
        result = await self.backend.find_by(user_uid=user_uid, limit=10)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(result.value)

    async def record_conversation(
        self,
        askesis_uid: str,
    ) -> Result[Askesis]:
        """
        Record that a conversation occurred (increment metrics).

        Args:
            askesis_uid: Askesis UID

        Returns:
            Result containing updated Askesis
        """
        existing_result = await self.get_askesis(askesis_uid)
        if existing_result.is_error:
            return existing_result

        existing = existing_result.value
        dto = existing.to_dto()

        # Increment conversation count
        dto.total_conversations += 1
        dto.last_interaction = datetime.now()

        # Update in backend (convert DTO to dict, filtering empty collections for Neo4j)
        update_result = await self.backend.update(askesis_uid, _dto_to_dict_filtered(dto))
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        return Result.ok(update_result.value)
