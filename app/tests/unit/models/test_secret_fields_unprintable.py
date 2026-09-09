"""Secret-bearing fields must not survive ``repr()``.

Pins PR-3 of the credential one-path arc: every field that holds a credential —
a password, a session token, a reset token, a bcrypt digest — is either a
``pydantic.SecretStr`` (masked repr) or carries ``field(repr=False)`` on its
dataclass. Nothing logs these objects today; this is the guard that keeps a
future log line, traceback frame or debugger view from disclosing one.

Every assertion is written against a sentinel value that is present in the
object and absent from its ``repr()``. Each case also reads the secret back, so
a field silently dropped (which would also pass the "not in repr" half) fails.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel, SecretStr, ValidationError

from adapters.inbound.auth_ui import _first_validation_error
from core.config.unified_config import (
    CacheConfig,
    DatabaseConfig,
    MessageQueueConfig,
    UnifiedConfig,
)
from core.models.auth import (
    LoginRequest,
    RegistrationRequest,
    ResetPasswordRequest,
)
from core.models.auth.password_reset_token import PasswordResetToken
from core.models.auth.session import Session
from core.models.user.user import User

# Deliberately self-describing: long enough to be a plausible credential, and
# unmistakable in a failure message or in scrollback.
SENTINEL = "sentinel-value-that-must-never-be-printed"


def _now() -> datetime:
    return datetime.now(UTC)


# ============================================================================
# Config dataclasses — field(repr=False)
# ============================================================================


class TestConfigSecretsAreNotInRepr:
    """core/config/unified_config.py credential fields."""

    def test_database_password_is_absent_from_repr_but_readable(self) -> None:
        config = DatabaseConfig(neo4j_uri="neo4j+s://example.invalid", neo4j_password=SENTINEL)

        rendered = repr(config)

        assert SENTINEL not in rendered
        assert config.neo4j_password == SENTINEL
        # The repr still renders the object — otherwise "not in repr" is vacuous.
        assert "neo4j+s://example.invalid" in rendered

    def test_cache_redis_password_is_absent_from_repr_but_readable(self) -> None:
        config = CacheConfig(redis_host="cache.invalid", redis_password=SENTINEL)

        rendered = repr(config)

        assert SENTINEL not in rendered
        assert config.redis_password == SENTINEL
        assert "cache.invalid" in rendered

    def test_message_queue_password_is_absent_from_repr_but_readable(self) -> None:
        config = MessageQueueConfig(host="queue.invalid", password=SENTINEL)

        rendered = repr(config)

        assert SENTINEL not in rendered
        assert config.password == SENTINEL
        assert "queue.invalid" in rendered

    def test_nested_config_repr_does_not_leak_the_database_password(self) -> None:
        """The realistic leak surface: repr(UnifiedConfig) nests every sub-config."""
        config = UnifiedConfig(database=DatabaseConfig(neo4j_password=SENTINEL))

        assert SENTINEL not in repr(config)

    def test_to_dict_still_excludes_every_credential(self) -> None:
        config = UnifiedConfig(
            database=DatabaseConfig(neo4j_password=SENTINEL),
            cache=CacheConfig(redis_password=SENTINEL),
            message_queue=MessageQueueConfig(password=SENTINEL),
        )

        assert SENTINEL not in str(config.to_dict())


# ============================================================================
# Auth request models — pydantic.SecretStr
# ============================================================================


class TestAuthRequestSecretsAreMasked:
    """core/models/auth/auth_request.py password and token fields.

    Constructed with ``SecretStr(...)`` because that is what the routes do —
    adapters/inbound/auth_ui.py wraps each form value at the boundary. Pydantic
    also coerces a bare ``str``; that path has its own test below.
    """

    def test_login_password_is_masked_in_repr_and_str(self) -> None:
        request = LoginRequest(username="learner", password=SecretStr(SENTINEL))

        assert SENTINEL not in repr(request)
        assert SENTINEL not in str(request)
        assert request.password.get_secret_value() == SENTINEL
        # Non-secret fields still render, so the masking is field-scoped.
        assert "learner" in repr(request)

    def test_registration_secrets_are_masked_in_repr(self) -> None:
        request = RegistrationRequest(
            username="learner",
            email="learner@example.invalid",
            display_name="Learner",
            password=SecretStr(SENTINEL),
            confirm_password=SecretStr(SENTINEL),
            accept_terms=True,
        )

        assert SENTINEL not in repr(request)
        assert request.password.get_secret_value() == SENTINEL
        assert request.confirm_password.get_secret_value() == SENTINEL

    def test_reset_password_secrets_and_token_are_masked_in_repr(self) -> None:
        request = ResetPasswordRequest(
            token=SecretStr(SENTINEL),
            password=SecretStr(SENTINEL),
            confirm_password=SecretStr(SENTINEL),
        )

        assert SENTINEL not in repr(request)
        assert request.token.get_secret_value() == SENTINEL
        assert request.password.get_secret_value() == SENTINEL

    def test_model_dump_masks_the_secrets(self) -> None:
        """Serialization is a second printing surface, not covered by repr()."""
        request = LoginRequest(username="learner", password=SecretStr(SENTINEL))

        assert SENTINEL not in str(request.model_dump())
        assert SENTINEL not in request.model_dump_json()

    def test_a_plain_string_is_still_coerced_and_masked(self) -> None:
        """Any caller handing over a bare str gets the masking regardless."""
        request = LoginRequest(username="learner", password=SENTINEL)  # type: ignore[arg-type]

        assert SENTINEL not in repr(request)
        assert request.password.get_secret_value() == SENTINEL


class TestSecretStrDoesNotBreakValidation:
    """SecretStr changes the field type — the rules built on it must still fire."""

    def test_mismatched_registration_passwords_still_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Passwords do not match"):
            RegistrationRequest(
                username="learner",
                email="learner@example.invalid",
                display_name="Learner",
                password=SecretStr(SENTINEL),
                confirm_password=SecretStr(SENTINEL + "-different"),
                accept_terms=True,
            )

    def test_matching_registration_passwords_still_accepted(self) -> None:
        request = RegistrationRequest(
            username="learner",
            email="learner@example.invalid",
            display_name="Learner",
            password=SecretStr(SENTINEL),
            confirm_password=SecretStr(SENTINEL),
            accept_terms=True,
        )

        assert request.password == request.confirm_password

    def test_mismatched_reset_passwords_still_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Passwords do not match"):
            ResetPasswordRequest(
                token=SecretStr(SENTINEL),
                password=SecretStr(SENTINEL),
                confirm_password=SecretStr(SENTINEL + "-different"),
            )

    def test_blank_secret_field_still_reads_as_required(self) -> None:
        """SecretStr's min_length message differs from str's.

        A ``str`` field says "String should have at least 1 character"; the same
        constraint on ``SecretStr`` says "Value should have at least 1 item after
        validation". ``_first_validation_error`` keys on the error ``type`` so the
        rendered form message stays the same for both.
        """
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username="learner", password=SecretStr(""))

        assert _first_validation_error(exc_info.value) == "Password is required"

    def test_blank_plain_field_still_reads_as_required(self) -> None:
        """The other half of the same branch — a plain str field is unchanged."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username="", password=SecretStr(SENTINEL))

        assert _first_validation_error(exc_info.value) == "Username is required"

    def test_missing_field_still_reads_as_required(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username="learner")  # type: ignore[call-arg]

        assert _first_validation_error(exc_info.value) == "Password is required"


