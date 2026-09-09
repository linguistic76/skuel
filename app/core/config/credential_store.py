"""
Credential Store — the OS keychain, with an explicit env shape for headless
===========================================================================

One storage backend and one read-through shape, selected by
``SKUEL_CREDENTIAL_BACKEND``:

    ``keyring`` (default)  → ``KeyringBackend``: the OS keychain — libsecret on
                             Linux (gnome-keyring / kwallet over the D-Bus
                             SecretService), Keychain on macOS, Credential
                             Locker on Windows. No plaintext on disk.
    ``env``                → ``EnvBackend``: the process environment, read-only.
                             For headless deployments (droplet, CI, ssh) where
                             no keychain daemon exists. Credentials arrive
                             through the environment — on the droplet, compose
                             loads ``/opt/skuel/secrets.env``.

Any other value raises ``ConfigurationError`` at the first credential read,
which is boot. A typo'd selector must not resolve to a silent fallback.

``get_credential(key, fallback_to_env=True)`` is the public funnel: it reads the
active backend, falls back to ``os.getenv``, and — for catalog credentials only
— writes an env-supplied value into a writable backend so subsequent reads come
from the keychain. ``CREDENTIAL_CATALOG`` is what makes that gate meaningful:
connection config such as ``NEO4J_URI`` / ``NEO4J_USERNAME`` is read through the
same funnel by callers and must never be stored, or the keychain becomes a
second, stale source of truth for where the database lives.
"""

__version__ = "3.0"

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, NoReturn

from core.errors import ConfigurationError
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CredentialSpec:
    """What the catalog declares about one credential.

    ``required`` means the app cannot start without it; an optional credential
    gates a feature that degrades (AI off, Firefly sidecar unused).

    ``expected_prefix`` is advisory — the setup tool warns when a pasted value
    doesn't start with it, and stores the value anyway. A provider can change
    its prefix before we do, so this must never become a refusal.
    """

    description: str
    required: bool
    expected_prefix: str | None = None


# THE credential catalog. Three consumers read it and two mirrors pin it:
#   - get_credential() gates auto-migration on membership (below)
#   - core/config/credential_setup.py drives the interactive setup tool from it
#   - scripts/lint_skuel.py::SkuelLinter.CREDENTIAL_CATALOG mirrors the names
#     (SKUEL019 severity) and scripts/git-hooks/credential-keys.txt mirrors them
#     for the secret scan; both mirrors are pinned by drift tests.
# Adding a credential here is what makes every one of those cover it.
CREDENTIAL_CATALOG: dict[str, CredentialSpec] = {
    # --- Core infra (required for app to function) ---
    "NEO4J_PASSWORD": CredentialSpec(
        description="Neo4j database password",
        required=True,
    ),
    "SESSION_SECRET_KEY": CredentialSpec(
        description="Session cookie signing key (32+ random bytes)",
        required=True,
    ),
    # --- Signup gate ---
    "SIGNUP_INVITE_CODE": CredentialSpec(
        description="Registration invite code — unset leaves signup open",
        required=False,
    ),
    # --- AI providers (required for INTELLIGENCE_TIER=full) ---
    "OPENAI_API_KEY": CredentialSpec(
        description="OpenAI API key — embeddings + LLM (INTELLIGENCE_TIER=full)",
        required=False,
        expected_prefix="sk-",
    ),
    "ANTHROPIC_API_KEY": CredentialSpec(
        description="Anthropic API key — only when LLMConfig.provider=anthropic",
        required=False,
    ),
    "HF_API_TOKEN": CredentialSpec(
        description="HuggingFace Inference API token (BAAI/bge-m3 — staged until Arc 3, ADR-083)",
        required=False,
        expected_prefix="hf_",
    ),
    "DEEPGRAM_API_KEY": CredentialSpec(
        description="Deepgram API key — voice journal transcription",
        required=False,
    ),
    # --- Firefly III finance sidecar (ADR-051) ---
    "FIREFLY_APP_KEY": CredentialSpec(
        description="Firefly III APP_KEY (base64:... format, 32 bytes)",
        required=False,
    ),
    "FIREFLY_DB_PASSWORD": CredentialSpec(
        description="Firefly III Postgres password",
        required=False,
    ),
    "FIREFLY_PAT_PERSONAL": CredentialSpec(
        description="Firefly Personal Access Token — Mike's personal account",
        required=False,
    ),
    "FIREFLY_PAT_SKUEL": CredentialSpec(
        description="Firefly Personal Access Token — SKUEL business account",
        required=False,
    ),
    # --- Stripe → Firefly revenue sync ---
    "STRIPE_WEBHOOK_SECRET": CredentialSpec(
        description="Stripe webhook signing secret (whsec_... format)",
        required=False,
    ),
    # --- Transactional email (required when EMAIL_ENABLED=true) ---
    "RESEND_API_KEY": CredentialSpec(
        description="Resend API key — password reset emails (gated by EMAIL_ENABLED)",
        required=False,
    ),
    # --- Dev/test accounts (local development only) ---
    "TEST_ADMIN_PASSWORD": CredentialSpec(
        description="Test admin account password (local dev/integration tests)",
        required=False,
    ),
    "TEST_USER_PASSWORD": CredentialSpec(
        description="Test regular user password (local dev/integration tests)",
        required=False,
    ),
}


