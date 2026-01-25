"""
Tests for Password Hashing and Verification.

Tests cover:
1. hash_password() - Password hashing with bcrypt
2. verify_password() - Password verification
3. Edge cases - Empty inputs, malformed hashes

The password module uses bcrypt with 12 rounds for secure password hashing.
"""

import pytest

from core.auth.password import BCRYPT_ROUNDS, hash_password, verify_password


class TestHashPassword:
    """Tests for hash_password()."""

    def test_hash_password_success(self):
        """Test hashing a valid password returns a hash string."""
        password = "my_secure_password123"
        hashed = hash_password(password)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_returns_bcrypt_format(self):
        """Test that hash follows bcrypt format ($2b$...)."""
        password = "test_password"
        hashed = hash_password(password)

        # Bcrypt hashes start with $2b$ (or $2a$ for older versions)
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
        # Bcrypt hashes are typically 60 characters
        assert len(hashed) == 60

    def test_hash_password_uses_configured_rounds(self):
        """Test that hash uses the configured number of rounds."""
        password = "test_password"
        hashed = hash_password(password)

        # Hash format: $2b$<rounds>$<salt+hash>
        # Extract rounds from hash
        parts = hashed.split("$")
        rounds = int(parts[2])

        assert rounds == BCRYPT_ROUNDS

    def test_hash_password_different_hashes_for_same_password(self):
        """Test that same password produces different hashes (salting)."""
        password = "same_password"

        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different due to random salt
        assert hash1 != hash2
        # But both should verify correctly
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_hash_password_empty_raises_value_error(self):
        """Test that empty password raises ValueError."""
        with pytest.raises(ValueError, match="Password cannot be empty"):
            hash_password("")

    def test_hash_password_whitespace_only_valid(self):
        """Test that whitespace-only password is valid (not empty string)."""
        password = "   "
        hashed = hash_password(password)

        assert hashed is not None
        assert verify_password(password, hashed)

    def test_hash_password_unicode_characters(self):
        """Test hashing password with unicode characters."""
        password = "pässwörd_with_émojis_🔐"
        hashed = hash_password(password)

        assert hashed is not None
        assert verify_password(password, hashed)

    def test_hash_password_max_length_password(self):
        """Test hashing a password at bcrypt's 72 byte limit."""
        # bcrypt has a hard limit of 72 bytes - passwords beyond this raise ValueError
        password = "a" * 72
        hashed = hash_password(password)

        assert hashed is not None
        assert verify_password(password, hashed)

    def test_hash_password_exceeds_max_length_raises(self):
        """Test that password exceeding 72 bytes raises ValueError."""
        # bcrypt enforces 72 byte limit
        password = "a" * 73
        with pytest.raises(ValueError, match="password cannot be longer than 72 bytes"):
            hash_password(password)


class TestVerifyPassword:
    """Tests for verify_password()."""

    def test_verify_correct_password(self):
        """Test that correct password returns True."""
        password = "correct_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        """Test that wrong password returns False."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_empty_password_returns_false(self):
        """Test that empty password returns False (not exception)."""
        hashed = hash_password("some_password")

        # Empty password should return False, not raise
        assert verify_password("", hashed) is False

    def test_verify_empty_hash_returns_false(self):
        """Test that empty hash returns False (not exception)."""
        password = "some_password"

        # Empty hash should return False, not raise
        assert verify_password(password, "") is False

    def test_verify_none_like_inputs_return_false(self):
        """Test that None-like inputs return False."""
        hashed = hash_password("password")

        # Empty strings should return False
        assert verify_password("", hashed) is False
        assert verify_password("password", "") is False

    def test_verify_malformed_hash_returns_false(self):
        """Test that malformed hash returns False (not exception)."""
        password = "some_password"

        # Various malformed hashes - should all return False gracefully
        malformed_hashes = [
            "not_a_valid_hash",
            "$2b$12$invalid",
            "12345678901234567890",
            "$invalid$format$here",
            "a" * 60,  # Right length but wrong format
        ]

        for malformed in malformed_hashes:
            result = verify_password(password, malformed)
            assert result is False, f"Expected False for malformed hash: {malformed}"

    def test_verify_case_sensitive(self):
        """Test that password verification is case sensitive."""
        password = "CaseSensitive"
        hashed = hash_password(password)

        # Same letters, different case
        assert verify_password("casesensitive", hashed) is False
        assert verify_password("CASESENSITIVE", hashed) is False
        assert verify_password("CaseSensitive", hashed) is True

    def test_verify_similar_passwords(self):
        """Test that similar but different passwords fail verification."""
        password = "password123"
        hashed = hash_password(password)

        # Similar but not exact
        assert verify_password("password1234", hashed) is False
        assert verify_password("password12", hashed) is False
        assert verify_password("Password123", hashed) is False
        assert verify_password("password123 ", hashed) is False


class TestBcryptRoundsConstant:
    """Tests for BCRYPT_ROUNDS configuration."""

    def test_bcrypt_rounds_is_12(self):
        """Test that default rounds is 12 (security/performance balance)."""
        assert BCRYPT_ROUNDS == 12

    def test_bcrypt_rounds_is_integer(self):
        """Test that rounds constant is an integer."""
        assert isinstance(BCRYPT_ROUNDS, int)
