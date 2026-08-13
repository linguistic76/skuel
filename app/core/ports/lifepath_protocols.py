"""
LifePath Protocols
===================

Protocols for the LifePathBackend — designation and alignment graph operations.

Implementation: adapters/persistence/neo4j/lifepath_backend.py
Consumers: LifePathCoreService, LifePathAlignmentService
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.ports.query_types import LifePathComposition
from core.utils.result_simplified import Result


@runtime_checkable
class LifePathBackendOperations(Protocol):
    """Backend operations for life path designation and alignment."""

    # Core — Designation CRUD
    async def get_designation(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def save_vision(
        self, user_uid: str, vision_statement: str, vision_themes: list[str], captured_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def designate_life_path(
        self, user_uid: str, life_path_uid: str, designated_at: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def remove_designation(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def update_alignment_score(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def record_alignment_snapshot(
        self, user_uid: str, score: float
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_alignment_snapshots(
        self, user_uid: str, days: int = 31
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_life_path_composition(
        self, life_path_uid: str
    ) -> Result[LifePathComposition | None]: ...

    # Alignment — Graph queries
    async def get_user_life_path(self, user_uid: str) -> Result[list[dict[str, Any]]]: ...

    async def calculate_knowledge_alignment(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def calculate_activity_alignment(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def calculate_goal_alignment(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def calculate_principle_alignment(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def calculate_momentum(
        self, user_uid: str, life_path_uid: str, seven_days_ago: str, fourteen_days_ago: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_knowledge_substance_stats(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[dict[str, Any]]]: ...