# Values that auto-migration should *not* copy into the backend. Captures the
# common placeholder patterns from the `.env.example`-style templates so a
# half-filled template doesn't end up persisting into the keychain.
#
# `scripts/git-hooks/secret-scan.sh` implements a deliberately broader rule and
# `tests/unit/scripts/test_secret_scan.py` drives the hook with every member of
# this set, so the hook never reports a value this funnel would accept.
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
        # The fixture string `HuggingFaceEmbeddingAdapter`'s own tests construct
        # with. It is long enough to satisfy a presence check and matches no other
        # arm here, so this entry is the only thing between it and the keychain.
        "test-token",
    }
)


def _is_placeholder(value: str | None) -> bool:
    """True if `value` is empty or a known template placeholder.

    The `your-` test looks anywhere in the value, not only at its start: the
    convention routinely sits behind a provider prefix, and `.env.example`'s own
    `sk-your-openai-key` and `sk-ant-your-anthropic-key` are exactly that shape.
    `scripts/git-hooks/secret-scan.sh` reads them the same way for the same
    reason. A real credential containing the literal `your-` is not a case worth
    protecting against the one this catches — a copied template overwriting a
    valid stored credential with a public string.
    """
    if not value:
        return True
    # Substring, not prefix, so a new template needs no list update.
    if "your-" in value:
        return True
    return value in _PLACEHOLDER_VALUES


