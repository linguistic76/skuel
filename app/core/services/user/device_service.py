"""
Device Service — Vault-Agent Device Enrollment + Revocation (ADR-075 B2)
========================================================================

Thin service over the device backend. Owns the pairing-code lifecycle
(mint → hash → redeem-and-burn) and enrollment/revocation semantics; the
Cypher lives in ``DeviceBackend`` below the hexagonal boundary.

Security posture (ADR-075 Decision 2):
- Pairing codes are stored HASHED (SHA-256) on the User node with a 10-minute
  TTL; the raw code exists only in the ``PairingCodeIssued`` return value.
- Redemption is a single atomic burn — a code validates exactly once.
- Invalid and expired codes are indistinguishable to the caller (one
  not-found shape, no oracle).
- The pairing code IS the credential for enrollment: the enroll door is
  sessionless, so nothing here trusts request identity.

Backend: DeviceBackend (adapters/persistence/neo4j/device_backend.py).
See: /docs/decisions/ADR-075-local-agent-vault-transport.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.auth.device_signature import decode_device_pubkey
from core.models.auth.device import (
    DEVICE_NAME_MAX_LENGTH,
    Device,
    PairingCodeIssued,
    generate_device_uid,
    generate_pairing_code,
    hash_pairing_code,
    pairing_code_expiry,
)
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.type_hints import Neo4jProperties
    from core.ports.device_protocols import DeviceBackendOperations

logger = get_logger("skuel.services.devices")

# Sanity ceiling for the base64url DER-SPKI pubkey string (real ones are ~60 chars).
_PUBKEY_MAX_LENGTH = 128


def _required_datetime(value: object) -> datetime:
    """Narrow a backend property that MUST be a datetime (wiring-defect guard)."""
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime device property, got {type(value).__name__}")
    return value


def _optional_datetime(value: object) -> datetime | None:
    """Narrow an optional backend datetime property (None passes through)."""
    return value if isinstance(value, datetime) else None


def _device_from_properties(props: Neo4jProperties) -> Device:
    """Build the frozen Device model from backend properties."""
    return Device(
        uid=str(props["uid"]),
        user_uid=str(props["user_uid"]),
        pubkey=str(props["pubkey"]),
        name=str(props["name"]),
        enrolled_at=_required_datetime(props["enrolled_at"]),
        revoked_at=_optional_datetime(props.get("revoked_at")),
        last_seen_at=_optional_datetime(props.get("last_seen_at")),
    )


class DeviceService:
    """Pairing-code enrollment + device lifecycle for vault agents."""

    def __init__(self, backend: DeviceBackendOperations) -> None:
        if backend is None:
            raise ValueError("Device backend is required")
        self.backend = backend

    async def create_pairing_code(self, user_uid: UserUID) -> Result[PairingCodeIssued]:
        """Mint a one-time pairing code for an authenticated user.

        Stores only the SHA-256 hash + expiry on the User node (replacing any
        previous unredeemed code) and returns the raw code exactly once.
        """
        code = generate_pairing_code()
        expires_at = pairing_code_expiry()
        stored = await self.backend.set_pairing_code(
            user_uid, hash_pairing_code(code), expires_at.isoformat()
        )
        if stored.is_error:
            return Result.fail(stored)
        if not stored.value:
            return Result.fail(Errors.not_found("User", user_uid))
        logger.info("Pairing code minted for %s (expires %s)", user_uid, expires_at.isoformat())
        return Result.ok(PairingCodeIssued(code=code, expires_at=expires_at))

    async def enroll_device(
        self, pairing_code: str, pubkey: str, device_name: str
    ) -> Result[Device]:
        """Enroll a device: redeem the pairing code, bind the pubkey to its user.

        The pairing code is the sole credential (the agent has no session).
        Input validation runs BEFORE redemption so malformed requests never
        burn a live code; a wrong/expired code returns the same not-found
        shape either way (no oracle).
        """
        name = device_name.strip()
        if not name or len(name) > DEVICE_NAME_MAX_LENGTH:
            return Result.fail(
                Errors.validation(
                    f"device_name must be 1-{DEVICE_NAME_MAX_LENGTH} characters",
                    field="device_name",
                )
            )
        if len(pubkey) > _PUBKEY_MAX_LENGTH or decode_device_pubkey(pubkey) is None:
            return Result.fail(
                Errors.validation(
                    "device_pubkey must be a base64url DER-encoded Ed25519 public key",
                    field="device_pubkey",
                )
            )

        now = datetime.now(UTC)
        redeemed = await self.backend.redeem_pairing_code(
            hash_pairing_code(pairing_code), now.isoformat()
        )
        if redeemed.is_error:
            return Result.fail(redeemed)
        user_uid = redeemed.value
        if user_uid is None:
            # Wrong and expired codes share one shape — no enrollment oracle.
            return Result.fail(Errors.not_found("Pairing code"))

        # Duplicate-pubkey guard AFTER redemption: reaching this answer costs a
        # valid pairing code, so it reveals nothing to unauthenticated probing.
        existing = await self.backend.get_device_by_pubkey(pubkey)
        if existing.is_error:
            return Result.fail(existing)
        if existing.value is not None:
            return Result.fail(
                Errors.validation(
                    "This device key is already enrolled — revoke the existing "
                    "device before re-enrolling it",
                    field="device_pubkey",
                )
            )

        created = await self.backend.create_device(
            UserUID(user_uid),
            generate_device_uid(),
            pubkey,
            name,
            now.isoformat(),
        )
        if created.is_error:
            # The read-then-create pre-check above is racy under concurrent
            # enrollments; the Device(pubkey) UNIQUE constraint is the real
            # guard (Kody #529). Map its violation to the same friendly
            # validation error instead of a raw database failure.
            message = str(created.expect_error().message)
            if "ConstraintValidationFailed" in message or "already exists" in message:
                return Result.fail(
                    Errors.validation(
                        "This device key is already enrolled — revoke the existing "
                        "device before re-enrolling it",
                        field="device_pubkey",
                    )
                )
            return Result.fail(created)
        if created.value is None:
            return Result.fail(Errors.not_found("User", user_uid))
        device = _device_from_properties(created.value)
        logger.info("Device %s enrolled for %s", device.uid, device.user_uid)
        return Result.ok(device)

    async def list_devices(self, user_uid: UserUID) -> Result[list[Device]]:
        """A user's devices, newest first — revoked rows included (audit surface)."""
        rows = await self.backend.list_devices(user_uid)
        if rows.is_error:
            return Result.fail(rows)
        return Result.ok([_device_from_properties(row) for row in rows.value])

    async def revoke_device(self, user_uid: UserUID, device_uid: str) -> Result[bool]:
        """Stamp ``revoked_at`` on an owned device. False = not found / not owned.

        Rows are stamped, not deleted — the device list doubles as an audit
        surface (ADR-075 Decision 2). Callers must also close any live agent
        session for this device (the routes layer owns the channel registry).
        """
        revoked = await self.backend.revoke_device(
            user_uid, device_uid, datetime.now(UTC).isoformat()
        )
        if revoked.is_error:
            return Result.fail(revoked)
        if revoked.value:
            logger.info("Device %s revoked by %s", device_uid, user_uid)
        return Result.ok(revoked.value)

    async def get_device_by_pubkey(self, pubkey: str) -> Result[Device | None]:
        """Resolve an UNREVOKED enrolled device by public key (WS handshake path)."""
        row = await self.backend.get_device_by_pubkey(pubkey)
        if row.is_error:
            return Result.fail(row)
        if row.value is None:
            return Result.ok(None)
        return Result.ok(_device_from_properties(row.value))

    async def touch_device(self, device_uid: str) -> Result[None]:
        """Stamp ``last_seen_at`` after a successful WS handshake."""
        return await self.backend.touch_device(device_uid, datetime.now(UTC).isoformat())


__all__ = ["DeviceService"]
