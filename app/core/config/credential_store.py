"""
Encrypted Credential Store
===========================

Secure storage for sensitive credentials using encryption.
All passwords and API keys are stored encrypted, never in plain text.
"""

__version__ = "1.0"

import json
import os
from base64 import b64encode
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.utils.logging import get_logger

logger = get_logger(__name__)


class CredentialStore:
    """
    Encrypted credential storage using Fernet symmetric encryption.

    Credentials are stored in a JSON file encrypted with a master key.
    The master key is derived from the SKUEL_MASTER_KEY environment variable.
    """

    def __init__(self, store_path: Path | None = None) -> None:
        """
        Initialize the credential store.

        Args:
            store_path: Path to the encrypted credential file.
                       Defaults to ~/.skuel/credentials.enc
        """
        if store_path is None:
            home = Path.home()
            skuel_dir = home / ".skuel"
            skuel_dir.mkdir(exist_ok=True, mode=0o700)  # Secure directory
            self.store_path = skuel_dir / "credentials.enc"
        else:
            self.store_path = Path(store_path)

        self.cipher = self._initialize_cipher()

    def _initialize_cipher(self) -> Fernet:
        """Initialize the encryption cipher with the master key."""
        master_key = os.getenv("SKUEL_MASTER_KEY")

        if not master_key:
            raise ValueError(
                "SKUEL_MASTER_KEY environment variable not set. "
                "Generate one with: openssl rand -base64 32"
            )

        try:
            # Use the master key directly if it's already base64 encoded
            if len(master_key) == 44 and master_key.endswith("="):
                # Looks like a base64 key
                key = master_key.encode()
            else:
                # Derive a key from the master key
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=b"skuel_salt_v1",  # Static salt for deterministic key
                    iterations=100000,
                )
                key = b64encode(kdf.derive(master_key.encode()))

            return Fernet(key)
        except Exception as e:
            raise ValueError(f"Failed to initialize encryption: {e}") from e

    def _load_store(self) -> dict[str, Any]:
        """Load and decrypt the credential store."""
        if not self.store_path.exists():
            return {}

        try:
            with self.store_path.open("rb") as f:
                encrypted_data = f.read()

            decrypted_data = self.cipher.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logger.error(f"Failed to load credential store: {e}")
            return {}

    def _save_store(self, data: dict[str, Any]) -> None:
        """Encrypt and save the credential store."""
        try:
            json_data = json.dumps(data, indent=2)
            encrypted_data = self.cipher.encrypt(json_data.encode())

            # Save with secure permissions
            with self.store_path.open("wb") as f:
                f.write(encrypted_data)

            # Ensure file has secure permissions (owner read/write only)
            self.store_path.chmod(0o600)

        except Exception as e:
            logger.error(f"Failed to save credential store: {e}")
            raise

    def set(self, key: str, value: str) -> None:
        """
        Store a credential securely.

        Args:
            key: The credential key (e.g., 'NEO4J_PASSWORD', 'OPENAI_API_KEY')
            value: The credential value to encrypt and store
        """
        store = self._load_store()
        store[key] = value
        self._save_store(store)
        logger.info(f"✅ Credential '{key}' stored securely")

    def get(self, key: str, default: str | None = None) -> str | None:
        """
        Retrieve a credential.

        Args:
            key: The credential key
            default: Default value if key not found

        Returns:
            The decrypted credential value or default
        """
        store = self._load_store()
        return store.get(key, default)

    def delete(self, key: str) -> bool:
        """
        Delete a credential.

        Args:
            key: The credential key to delete

        Returns:
            True if deleted, False if key didn't exist
        """
        store = self._load_store()
        if key in store:
            del store[key]
            self._save_store(store)
            logger.info(f"✅ Credential '{key}' deleted")
            return True
        return False

    def list_keys(self) -> list[str]:
        """
        List all stored credential keys (not values).

        Returns:
            List of credential keys
        """
        store = self._load_store()
        return list(store.keys())

    def exists(self, key: str) -> bool:
        """
        Check if a credential exists.

        Args:
            key: The credential key

        Returns:
            True if the credential exists
        """
        store = self._load_store()
        return key in store

    def migrate_from_env(self, keys: list[str]) -> dict[str, bool]:
        """
        Migrate credentials from environment variables to encrypted store.

        Args:
            keys: List of environment variable names to migrate

        Returns:
            Dict mapping keys to migration success status
        """
        results = {}

        for key in keys:
            value = os.getenv(key)
            if (
                value
                and value != "your-openai-api-key-here"
                and value != "your-deepgram-api-key-here"
            ):
                # Only migrate real values, not placeholders
                self.set(key, value)
                results[key] = True
                logger.info(f"✅ Migrated {key} to encrypted store")
            else:
                results[key] = False

        return results


# Singleton instance
_store_instance: CredentialStore | None = None


def get_credential_store() -> CredentialStore:
    """Get the singleton credential store instance."""
    global _store_instance
    if _store_instance is None:
        _store_instance = CredentialStore()
    return _store_instance


def get_credential(key: str, fallback_to_env: bool = True) -> str | None:
    """
    Get a credential from the encrypted store or environment.

    Args:
        key: The credential key,
        fallback_to_env: If True, check environment variable if not in store

    Returns:
        The credential value or None
    """
    try:
        store = get_credential_store()
        value = store.get(key)

        if value:
            return value

        if fallback_to_env:
            # Fallback to environment variable
            env_value = os.getenv(key)
            if env_value and env_value not in [
                "your-openai-api-key-here",
                "your-deepgram-api-key-here",
            ]:
                # Migrate to store automatically
                store.set(key, env_value)
                logger.info(f"Auto-migrated {key} from environment to encrypted store")
                return env_value

        return None

    except ValueError:
        # Master key not set
        if fallback_to_env:
            return os.getenv(key)
        raise