# ============================================================================
# Auth domain dataclasses — field(repr=False)
# ============================================================================


class TestAuthModelSecretsAreNotInRepr:
    def test_session_token_is_absent_from_repr_but_readable(self) -> None:
        now = _now()
        session = Session(
            uid="session_abc",
            session_token=SENTINEL,
            user_uid="user_abc",
            created_at=now,
            expires_at=now + timedelta(days=1),
            last_active_at=now,
            ip_address="203.0.113.1",
            user_agent="pytest",
        )

        rendered = repr(session)

        assert SENTINEL not in rendered
        assert session.session_token == SENTINEL
        assert "session_abc" in rendered

    def test_session_token_survives_the_derivation_helpers(self) -> None:
        """with_updated_activity/invalidate rebuild the dataclass field by field."""
        now = _now()
        session = Session(
            uid="session_abc",
            session_token=SENTINEL,
            user_uid="user_abc",
            created_at=now,
            expires_at=now + timedelta(days=1),
            last_active_at=now,
            ip_address="203.0.113.1",
            user_agent="pytest",
        )

        for derived in (session.with_updated_activity(), session.invalidate()):
            assert derived.session_token == SENTINEL
            assert SENTINEL not in repr(derived)

    def test_reset_token_is_absent_from_repr_but_readable(self) -> None:
        now = _now()
        token = PasswordResetToken(
            uid="reset_abc",
            token=SENTINEL,
            user_uid="user_abc",
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )

        rendered = repr(token)

        assert SENTINEL not in rendered
        assert token.token == SENTINEL
        assert "reset_abc" in rendered
        assert SENTINEL not in repr(token.mark_used())

    def test_user_password_hash_is_absent_from_repr_but_readable(self) -> None:
        """A bcrypt digest is offline-crackable — a credential, not an opaque id."""
        user = User(uid="user_abc", title="learner", password_hash=SENTINEL)

        rendered = repr(user)

        assert SENTINEL not in rendered
        assert user.password_hash == SENTINEL
        assert "learner" in rendered


