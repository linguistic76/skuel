"""
DeviceService unit tests — pairing-code lifecycle + enrollment (ADR-075 B2).

Covers: code minting (hashed storage, TTL), enrollment happy path, the
no-oracle invalid/expired code shape, single-use burn ordering (validation
before redemption), duplicate-pubkey guard, and revocation semantics.
Backend is mocked (unit tier).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.models.auth.device import (
    PAIRING_CODE_TTL_MINUTES,
    hash_pairing_code,
)
from core.services.user.device_service import DeviceService
from core.utils.result_simplified import ErrorCategory, Result


def _pubkey_b64url() -> str:
    """A real Ed25519 public key in the ADR-075 wire shape (b64url DER SPKI)."""
    der = (
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    return base64.urlsafe_b64encode(der).decode("ascii").rstrip("=")


def _device_row(pubkey: str, user_uid: str = "user_mike") -> dict:
    return {
        "uid": "device_ab12cd34",
        "pubkey": pubkey,
        "name": "mike-laptop",
        "user_uid": user_uid,
        "enrolled_at": datetime.now(UTC),
        "revoked_at": None,
        "last_seen_at": None,
    }


def _backend(**overrides) -> SimpleNamespace:
    backend = SimpleNamespace(
        set_pairing_code=AsyncMock(return_value=Result.ok(True)),
        redeem_pairing_code=AsyncMock(return_value=Result.ok("user_mike")),
        create_device=AsyncMock(return_value=Result.ok(None)),
        list_devices=AsyncMock(return_value=Result.ok([])),
        revoke_device=AsyncMock(return_value=Result.ok(True)),
        get_device_by_pubkey=AsyncMock(return_value=Result.ok(None)),
        touch_device=AsyncMock(return_value=Result.ok(None)),
    )
    for key, value in overrides.items():
        setattr(backend, key, value)
    return backend


class TestPairingCode:
    @pytest.mark.asyncio
    async def test_create_returns_code_once_and_stores_only_the_hash(self) -> None:
        backend = _backend()
        service = DeviceService(backend)

        result = await service.create_pairing_code("user_mike")

        assert result.is_ok
        issued = result.value
        assert len(issued.code) == 8
        user_uid, stored_hash, expires_iso = backend.set_pairing_code.await_args.args
        assert user_uid == "user_mike"
        # The backend receives the SHA-256 of the code — never the raw code.
        assert stored_hash == hash_pairing_code(issued.code)
        assert issued.code not in stored_hash
        assert expires_iso == issued.expires_at.isoformat()

    @pytest.mark.asyncio
    async def test_expiry_is_ten_minutes(self) -> None:
        service = DeviceService(_backend())
        before = datetime.now(UTC)

        result = await service.create_pairing_code("user_mike")

        ttl = result.value.expires_at - before
        assert timedelta(minutes=PAIRING_CODE_TTL_MINUTES - 1) < ttl
        assert ttl <= timedelta(minutes=PAIRING_CODE_TTL_MINUTES, seconds=5)

    @pytest.mark.asyncio
    async def test_unknown_user_yields_not_found(self) -> None:
        backend = _backend(set_pairing_code=AsyncMock(return_value=Result.ok(False)))
        service = DeviceService(backend)

        result = await service.create_pairing_code("user_ghost")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND

    def test_hash_normalizes_user_typed_input(self) -> None:
        # Codes are pasted by humans — case and spaces must not matter.
        assert hash_pairing_code(" kar3 mwcs ") == hash_pairing_code("KAR3MWCS")
        assert hash_pairing_code("KAR3MWCS") != hash_pairing_code("KAR3MWCT")


class TestEnrollment:
    @pytest.mark.asyncio
    async def test_happy_path_binds_device_to_the_codes_user(self) -> None:
        pubkey = _pubkey_b64url()
        backend = _backend(create_device=AsyncMock(return_value=Result.ok(_device_row(pubkey))))
        service = DeviceService(backend)

        result = await service.enroll_device("KAR3MWCS", pubkey, "mike-laptop")

        assert result.is_ok
        device = result.value
        assert device.user_uid == "user_mike"
        assert device.pubkey == pubkey
        assert not device.is_revoked
        # Redemption used the HASH of the submitted code.
        code_hash, _now = backend.redeem_pairing_code.await_args.args
        assert code_hash == hash_pairing_code("KAR3MWCS")

    @pytest.mark.asyncio
    async def test_invalid_and_expired_codes_share_one_not_found_shape(self) -> None:
        # The backend returns None for BOTH wrong and expired codes (one Cypher
        # shape) — the service must surface one indistinguishable 404 error.
        backend = _backend(redeem_pairing_code=AsyncMock(return_value=Result.ok(None)))
        service = DeviceService(backend)

        result = await service.enroll_device("WRONGCOD", _pubkey_b64url(), "laptop")

        assert result.is_error
        error = result.expect_error()
        assert error.category == ErrorCategory.NOT_FOUND
        # No oracle: the message names the pairing code only, never the pubkey
        # or any enrollment state.
        assert "pairing code" in error.message.lower()
        backend.create_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_malformed_pubkey_never_burns_the_code(self) -> None:
        backend = _backend()
        service = DeviceService(backend)

        result = await service.enroll_device("KAR3MWCS", "not-a-key!!", "laptop")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.VALIDATION
        backend.redeem_pairing_code.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_blank_device_name_never_burns_the_code(self) -> None:
        backend = _backend()
        service = DeviceService(backend)

        result = await service.enroll_device("KAR3MWCS", _pubkey_b64url(), "   ")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.VALIDATION
        backend.redeem_pairing_code.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_duplicate_pubkey_is_rejected_after_redemption(self) -> None:
        pubkey = _pubkey_b64url()
        backend = _backend(
            get_device_by_pubkey=AsyncMock(return_value=Result.ok(_device_row(pubkey)))
        )
        service = DeviceService(backend)

        result = await service.enroll_device("KAR3MWCS", pubkey, "laptop")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.VALIDATION
        # Ordering: reaching the duplicate answer must have COST a valid code
        # (no unauthenticated pubkey probing).
        backend.redeem_pairing_code.assert_awaited_once()
        backend.create_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_duplicate_race_maps_constraint_violation_to_validation(self) -> None:
        # Kody #529: two enrollments can race past the read-then-create
        # pre-check; the Device(pubkey) UNIQUE constraint is the real guard,
        # and its violation must surface as the same friendly validation
        # error, not a raw database failure.
        from core.utils.result_simplified import Errors

        pubkey = _pubkey_b64url()
        backend = _backend(
            create_device=AsyncMock(
                return_value=Result.fail(
                    Errors.database(
                        operation="create_device",
                        message=(
                            "Neo.ClientError.Schema.ConstraintValidationFailed: Node "
                            "already exists with label `Device` and property `pubkey`"
                        ),
                    )
                )
            )
        )
        service = DeviceService(backend)

        result = await service.enroll_device("KAR3MWCS", pubkey, "laptop")

        assert result.is_error
        error = result.expect_error()
        assert error.category == ErrorCategory.VALIDATION
        assert "already enrolled" in error.message


class TestDeviceLifecycle:
    @pytest.mark.asyncio
    async def test_list_devices_converts_rows_to_models(self) -> None:
        pubkey = _pubkey_b64url()
        revoked_row = {
            **_device_row(pubkey),
            "uid": "device_old00000",
            "revoked_at": datetime.now(UTC),
        }
        backend = _backend(
            list_devices=AsyncMock(return_value=Result.ok([_device_row(pubkey), revoked_row]))
        )
        service = DeviceService(backend)

        result = await service.list_devices("user_mike")

        assert result.is_ok
        active, revoked = result.value
        assert not active.is_revoked
        assert revoked.is_revoked

    @pytest.mark.asyncio
    async def test_revoke_reports_whether_a_row_was_stamped(self) -> None:
        service = DeviceService(_backend())
        assert (await service.revoke_device("user_mike", "device_ab12cd34")).value is True

        service = DeviceService(_backend(revoke_device=AsyncMock(return_value=Result.ok(False))))
        assert (await service.revoke_device("user_mike", "device_nope")).value is False

    @pytest.mark.asyncio
    async def test_get_device_by_pubkey_returns_none_when_unknown(self) -> None:
        service = DeviceService(_backend())
        result = await service.get_device_by_pubkey(_pubkey_b64url())
        assert result.is_ok
        assert result.value is None
