"""Lifecycle pins for PasswordResetToken (core/models/auth/password_reset_token.py).

The token is a security state machine: 15-minute expiry, single-use, admin
provenance. These tests pin the invariants the auth flow depends on — a token
is valid only while unexpired AND unused, ``mark_used`` is a one-way door, and
generated tokens carry full 256-bit entropy.
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


def _token(
    *,
    expires_delta: timedelta = timedelta(minutes=15),
    is_used: bool = False,
) -> PasswordResetToken:
    now = datetime.now(UTC)
    return PasswordResetToken(
        uid="reset_deadbeef",
        token="tok",
        user_uid=_USER,
        created_at=now,
        expires_at=now + expires_delta,
        is_used=is_used,
        created_by_admin_uid=_ADMIN,
    )


class TestFactory:
    def test_defaults_to_fifteen_minute_expiry(self) -> None:
        token = create_password_reset_token(_USER, created_by_admin_uid=_ADMIN)

        assert RESET_TOKEN_EXPIRY_MINUTES == 15
        assert token.expires_at - token.created_at == timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
        assert token.is_used is False
        assert token.is_valid()
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


class TestValidity:
    def test_expired_token_is_invalid(self) -> None:
        token = _token(expires_delta=timedelta(minutes=-1))

        assert token.is_expired()
        assert not token.is_valid()

    def test_used_token_is_invalid_even_if_unexpired(self) -> None:
        token = _token(is_used=True)

        assert not token.is_expired()
        assert not token.is_valid()

    def test_fresh_token_is_valid(self) -> None:
        token = _token()

        assert token.is_valid()
        assert token.time_until_expiry() > timedelta(0)

    def test_expired_token_reports_negative_time_remaining(self) -> None:
        token = _token(expires_delta=timedelta(minutes=-5))

        assert token.time_until_expiry() < timedelta(0)


class TestSingleUse:
    def test_mark_used_is_one_way_and_preserves_identity(self) -> None:
        token = _token()

        used = token.mark_used()

        assert used.is_used is True
        assert not used.is_valid()
        # Identity fields survive the transition untouched.
        assert (used.uid, used.token, used.user_uid) == (
            token.uid,
            token.token,
            token.user_uid,
        )
        assert (used.created_at, used.expires_at) == (token.created_at, token.expires_at)
        assert used.created_by_admin_uid == token.created_by_admin_uid

    def test_original_token_is_immutable(self) -> None:
        token = _token()

        token.mark_used()

        assert token.is_used is False  # mark_used returned a copy
        with pytest.raises(FrozenInstanceError):
            token.is_used = True  # type: ignore[misc]
