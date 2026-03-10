"""
Auth Request Models (Tier 1 - External)
========================================

Pydantic models for authentication form validation.

These models extract and validate HTML form data for registration,
login, and password reset — moving business validation out of route handlers.
"""

from pydantic import Field, model_validator

from core.models.request_base import RequestBase


class RegistrationRequest(RequestBase):
    """Validates registration form data."""

    username: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1)
    confirm_password: str = Field(min_length=1)
    accept_terms: bool = False

    @model_validator(mode="after")
    def validate_registration(self) -> "RegistrationRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        if not self.accept_terms:
            raise ValueError("You must accept the Terms of Service")
        return self


class LoginRequest(RequestBase):
    """Validates login form data."""

    username: str = Field(min_length=1, description="Username or email")
    password: str = Field(min_length=1)


class ResetPasswordRequest(RequestBase):
    """Validates password reset form data."""

    token: str = Field(min_length=1)
    password: str = Field(min_length=1)
    confirm_password: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "ResetPasswordRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class ForgotPasswordRequest(RequestBase):
    """Validates forgot password form data."""

    email: str = Field(min_length=1)
