"""
Device Protocols — Vault-Agent Device Enrollment (ADR-075)
==========================================================

Protocol Responsibilities
--------------------------
    DeviceBackendOperations — Persistence-layer operations consumed by
                              DeviceService (typed against self.backend).

Devices are auth infrastructure (like sessions), NOT an EntityType — the
backend speaks raw property dicts keyed on the ``(User)-[:HAS_DEVICE]->(Device)``
graph shape. DeviceService converts to the frozen ``Device`` domain model.

Implementation: adapters/persistence/neo4j/device_backend.py

See: /docs/decisions/ADR-075-local-agent-vault-transport.md (Decision 2)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result


@runtime_checkable
class DeviceBackendOperations(Protocol):
    """Backend operations consumed by DeviceService."""

    async def set_pairing_code(
        self, user_uid: UserUID, code_hash: str, expires_at_iso: str
    ) -> Result[bool]:
        """Store the hashed pairing code + expiry on the User node.

        Replaces any previous unredeemed code (one active code per user).
        Returns True when the user exists, False otherwise.
        """
        ...

    async def redeem_pairing_code(self, code_hash: str, now_iso: str) -> Result[str | None]:
        """Atomically burn an unexpired pairing code, returning the owner's uid.

        Single query: match the User holding this hash with an unexpired
        expiry, REMOVE both code properties (single-use burn), return the uid.
        None when no user holds a live matching code (wrong OR expired — one
        indistinguishable shape, no oracle).
        """
        ...

    async def create_device(
        self,
        user_uid: UserUID,
        device_uid: str,
        pubkey: str,
        device_name: str,
        enrolled_at_iso: str,
    ) -> Result[Neo4jProperties | None]:
        """Create the Device node + HAS_DEVICE edge; None if the user vanished."""
        ...

    async def list_devices(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """All of a user's devices (including revoked — audit surface)."""
        ...

    async def revoke_device(self, user_uid: UserUID, device_uid: str, now_iso: str) -> Result[bool]:
        """Stamp ``revoked_at`` on an owned, unrevoked device. True if stamped."""
        ...

    async def get_device_by_pubkey(self, pubkey: str) -> Result[Neo4jProperties | None]:
        """Look up an UNREVOKED device by public key (with its owner's uid)."""
        ...

    async def touch_device(self, device_uid: str, now_iso: str) -> Result[None]:
        """Stamp ``last_seen_at`` after a successful WS handshake."""
        ...


__all__ = ["DeviceBackendOperations"]
