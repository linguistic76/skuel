"""
Credential Store — Fernet (default) + OS Keychain (opt-in)
============================================================

Two backends with the same get/set/delete/list/exists/migrate interface:

- ``CredentialStore`` (default): Fernet-encrypted JSON at
  ``~/.skuel/credentials.enc``. Keyed by ``SKUEL_MASTER_KEY``.
- ``KeyringBackend`` (Stage 3 opt-in): OS keychain via ``keyring`` package —
  libsecret on Linux (gnome-keyring / kwallet via D-Bus SecretService),
  Keychain on macOS, Credential Locker on Windows. No plaintext on disk.

Pick a backend by setting ``SKUEL_CREDENTIAL_BACKEND``:

    unset / anything            → ``CredentialStore`` (Fernet JSON)
    "keyring"                   → ``KeyringBackend``

``get_credential(key, fallback_to_env=True)`` is the public funnel. It picks
the active backend, looks up the key, falls back to ``os.getenv`` if missing,
and auto-migrates env values into the backend on first read (so transitioning
from direnv-loaded ``~/.config/skuel/secrets.env`` to a keychain happens
organically as services hit each credential for the first time).
"""

__version__ = "2.0"

import json
import os
from base64 import b64encode
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.utils.logging import get_logger

logger = get_logger(__name__)


# Values that auto-migration should *not* copy into the backend. Captures the
# common placeholder patterns from the `.env.example`-style templates so a
# half-filled template doesn't end up persisting into the keychain.
_PLACEHOLDER_VALUES: frozenset[str] = frozenset(
    {
        "",
        "your-openai-api-key-here",
        "your-deepgram-api-key-here",
        "your-neo4j-password",
        "your-redis-password",
        "your-session-secret-key",
        "your-jwt-secret",
        "your-encryption-key",
        "your-openai-key",
        "your-anthropic-key",
        "your-key",
        "your-api-key",
        "test-key",
    }
)


def _is_placeholder(value: str | None) -> bool:
    """True if `value` is empty or a known template placeholder."""
    if not value:
        return True
    # Catch any "your-*" pattern so new templates don't require a list update.
    if value.startswith("your-"):
        return True
    return value in _PLACEHOLDER_VALUES


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
        except (ValueError, TypeError, InvalidTag) as e:
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
        except (OSError, InvalidToken, json.JSONDecodeError, UnicodeDecodeError) as e:
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

        except (OSError, TypeError, InvalidToken) as e:
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
        results: dict[str, bool] = {}

        for key in keys:
            value = os.getenv(key)
            if value and not _is_placeholder(value):
                self.set(key, value)
                results[key] = True
                logger.info(f"✅ Migrated {key} to encrypted store")
            else:
                results[key] = False

        return results


class KeyringBackend:
    """OS-keychain credential storage (Stage 3).

    Delegates to the ``keyring`` package, which selects an OS-appropriate
    backend at import time:

    - Linux: ``SecretService`` over D-Bus (gnome-keyring or kwallet)
    - macOS: ``Keychain``
    - Windows: ``Credential Locker``

    All entries are stored under service name ``skuel``; the key passed to
    ``get/set/delete`` is used verbatim as the keychain account name
    (e.g. ``HF_API_TOKEN``).

    Listing keys is tricky across backends — ``keyring``'s API doesn't expose
    a portable iterator. We maintain a small index file at
    ``~/.config/skuel/keyring-index.json`` (key names only, no values) so
    ``credential_setup.py`` can show "what's stored" without probing
    individual keys. The index is best-effort; the keychain itself is the
    source of truth.
    """

    SERVICE = "skuel"
    INDEX_PATH = Path.home() / ".config" / "skuel" / "keyring-index.json"

    def __init__(self) -> None:
        # Import lazily — only the keyring path needs the dependency, and
        # devs on the Fernet path shouldn't pay the import cost (which
        # touches D-Bus on Linux).
        import keyring as _keyring

        self._keyring = _keyring
        self.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        logger.debug(
            f"KeyringBackend initialized — active keyring: {type(_keyring.get_keyring()).__name__}"
        )

    def set(self, key: str, value: str) -> None:
        """Store a credential in the OS keychain."""
        self._keyring.set_password(self.SERVICE, key, value)
        self._index_add(key)
        logger.info(f"✅ Credential '{key}' stored in OS keychain")

    def get(self, key: str, default: str | None = None) -> str | None:
        """Retrieve a credential from the OS keychain."""
        try:
            value = self._keyring.get_password(self.SERVICE, key)
            return value if value is not None else default
        except Exception as e:  # safety-net: keyring backend errors vary widely
            logger.warning(f"Keyring get failed for {key}: {e}")
            return default

    def delete(self, key: str) -> bool:
        """Remove a credential. Returns True if it existed."""
        try:
            self._keyring.delete_password(self.SERVICE, key)
            self._index_remove(key)
            logger.info(f"✅ Credential '{key}' deleted from OS keychain")
            return True
        except Exception:  # safety-net: PasswordDeleteError is in keyring.errors
            return False

    def list_keys(self) -> list[str]:
        """Return known credential keys. Best-effort via the index file."""
        return self._index_load()

    def exists(self, key: str) -> bool:
        """True if the key has a non-None value in the keychain."""
        return self.get(key) is not None

    def migrate_from_env(self, keys: list[str]) -> dict[str, bool]:
        """Migrate env-var values into the keychain. Same interface as
        CredentialStore.migrate_from_env so both backends are swappable
        from credential_setup.py.
        """
        results: dict[str, bool] = {}
        for key in keys:
            value = os.getenv(key)
            if value and not _is_placeholder(value):
                self.set(key, value)
                results[key] = True
            else:
                results[key] = False
        return results

    # ----- Index maintenance --------------------------------------------------

    def _index_load(self) -> list[str]:
        if not self.INDEX_PATH.exists():
            return []
        try:
            data = json.loads(self.INDEX_PATH.read_text())
            return list(data) if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):  # fmt: skip
            return []

    def _index_save(self, keys: list[str]) -> None:
        self.INDEX_PATH.write_text(json.dumps(sorted(set(keys)), indent=2))
        self.INDEX_PATH.chmod(0o600)

    def _index_add(self, key: str) -> None:
        keys = self._index_load()
        if key not in keys:
            keys.append(key)
            self._index_save(keys)

    def _index_remove(self, key: str) -> None:
        keys = self._index_load()
        if key in keys:
            keys.remove(key)
            self._index_save(keys)


