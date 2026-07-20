"""
User Progress Protocols
========================

Protocols for the UserProgressBackend — user learning progress graph operations.

Implementation: adapters/persistence/neo4j/user_progress_backend.py
Consumer: UserProgressService
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class UserProgressBackendOperations(Protocol):
    """Backend operations for user learning progress."""

    # Profile building
    async def get_user_username(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...
    async def get_mastered_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...
    async def get_in_progress_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...
    async def get_completed_prerequisites(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...
    async def get_prerequisite_map(self) -> Result[list[dict[str, Any]]]: ...
    async def get_active_learning_paths(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...
    async def get_completed_learning_paths(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...
    async def get_interested_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...
    async def get_bookmarked_knowledge(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    # Readiness
    async def get_prerequisites_for_entity(
        self, target_uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    # Mastery & progress tracking
    async def record_mastery(
        self,
        user_uid: str,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int,
        confidence_level: float,
    ) -> Result[list[dict[str, Any]]]: ...

    async def record_progress(
        self,
        user_uid: str,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int,
        difficulty_rating: float,
    ) -> Result[list[dict[str, Any]]]: ...

    # Analytics
    async def calculate_knowledge_coverage(
        self, user_uid: str, domain: str | None
    ) -> Result[list[dict[str, Any]]]: ...
