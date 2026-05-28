"""
Password Hashing and Verification
==================================

Utilities for secure password management using bcrypt.

Features:
- Password hashing with bcrypt
- Password verification
- Secure defaults (12 rounds)

Version: 1.0.0
Date: 2025-10-18
"""

import bcrypt

from core.utils.logging import get_logger

logger = get_logger("skuel.auth.password")

# Bcrypt work factor (number of rounds)
# 12 rounds is a good balance between security and performance
BCRYPT_ROUNDS = 12


MIN_PASSWORD_LENGTH = 8

# bcrypt hashes only the first 72 bytes of input. bcrypt >=4 raises ValueError on
# longer input rather than silently truncating, but that error surfaces from the
# adapter as a generic "Sign up error: ..." string. Validate up-front so the user
# gets a clean field-level error before the hash call is ever reached.
MAX_PASSWORD_BYTES = 72


def validate_password(password: str) -> str | None:
    """Validate password against policy rules.

    Returns None if valid, or an error message string if invalid.
    """
    if not password:
        return "Password is required"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return (
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes "
            "(non-ASCII characters count as multiple bytes)"
        )
    return None


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password,

    Returns:
        Bcrypt hashed password (as string)

    Example:
        >>> hash_password("my_secure_password123")
        '$2b$12$...'
    """
    if not password:
        raise ValueError("Password cannot be empty")

    # Convert password to bytes
    password_bytes = password.encode("utf-8")

    # Generate salt and hash
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password_bytes, salt)

    # Return as string
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against a bcrypt hash.

    Args:
        password: Plain text password to verify,
        password_hash: Bcrypt hash to verify against

    Returns:
        True if password matches hash, False otherwise,

    Example:
        >>> hashed = hash_password("my_password")
        >>> verify_password("my_password", hashed)
        True
        >>> verify_password("wrong_password", hashed)
        False
    """
    if not password or not password_hash:
        return False

    try:
        # Convert to bytes
        password_bytes = password.encode("utf-8")
        hash_bytes = password_hash.encode("utf-8")

        # Verify
        return bcrypt.checkpw(password_bytes, hash_bytes)

    except (ValueError, TypeError) as e:
        logger.error(f"Password verification error: {e}")
        return False


__all__ = [
    "BCRYPT_ROUNDS",
    "MAX_PASSWORD_BYTES",
    "MIN_PASSWORD_LENGTH",
    "hash_password",
    "validate_password",
    "verify_password",
]