class KeyringBackend:
    """OS-keychain credential storage — the default backend.

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

    READ_ONLY: ClassVar[bool] = False

    SERVICE = "skuel"
    INDEX_PATH = Path.home() / ".config" / "skuel" / "keyring-index.json"

    def __init__(self) -> None:
        # Import lazily — the env backend must not pay the import cost, which
        # touches D-Bus on Linux and has no daemon to reach on a droplet.
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


class EnvBackend:
    """The process environment, read-only — the headless shape.

    Selected by ``SKUEL_CREDENTIAL_BACKEND=env`` where no keychain daemon
    exists: the droplet (compose loads ``/opt/skuel/secrets.env`` into the
    container environment), CI, an ssh session with no D-Bus.

    Writes raise rather than no-op. A process cannot durably store a
    credential in its own environment, and a setup tool that appeared to
    succeed while discarding the key is worse than one that refuses.
    """

    READ_ONLY: ClassVar[bool] = True

    def get(self, key: str, default: str | None = None) -> str | None:
        """Read the credential from the process environment.

        A placeholder reads as absent. `.env.example` is meant to be copied, so
        the environment is exactly where `your-neo4j-password` arrives — and a
        credential that is *present but unusable* fails at the first
        authentication instead of at the boot check that exists to catch it.
        `get_credential()` applies the same rule to an env value reaching it by
        fallback, so both backends treat one identically.
        """
        value = os.getenv(key)
        return default if _is_placeholder(value) else value

    def exists(self, key: str) -> bool:
        """True if the environment carries a usable value for the key."""
        return self.get(key) is not None

    def list_keys(self) -> list[str]:
        """Catalog credentials the environment actually carries."""
        return [key for key in CREDENTIAL_CATALOG if self.exists(key)]

    def set(self, key: str, value: str) -> NoReturn:  # noqa: ARG002 — backend interface
        """Always raises — the environment is not writable storage."""
        raise ConfigurationError(
            f"Cannot store '{key}': SKUEL_CREDENTIAL_BACKEND=env is read-only. "
            f"Set the value in the environment this process is started with "
            f"(on the droplet: /opt/skuel/secrets.env, loaded by compose)."
        )

    def delete(self, key: str) -> NoReturn:
        """Always raises — the environment is not writable storage."""
        raise ConfigurationError(
            f"Cannot delete '{key}': SKUEL_CREDENTIAL_BACKEND=env is read-only. "
            f"Remove the value from the environment this process is started with."
        )


# Type alias for "anything with the credential-backend interface".
# Used in get_active_backend() to express that either class is acceptable.
CredentialBackend = KeyringBackend | EnvBackend

_BACKENDS: dict[str, type[KeyringBackend] | type[EnvBackend]] = {
    "keyring": KeyringBackend,
    "env": EnvBackend,
}


def get_active_backend() -> CredentialBackend:
    """Return the credential backend selected by ``SKUEL_CREDENTIAL_BACKEND``.

    Values:
        ``"keyring"`` — OS keychain. The default: desktop development, where a
                        gnome-keyring / kwallet / Keychain / Credential Locker
                        session exists.
        ``"env"``     — the process environment, read-only. Headless: droplet,
                        CI, ssh.

    Raises:
        ConfigurationError: on any other value. Selecting a backend by typo is
            how a machine ends up reading credentials from somewhere nobody
            wrote them, so an unknown selector fails rather than falling back.
    """
    name = os.getenv("SKUEL_CREDENTIAL_BACKEND", "keyring").strip().lower()
    backend_class = _BACKENDS.get(name)
    if backend_class is None:
        raise ConfigurationError(
            f"SKUEL_CREDENTIAL_BACKEND={name!r} is not a credential backend. "
            f"Use 'keyring' (desktop, the default) or 'env' (headless — droplet, CI)."
        )
    return backend_class()


def get_credential(key: str, fallback_to_env: bool = True) -> str | None:
    """Fetch a credential from the active backend, with env fallback.

    Args:
        key: The credential key (e.g. ``"HF_API_TOKEN"``).
        fallback_to_env: If the backend doesn't have a value, check
            ``os.getenv(key)`` — and, for a key in ``CREDENTIAL_CATALOG``,
            auto-migrate that value into a writable backend so subsequent
            reads are direct. Defaults True.

    Returns:
        The credential value, or None if not found in either location.

    Raises:
        ConfigurationError: if ``SKUEL_CREDENTIAL_BACKEND`` names no backend.

    Behavior matrix:
        backend_has_value      → return it
        env_has_value          → return it; auto-migrate when the key is a
                                 catalog credential and the backend is writable
        neither                → return None
        backend_read_fails     → fall through to env (no auto-migration)
                                 D-Bus can be unreachable mid-session; a
                                 credential read must not crash on it.
    """
    backend = get_active_backend()

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
        # Catalog-gated: only a declared credential is ever written into the
        # backend. Callers read connection config (NEO4J_URI, NEO4J_USERNAME)
        # through this same funnel, and storing those makes the keychain a
        # second source of truth that goes stale the day the database moves.
        if not backend.READ_ONLY and key in CREDENTIAL_CATALOG:
            try:
                backend.set(key, env_value)
                logger.info(f"Auto-migrated {key} from environment to {type(backend).__name__}")
            except Exception as e:  # safety-net: never block on a migration failure
                logger.warning(f"Auto-migration failed for {key}: {e}")
        return env_value

    return None
