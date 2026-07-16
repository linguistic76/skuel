"""
Device Backend — Graph-Native Vault-Agent Device Persistence (ADR-075)
======================================================================

Neo4j backend for vault-agent device enrollment, revocation, and the pairing
code lifecycle. Devices are auth infrastructure (like sessions), NOT an
EntityType — no ``:Entity`` multi-label, no DTO.

Graph shape:
    (User)-[:HAS_DEVICE]->(Device {uid, pubkey, name, enrolled_at,
                                   revoked_at, last_seen_at})

Pairing codes live HASHED on the User node (``pairing_code_hash`` +
``pairing_code_expires_at``) — one active code per user; redemption is an
atomic ``REMOVE`` burn (ADR-075 Decision 2, storage question resolved in B2).

Protocol: core/ports/device_protocols.py (DeviceBackendOperations)
See Also: session_backend.py — the sibling auth-infrastructure backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j._backend_helpers import to_native_datetime
from core.models.relationship_names import RelationshipName
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.type_hints import Neo4jProperties, UserUID

logger = get_logger(__name__)

_HAS_DEVICE = RelationshipName.HAS_DEVICE.value

# Shared RETURN shape: device properties (native datetimes) + owner uid.
_DEVICE_RETURN = """
        RETURN d.uid AS uid, d.pubkey AS pubkey, d.name AS name,
               d.enrolled_at AS enrolled_at, d.revoked_at AS revoked_at,
               d.last_seen_at AS last_seen_at, u.uid AS user_uid
"""


def _device_record(data: dict[str, object]) -> Neo4jProperties:
    """Normalize a device row: Neo4j temporals → native datetimes."""
    return {
        "uid": str(data["uid"]),
        "pubkey": str(data["pubkey"]),
        "name": str(data["name"]),
        "user_uid": str(data["user_uid"]),
        "enrolled_at": to_native_datetime(data.get("enrolled_at")),
        "revoked_at": to_native_datetime(data.get("revoked_at")),
        "last_seen_at": to_native_datetime(data.get("last_seen_at")),
    }


class DeviceBackend:
    """Neo4j persistence for vault-agent devices + pairing codes (ADR-075)."""

    def __init__(self, driver: AsyncDriver) -> None:
        self.driver = driver
        self.logger = logger

    async def set_pairing_code(
        self, user_uid: UserUID, code_hash: str, expires_at_iso: str
    ) -> Result[bool]:
        """Store the hashed pairing code + expiry on the User node (replace old)."""
        query = """
        MATCH (u:User {uid: $user_uid})
        SET u.pairing_code_hash = $code_hash,
            u.pairing_code_expires_at = datetime($expires_at)
        RETURN u.uid AS uid
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "code_hash": code_hash,
                        "expires_at": expires_at_iso,
                    },
                )
                record = await result.single()
                return Result.ok(record is not None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to set pairing code: {e}")
            return Result.fail(Errors.database("set_pairing_code", str(e)))

    async def redeem_pairing_code(self, code_hash: str, now_iso: str) -> Result[str | None]:
        """Atomically burn an unexpired pairing code; return the owner's uid.

        Wrong and expired codes both yield zero rows → None (one shape, no
        oracle). The ``REMOVE`` in the same write guarantees single-use.
        """
        query = """
        MATCH (u:User {pairing_code_hash: $code_hash})
        WHERE u.pairing_code_expires_at IS NOT NULL
          AND u.pairing_code_expires_at > datetime($now)
        REMOVE u.pairing_code_hash, u.pairing_code_expires_at
        RETURN u.uid AS uid
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"code_hash": code_hash, "now": now_iso})
                record = await result.single()
                return Result.ok(str(record["uid"]) if record else None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to redeem pairing code: {e}")
            return Result.fail(Errors.database("redeem_pairing_code", str(e)))

    async def create_device(
        self,
        user_uid: UserUID,
        device_uid: str,
        pubkey: str,
        device_name: str,
        enrolled_at_iso: str,
    ) -> Result[Neo4jProperties | None]:
        """Create the Device node + HAS_DEVICE edge for its owner."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        CREATE (u)-[:{_HAS_DEVICE}]->(d:Device {{
            uid: $device_uid,
            pubkey: $pubkey,
            name: $device_name,
            enrolled_at: datetime($enrolled_at)
        }})
        {_DEVICE_RETURN}
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "device_uid": device_uid,
                        "pubkey": pubkey,
                        "device_name": device_name,
                        "enrolled_at": enrolled_at_iso,
                    },
                )
                record = await result.single()
                return Result.ok(_device_record(dict(record)) if record else None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to create device: {e}")
            return Result.fail(Errors.database("create_device", str(e)))

    async def list_devices(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """All devices for a user, newest first (revoked included — audit)."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{_HAS_DEVICE}]->(d:Device)
        {_DEVICE_RETURN}
        ORDER BY d.enrolled_at DESC
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid})
                records = await result.data()
                return Result.ok([_device_record(row) for row in records])
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to list devices: {e}")
            return Result.fail(Errors.database("list_devices", str(e)))

    async def revoke_device(self, user_uid: UserUID, device_uid: str, now_iso: str) -> Result[bool]:
        """Stamp ``revoked_at`` on an owned, unrevoked device (never delete)."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{_HAS_DEVICE}]->(d:Device {{uid: $device_uid}})
        WHERE d.revoked_at IS NULL
        SET d.revoked_at = datetime($now)
        RETURN d.uid AS uid
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {"user_uid": user_uid, "device_uid": device_uid, "now": now_iso},
                )
                record = await result.single()
                return Result.ok(record is not None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to revoke device: {e}")
            return Result.fail(Errors.database("revoke_device", str(e)))

    async def get_device_by_pubkey(self, pubkey: str) -> Result[Neo4jProperties | None]:
        """UNREVOKED device by public key — the WS handshake lookup."""
        query = f"""
        MATCH (u:User)-[:{_HAS_DEVICE}]->(d:Device {{pubkey: $pubkey}})
        WHERE d.revoked_at IS NULL
        {_DEVICE_RETURN}
        LIMIT 1
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"pubkey": pubkey})
                record = await result.single()
                return Result.ok(_device_record(dict(record)) if record else None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to get device by pubkey: {e}")
            return Result.fail(Errors.database("get_device_by_pubkey", str(e)))

    async def touch_device(self, device_uid: str, now_iso: str) -> Result[None]:
        """Stamp ``last_seen_at`` after a successful handshake."""
        query = """
        MATCH (d:Device {uid: $device_uid})
        SET d.last_seen_at = datetime($now)
        RETURN d.uid AS uid
        """
        try:
            async with self.driver.session() as session:
                await session.run(query, {"device_uid": device_uid, "now": now_iso})
                return Result.ok(None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to touch device: {e}")
            return Result.fail(Errors.database("touch_device", str(e)))


__all__ = ["DeviceBackend"]
