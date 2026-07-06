"""
Device - Enrolled Vault-Agent Device Model (ADR-075)
====================================================

A Device is a user's enrolled vault-agent machine, identified by an Ed25519
public key. Devices are auth infrastructure — like sessions and unlike the 25
domain entities — so Device is explicitly NOT an EntityType: no ``:Entity``
multi-label, no DTO, no DomainConfig (mirrors how Group lives outside the
Entity hierarchy).

Graph shape (ADR-075 Decision 2):
    (User)-[:HAS_DEVICE]->(Device {uid, pubkey, name, enrolled_at,
                                   revoked_at, last_seen_at})

Pairing codes (ADR-075 Decision 2, storage question resolved in B2):
    The one-time enrollment code is stored HASHED (SHA-256, same discipline as
    session tokens) as properties on the ``User`` node —
    ``pairing_code_hash`` + ``pairing_code_expires_at`` — NOT as a separate
    ``(:PairingCode)`` node. One active code per user (generating a new code
    replaces the old), single-use burn is an atomic ``REMOVE`` in the redeem
    query, and no TTL cleanup job is needed for orphaned nodes (preserves the
    CORE-tier "no background workers" guarantee).

See: /docs/decisions/ADR-075-local-agent-vault-transport.md
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Pairing code: 8 chars base32, 10-minute TTL, single-use (ADR-075 Decision 2).
PAIRING_CODE_TTL_MINUTES = 10
PAIRING_CODE_BYTES = 5  # 5 bytes -> exactly 8 base32 chars, 40 bits of entropy

DEVICE_UID_PREFIX = "device_"
DEVICE_NAME_MAX_LENGTH = 64


@dataclass(frozen=True)
class Device:
    """
    Enrolled vault-agent device stored as a Neo4j node.

    Attributes:
        uid: Unique device identifier (``device_<8 hex>``)
        user_uid: Owning user (via the HAS_DEVICE edge)
        pubkey: base64url-encoded DER SubjectPublicKeyInfo Ed25519 public key
        name: User-chosen label ("mike-laptop")
        enrolled_at: Enrollment timestamp
        revoked_at: Revocation timestamp — stamped, never deleted (audit surface)
        last_seen_at: Last successful WS handshake
    """

    uid: str
    user_uid: str
    pubkey: str
    name: str
    enrolled_at: datetime
    revoked_at: datetime | None = None
    last_seen_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        """True once ``revoked_at`` has been stamped."""
        return self.revoked_at is not None


@dataclass(frozen=True)
class PairingCodeIssued:
    """A freshly minted pairing code — the raw code exists ONLY in this value.

    The server persists the SHA-256 hash; the code itself is shown to the user
    once and never stored or logged.
    """

    code: str
    expires_at: datetime


def generate_device_uid() -> str:
    """Generate a device UID: ``device_<8 random hex chars>`` (ADR-075)."""
    return f"{DEVICE_UID_PREFIX}{secrets.token_hex(4)}"


def generate_pairing_code() -> str:
    """Generate an 8-char base32 one-time pairing code (ADR-075 Decision 2)."""
    return base64.b32encode(secrets.token_bytes(PAIRING_CODE_BYTES)).decode("ascii")


def hash_pairing_code(code: str) -> str:
    """One-way SHA-256 hash for pairing-code storage (session-token discipline).

    Codes are user-typed — normalize case and whitespace so "abcd efgh" pasted
    from a phone screen matches the code the server minted.
    """
    normalized = code.strip().replace(" ", "").upper()
    return hashlib.sha256(normalized.encode("ascii", errors="replace")).hexdigest()


def pairing_code_expiry(now: datetime | None = None) -> datetime:
    """Compute the pairing-code expiry (now + 10 minutes, UTC)."""
    base = now if now is not None else datetime.now(UTC)
    return base + timedelta(minutes=PAIRING_CODE_TTL_MINUTES)


__all__ = [
    "DEVICE_NAME_MAX_LENGTH",
    "DEVICE_UID_PREFIX",
    "PAIRING_CODE_BYTES",
    "PAIRING_CODE_TTL_MINUTES",
    "Device",
    "PairingCodeIssued",
    "generate_device_uid",
    "generate_pairing_code",
    "hash_pairing_code",
    "pairing_code_expiry",
]
