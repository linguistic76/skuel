"""
Interaction Protocols - ISP Contract for the User Interaction Contract (ADR-051)
================================================================================

Backend-level protocol typing ``InteractionService.backend``: base CRUD from
``BackendOperations[Interaction]`` plus the Phase 2 result-status transition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from core.ports.base_protocols import BackendOperations
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.enums.interaction_enums import InteractionResult
    from core.models.interaction.interaction import Interaction  # noqa: F401


class InteractionBackendOperations(BackendOperations["Interaction"], Protocol):
    """Backend operations for Interaction — base CRUD + result-status transition.

    Implementation: InteractionBackend (backends/misc_backends.py)
    Consumer: InteractionService.__init__
    """

    async def update_result_status_for_entry(
        self,
        entry_uid: str,
        new_status: InteractionResult,
        allowed_from: tuple[InteractionResult, ...],
    ) -> Result[int]: ...