# Singleton instance for the Fernet backend (kept across calls so we don't
# re-derive the KDF key on every credential read).
_store_instance: CredentialStore | None = None


def get_credential_store() -> CredentialStore:
    """Get the singleton Fernet-backed credential store instance.

    Kept as a public helper so older callers that imported it directly
    (e.g. credential_setup.py's interactive flow) keep working. New code
    should prefer ``get_credential()`` which dispatches to the active
    backend.
    """
    global _store_instance
    if _store_instance is None:
        _store_instance = CredentialStore()
    return _store_instance


# Type alias for "anything with the credential-backend interface".
# Used in get_active_backend() to express that either class is acceptable.
CredentialBackend = CredentialStore | KeyringBackend


def get_active_backend() -> CredentialBackend:
    """Return the credential backend selected by ``SKUEL_CREDENTIAL_BACKEND``.

    Values:
        ``"keyring"`` — OS keychain (Stage 3). Requires a desktop session
                        with gnome-keyring / kwallet running on Linux, or
                        Keychain/Credential Locker on macOS/Windows.
        anything else / unset — Fernet-encrypted JSON (the default).

    Raises:
        ValueError: if Fernet is selected and ``SKUEL_MASTER_KEY`` is unset.
            Callers that want a graceful fallback should catch this and
            consult ``os.getenv`` directly.
    """
    backend_name = os.getenv("SKUEL_CREDENTIAL_BACKEND", "").lower()
    if backend_name == "keyring":
        return KeyringBackend()
    return get_credential_store()


def get_credential(key: str, fallback_to_env: bool = True) -> str | None:
    """Fetch a credential from the active backend, with env fallback.

    Args:
        key: The credential key (e.g. ``"HF_API_TOKEN"``).
        fallback_to_env: If the backend doesn't have a value, check
            ``os.getenv(key)`` — and auto-migrate that value into the
            backend so subsequent reads are direct. Defaults True.

    Returns:
        The credential value, or None if not found in either location.

    Behavior matrix:
        backend_has_value      → return it
        env_has_value          → auto-migrate to backend, return env value
        neither                → return None
        backend_unavailable    → fall through to env (no auto-migration)
                                  This matters when SKUEL_MASTER_KEY isn't
                                  set OR keychain D-Bus isn't reachable —
                                  callers shouldn't crash on get_credential.
    """
    try:
        backend = get_active_backend()
    except ValueError:
        # Fernet backend, master key absent — fall straight to env.
        return os.getenv(key) if fallback_to_env else None

    try:
        value = backend.get(key)
        if value:
            return value
    except Exception as e:  # safety-net: keychain/D-Bus errors vary widely
        logger.warning(f"Backend lookup failed for {key}: {e}")

    if not fallback_to_env:
        return None

    env_value = os.getenv(key)
    if env_value and not _is_placeholder(env_value):
        try:
            backend.set(key, env_value)
            logger.info(f"Auto-migrated {key} from environment to {type(backend).__name__}")
        except Exception as e:  # safety-net: never block on a migration failure
            logger.warning(f"Auto-migration failed for {key}: {e}")
        return env_value

    return None
