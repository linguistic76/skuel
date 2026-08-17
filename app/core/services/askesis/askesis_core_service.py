"""
Askesis Core Service - CRUD Operations
========================================

Handles basic CRUD operations for Askesis AI assistant instances.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.askesis.askesis_converters import (
    apply_askesis_update_to_dto,
    askesis_create_request_to_dto,
    askesis_update_request_to_dto,
    create_askesis_dto_from_create_dto,
)
from core.models.askesis.askesis_dto import AskesisDTO
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.models.askesis.askesis import Askesis
    from core.models.askesis.askesis_request import (
        AskesisCreateRequest,
        AskesisUpdateRequest,
    )
    from core.ports.base_protocols import BackendOperations


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
    """

    def __init__(self, backend: BackendOperations) -> None:
        """
        Initialize Askesis core service.

        Args:
            backend: Backend implementing BackendOperations protocol
        """
        self.backend = backend
        self.logger = get_logger("skuel.services.askesis.core")

    async def get_or_create_for_user(
        self,
        user_uid: UserUID,
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
            return Result.fail(result)

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
            return Result.fail(create_result)

        self.logger.info(f"Created Askesis instance {askesis_uid} for user {user_uid}")
        return Result.ok(create_result.value)

    async def create_askesis(
        self,
        user_uid: UserUID,
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
            return Result.fail(existing_result)

        if existing_result.value:
            return Result.fail(
                Errors.validation(
                    message=f"User {user_uid} already has an Askesis instance",
                    field="user_uid",
                    value=user_uid,
                )
            )

        # Run the three-tier conversion chain: Request -> CreateDTO -> AskesisDTO.
        # ``create_askesis_dto_from_create_dto`` generates the UID via
        # UIDGenerator so the format matches the rest of SKUEL.
        create_dto = askesis_create_request_to_dto(create_request, user_uid)
        dto = create_askesis_dto_from_create_dto(create_dto)

        result = await self.backend.create(dto)
        if result.is_error:
            return Result.fail(result)

        self.logger.info(f"Created Askesis instance {dto.uid} for user {user_uid}")
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
            return Result.fail(result)

        if not result.value:
            return Result.fail(
                Errors.not_found(
                    resource="Askesis",
                    identifier=askesis_uid,
                )
            )

        return Result.ok(result.value)

    async def get_user_askesis(self, user_uid: UserUID) -> Result[Askesis]:
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

        # Three-tier patch chain: Request -> UpdateDTO -> apply -> AskesisDTO.
        # ``apply_askesis_update_to_dto`` only overwrites fields the
        # UpdateDTO specifies (skipping ``None`` values), then we stamp
        # ``last_interaction`` at the service boundary so the converter
        # stays purely about request->DTO translation.
        dto = existing.to_dto()
        update_dto = askesis_update_request_to_dto(update_request, askesis_uid)
        dto = apply_askesis_update_to_dto(dto, update_dto)
        dto.last_interaction = datetime.now()

        # Update in backend (convert DTO to dict, filtering empty collections for Neo4j)
        update_result = await self.backend.update(askesis_uid, _dto_to_dict_filtered(dto))
        if update_result.is_error:
            return Result.fail(update_result)

        self.logger.info(f"Updated Askesis instance {askesis_uid}")
        return Result.ok(update_result.value)

    async def delete_askesis(self, askesis_uid: str) -> Result[bool]:
        """
        Delete an Askesis instance.

        ``cascade=True`` because an Askesis is user-owned: it always carries at
        least the ``(User)-[:OWNS]->(askesis)`` edge, and a non-cascade delete
        refuses any node that still has relationships. Matches every other
        owned-entity delete (Choices, Forms, Groups, Tasks, UserEntry) and the
        route factory's G18 rule.

        Args:
            askesis_uid: Askesis UID

        Returns:
            Result indicating success
        """
        result = await self.backend.delete(askesis_uid, cascade=True)
        if result.is_error:
            return Result.fail(result)

        self.logger.info(f"Deleted Askesis instance {askesis_uid}")
        return Result.ok(True)

    async def list_user_instances(self, user_uid: UserUID) -> Result[list[Askesis]]:
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
            return Result.fail(result)

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
            return Result.fail(update_result)

        return Result.ok(update_result.value)
