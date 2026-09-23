"""Lifecycle pins for PasswordResetToken (core/models/auth/password_reset_token.py).

The model is the token's shape and its factory: 15-minute expiry, admin
provenance, full 256-bit entropy, immutability. Validity (unused, unexpired)
is decided by the claiming write, not by the model — that half is pinned
against a real graph in tests/integration/test_login_roundtrip.py.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from core.models.auth.password_reset_token import (
    RESET_TOKEN_EXPIRY_MINUTES,
    PasswordResetToken,
    create_password_reset_token,
    generate_reset_token,
)
from core.models.type_hints import UserUID

_USER = UserUID("user_target")
_ADMIN = "user_admin"


def _token() -> PasswordResetToken:
    now = datetime.now(UTC)
    return PasswordResetToken(
        uid="reset_deadbeef",
        token="tok",
        user_uid=_USER,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
        created_by_admin_uid=_ADMIN,
    )


class TestFactory:
    def test_defaults_to_fifteen_minute_expiry(self) -> None:
        token = create_password_reset_token(_USER, created_by_admin_uid=_ADMIN)

        assert RESET_TOKEN_EXPIRY_MINUTES == 15
        assert token.expires_at - token.created_at == timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
        assert token.is_used is False
        assert token.user_uid == _USER
        assert token.created_by_admin_uid == _ADMIN
        assert token.uid.startswith("reset_")

    def test_custom_expiry_minutes_honored(self) -> None:
        token = create_password_reset_token(_USER, expiry_minutes=1)

        assert token.expires_at - token.created_at == timedelta(minutes=1)

    def test_generated_tokens_are_unique_and_high_entropy(self) -> None:
        tokens = {generate_reset_token() for _ in range(100)}

        assert len(tokens) == 100
        # 32 urlsafe-encoded bytes ≈ 43 chars; anything shorter lost entropy.
        assert all(len(t) >= 43 for t in tokens)


class TestImmutability:
    def test_token_is_frozen(self) -> None:
        token = _token()

        with pytest.raises(FrozenInstanceError):
            token.is_used = True  # type: ignore[misc]