# ============================================================================
# Structural guard — the declaration, not one instance
# ============================================================================


SECRET_DATACLASS_FIELDS = [
    (DatabaseConfig, "neo4j_password"),
    (CacheConfig, "redis_password"),
    (MessageQueueConfig, "password"),
    (Session, "session_token"),
    (PasswordResetToken, "token"),
    (User, "password_hash"),
]


@pytest.mark.parametrize(("model", "field_name"), SECRET_DATACLASS_FIELDS)
def test_secret_dataclass_field_declares_repr_false(model: type[object], field_name: str) -> None:
    """Catches a field re-declared without repr=False, independent of any instance."""
    declared = {f.name: f for f in fields(model)}  # type: ignore[arg-type]

    assert field_name in declared, f"{model.__name__}.{field_name} no longer exists"
    assert not declared[field_name].repr, (
        f"{model.__name__}.{field_name} holds a credential and must be "
        f"declared field(..., repr=False)"
    )


def test_the_structural_guard_can_fail() -> None:
    """Positive control: the guard above detects a field that lacks repr=False."""

    @dataclass
    class Leaky:
        password: str = ""

    assert fields(Leaky)[0].repr is True


SECRET_PYDANTIC_FIELDS = [
    (RegistrationRequest, "password"),
    (RegistrationRequest, "confirm_password"),
    (LoginRequest, "password"),
    (ResetPasswordRequest, "token"),
    (ResetPasswordRequest, "password"),
    (ResetPasswordRequest, "confirm_password"),
]


@pytest.mark.parametrize(("model", "field_name"), SECRET_PYDANTIC_FIELDS)
def test_secret_pydantic_field_is_declared_secretstr(
    model: type[BaseModel], field_name: str
) -> None:
    """The declaration, not one instance — catches a field retyped back to str."""
    declared = model.model_fields

    assert field_name in declared, f"{model.__name__}.{field_name} no longer exists"
    assert declared[field_name].annotation is SecretStr, (
        f"{model.__name__}.{field_name} holds a credential and must be "
        f"annotated SecretStr, not {declared[field_name].annotation}"
    )
