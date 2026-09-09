"""Tests for the credential funnel — one backend, one write path.

The funnel's failure modes are all silent: a credential read from the wrong
place, a connection-config key stored as if it were a credential, a setup tool
that appears to store a key it discards. Each one is pinned here.

`KeyringBackend` is driven against a fake `keyring` module rather than the
developer's real keychain — the assertions are about *which* store the funnel
reaches and *what* it puts there, which a fake records exactly.
"""

import ast
import sys
from pathlib import Path

import pytest

from core.config.credential_setup import CredentialSetup
from core.config.credential_store import (
    CREDENTIAL_CATALOG,
    EnvBackend,
    KeyringBackend,
    get_active_backend,
    get_credential,
)
from core.errors import ConfigurationError


class _FakeKeyring:
    """Stands in for the `keyring` package — records what reaches the keychain."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, key: str, value: str) -> None:
        self.store[(service, key)] = value

    def get_password(self, service: str, key: str) -> str | None:
        return self.store.get((service, key))

    def delete_password(self, service: str, key: str) -> None:
        del self.store[(service, key)]

    def get_keyring(self) -> "_FakeKeyring":
        return self


@pytest.fixture
def fake_keychain(monkeypatch, tmp_path):
    """A KeyringBackend wired to an in-memory keychain and a temp index file.

    The stub is installed as the `keyring` module itself, because that is what
    `KeyringBackend.__init__` imports — so the real constructor runs unchanged
    and the test cannot pass by skipping it.
    """
    fake = _FakeKeyring()
    monkeypatch.setitem(sys.modules, "keyring", fake)
    monkeypatch.setenv("SKUEL_CREDENTIAL_BACKEND", "keyring")
    monkeypatch.setattr(KeyringBackend, "INDEX_PATH", tmp_path / "keyring-index.json")
    return fake


# ---------------------------------------------------------------------------
# Backend selection — two values, both explicit
# ---------------------------------------------------------------------------
class TestBackendSelection:
    def test_keyring_is_the_default(self, monkeypatch, fake_keychain) -> None:
        monkeypatch.delenv("SKUEL_CREDENTIAL_BACKEND", raising=False)
        assert isinstance(get_active_backend(), KeyringBackend)

    def test_env_selects_the_headless_backend(self, monkeypatch) -> None:
        monkeypatch.setenv("SKUEL_CREDENTIAL_BACKEND", "env")
        assert isinstance(get_active_backend(), EnvBackend)

    @pytest.mark.parametrize("value", ["fernet", "keychain", "Keyring ", "", "  "])
    def test_an_unknown_selector_fails_rather_than_falling_back(
        self, monkeypatch, value: str
    ) -> None:
        """A typo'd selector must not resolve to a backend nobody wrote to.

        `"Keyring "` is here because the selector is normalised (strip + lower)
        before the lookup — that arm has to keep working, or a stray space in a
        `.env` line takes the whole app down.
        """
        monkeypatch.setenv("SKUEL_CREDENTIAL_BACKEND", value)
        if value.strip().lower() in {"keyring", "env"}:
            get_active_backend()  # normalisation arm — no raise expected
            return
        with pytest.raises(ConfigurationError, match="not a credential backend"):
            get_active_backend()

    def test_the_selector_is_case_and_space_insensitive(self, monkeypatch, fake_keychain) -> None:
        monkeypatch.setenv("SKUEL_CREDENTIAL_BACKEND", "  KEYRING  ")
        assert isinstance(get_active_backend(), KeyringBackend)


# ---------------------------------------------------------------------------
# The write path and the read path are the same backend (F1)
# ---------------------------------------------------------------------------
class TestOneWritePath:
    def test_the_setup_tool_writes_where_get_credential_reads(self, fake_keychain) -> None:
        """Setup stores into the backend `get_credential()` reads.

        Two of them means a credential that stores successfully and never
        resolves — a silent failure on both sides of the funnel.
        """
        setup = CredentialSetup()
        setup.backend.set("OPENAI_API_KEY", "sk-written-by-the-setup-tool")

        assert fake_keychain.store[("skuel", "OPENAI_API_KEY")] == "sk-written-by-the-setup-tool"
        assert get_credential("OPENAI_API_KEY") == "sk-written-by-the-setup-tool"

    def test_a_stored_credential_wins_over_the_environment(
        self, monkeypatch, fake_keychain
    ) -> None:
        monkeypatch.setenv("DEEPGRAM_API_KEY", "from-the-environment")
        get_active_backend().set("DEEPGRAM_API_KEY", "from-the-keychain")

        assert get_credential("DEEPGRAM_API_KEY") == "from-the-keychain"

    def test_the_setup_tool_lists_what_it_stored(self, fake_keychain) -> None:
        """`list_keys()` is index-backed — a write that skips the index is invisible."""
        setup = CredentialSetup()
        setup.backend.set("RESEND_API_KEY", "re-a-value")

        assert setup.backend.list_keys() == ["RESEND_API_KEY"]


# ---------------------------------------------------------------------------
# Auto-migration is catalog-gated (fact 3)
# ---------------------------------------------------------------------------
class TestAutoMigrationIsCatalogGated:
    def test_a_catalog_credential_migrates_from_env(self, monkeypatch, fake_keychain) -> None:
        monkeypatch.setenv("SESSION_SECRET_KEY", "a-real-session-signing-key")

        assert get_credential("SESSION_SECRET_KEY") == "a-real-session-signing-key"
        assert fake_keychain.store[("skuel", "SESSION_SECRET_KEY")] == "a-real-session-signing-key"

    @pytest.mark.parametrize("key", ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_AUTH"])
    def test_connection_config_is_returned_but_never_stored(
        self, monkeypatch, fake_keychain, key: str
    ) -> None:
        """These reach the funnel from real callers and are NOT credentials.

        Storing one makes the keychain a second source of truth for where the
        database lives — one that goes stale the day the database moves. A
        keychain answering `NEO4J_USERNAME=neo4j` authenticates as the wrong
        user against Aura, which presents as Unauthorized, indistinguishable
        from a bad password.
        """
        monkeypatch.setenv(key, "neo4j+s://d2d160c4.databases.neo4j.io")

        assert get_credential(key) == "neo4j+s://d2d160c4.databases.neo4j.io"
        assert ("skuel", key) not in fake_keychain.store
        assert key not in get_active_backend().list_keys()

    def test_a_placeholder_never_migrates(self, monkeypatch, fake_keychain) -> None:
        monkeypatch.setenv("NEO4J_PASSWORD", "your-neo4j-password")

        assert get_credential("NEO4J_PASSWORD") is None
        assert ("skuel", "NEO4J_PASSWORD") not in fake_keychain.store

    def test_a_fixture_credential_never_migrates(self, monkeypatch, fake_keychain) -> None:
        """A test fixture reaching the environment must not plant a credential.

        The funnel is the only place that can refuse one. Nothing catches an
        unusable credential downstream: `HuggingFaceEmbeddingAdapter` gates on
        `if not api_key` and the setup tool reports a stored credential from
        `exists()` alone, so a non-token clears both presence checks and fails
        later as a 401, inside a retry wrapper.
        """
        monkeypatch.setenv("HF_API_TOKEN", "your-hf-token")

        assert get_credential("HF_API_TOKEN") is None
        assert ("skuel", "HF_API_TOKEN") not in fake_keychain.store

    def test_fallback_to_env_false_never_reaches_the_environment(
        self, monkeypatch, fake_keychain
    ) -> None:
        monkeypatch.setenv("HF_API_TOKEN", "hf-a-real-token")

        assert get_credential("HF_API_TOKEN", fallback_to_env=False) is None
        assert ("skuel", "HF_API_TOKEN") not in fake_keychain.store


# ---------------------------------------------------------------------------
# The headless shape
# ---------------------------------------------------------------------------
class TestEnvBackend:
    @pytest.fixture(autouse=True)
    def _select_env(self, monkeypatch) -> None:
        monkeypatch.setenv("SKUEL_CREDENTIAL_BACKEND", "env")

    def test_it_reads_the_process_environment(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-opt-skuel-secrets-env")
        assert get_credential("OPENAI_API_KEY") == "sk-from-opt-skuel-secrets-env"

    def test_a_missing_credential_is_none(self, monkeypatch) -> None:
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        assert get_credential("STRIPE_WEBHOOK_SECRET") is None

    def test_writes_raise_rather_than_silently_discarding(self) -> None:
        """A tool that reports success while dropping the key is the worse bug."""
        with pytest.raises(ConfigurationError, match="read-only"):
            EnvBackend().set("OPENAI_API_KEY", "sk-discarded")
        with pytest.raises(ConfigurationError, match="read-only"):
            EnvBackend().delete("OPENAI_API_KEY")

    def test_list_keys_reports_only_catalog_credentials_that_are_present(self, monkeypatch) -> None:
        for key in CREDENTIAL_CATALOG:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("NEO4J_PASSWORD", "present")
        monkeypatch.setenv("PATH_TO_SOMETHING_ELSE", "not-a-credential")

        assert EnvBackend().list_keys() == ["NEO4J_PASSWORD"]

    @pytest.mark.parametrize(
        "placeholder",
        [
            "your-neo4j-password",
            "your-anything",
            # `.env.example`'s own value: the convention sits behind a provider
            # prefix, so the check has to look past the start of the value.
            "sk-your-openai-key",
            "sk-ant-your-anthropic-key",
            "",
        ],
    )
    def test_a_placeholder_reads_as_absent(self, monkeypatch, placeholder: str) -> None:
        """`.env.example` is meant to be copied, so this is where placeholders arrive.

        Returning one makes a required credential look configured: the boot
        check that exists to catch a missing key passes, and the failure
        surfaces later as an authentication error against the database instead.
        The keyring path already applies this rule to an env value reaching it
        by fallback; both backends must agree.
        """
        monkeypatch.setenv("NEO4J_PASSWORD", placeholder)

        assert EnvBackend().get("NEO4J_PASSWORD") is None
        assert EnvBackend().exists("NEO4J_PASSWORD") is False
        assert "NEO4J_PASSWORD" not in EnvBackend().list_keys()
        assert get_credential("NEO4J_PASSWORD") is None

    def test_the_setup_tool_refuses_instead_of_pretending(self, capsys) -> None:
        """`run()` must return without prompting — the tool has nowhere to write."""
        CredentialSetup().run()

        out = capsys.readouterr().out
        assert "read-only" in out
        assert "Options:" not in out


# ---------------------------------------------------------------------------
# The catalog covers what the funnel actually reads
# ---------------------------------------------------------------------------
APP_ROOT = Path(__file__).resolve().parents[3]
FUNNEL_TREES = ("core", "adapters", "services_bootstrap", "scripts", "ui")

# Names read through get_credential() that are deliberately NOT credentials, and
# so must never be stored. Each is connection config: where the database is, and
# who we connect as. A keychain copy of either is a second source of truth that
# goes stale the day the database moves, and authenticating as the wrong user
# against Aura is indistinguishable from a bad password
# (docs/deployment/AURADB_MIGRATION_GUIDE.md § 6.1).
NON_CREDENTIAL_FUNNEL_READS = {
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_USER",
}


def _funnel_reads() -> set[str]:
    """Every literal name passed to `get_credential()` in first-party code.

    Under-approximates by design: a call whose first argument is a variable or a
    module constant (`get_credential(SESSION_SECRET_KEY_ENV)` in
    `adapters/inbound/auth/session.py`) is invisible to an AST walk, so this
    finds a subset. That is the right trade — every name it does find is
    certain, and a guard that missed nothing would need to resolve names it
    cannot.
    """
    names: set[str] = set()
    for tree in FUNNEL_TREES:
        for path in (APP_ROOT / tree).rglob("*.py"):
            try:
                parsed = ast.parse(path.read_text())
            except (OSError, SyntaxError):  # fmt: skip
                continue
            for node in ast.walk(parsed):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if called != "get_credential":
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    names.add(first.value)
    return names


class TestTheCatalogCoversTheFunnel:
    """Auto-migration is catalog-gated, so an uncatalogued read never reaches
    the keychain — and the setup tool, which walks the same catalog, cannot
    offer it. Both failures are silent, which is why this is a test rather than
    a census someone runs once.
    """

    def test_every_funnel_read_is_catalogued_or_declared_non_credential(self) -> None:
        found = _funnel_reads()
        assert found, "the AST walk found no get_credential() call sites — it has stopped working"

        unaccounted = found - set(CREDENTIAL_CATALOG) - NON_CREDENTIAL_FUNNEL_READS
        assert not unaccounted, (
            f"{sorted(unaccounted)} is read through get_credential() but is neither in "
            f"CREDENTIAL_CATALOG nor declared non-credential. If it is a credential, add "
            f"it to the catalog — until then it never migrates into the keychain and the "
            f"setup tool cannot store it. If it is connection config, add it to "
            f"NON_CREDENTIAL_FUNNEL_READS with the reason."
        )

    def test_the_declared_non_credentials_are_not_also_catalogued(self) -> None:
        """A name cannot be both — the gate would then store what it exists to refuse."""
        overlap = NON_CREDENTIAL_FUNNEL_READS & set(CREDENTIAL_CATALOG)
        assert not overlap, f"{sorted(overlap)} is declared non-credential AND catalogued"

    def test_the_walk_sees_the_call_sites_it_claims_to(self) -> None:
        """Positive control: without this, an AST walk that finds nothing passes."""
        found = _funnel_reads()
        # auth_ui.py's invite gate and neo4j_connection.py's username read are the
        # two ends of the question this class exists to answer.
        assert "SIGNUP_INVITE_CODE" in found
        assert "NEO4J_USERNAME" in found


# ---------------------------------------------------------------------------
# Catalog shape
# ---------------------------------------------------------------------------
class TestCredentialCatalog:
    def test_the_required_credentials_are_the_two_the_app_cannot_boot_without(self) -> None:
        required = {name for name, spec in CREDENTIAL_CATALOG.items() if spec.required}
        assert required == {"NEO4J_PASSWORD", "SESSION_SECRET_KEY"}

    def test_every_entry_describes_itself(self) -> None:
        """The description is what the setup tool shows next to the prompt."""
        undescribed = [name for name, spec in CREDENTIAL_CATALOG.items() if not spec.description]
        assert not undescribed
