"""Pin the catalog filter in ``scripts/migrate_secrets_to_keychain.py``.

Why this file exists
--------------------
The script writes to the keychain directly — it never calls `get_credential()`,
so the funnel's own catalog gate does not cover it. `parse_credentials` is that
gate's counterpart on this path, and it is the whole contract for what a
migration is allowed to store.

Both of the script's file sources need it, for different reasons. `app/.env` is
mostly non-secret config — `NEO4J_URI`, `APP_PORT`, `INTELLIGENCE_TIER`, vault
paths — and is a migration source because a legacy `.env` can still carry
credentials. `~/.config/skuel/secrets.env` is the dedicated secrets file, but it
also carries `NEO4J_AUTH` for Docker Compose `${VAR}` interpolation.

Storing either kind is the same defect: a keychain that answers `NEO4J_URI` is a
second source of truth for where the database lives, and it goes stale the day
the database moves. So both halves of the filter are asserted below — the names
that must come through, and the names that must not.

The other two cases here are about what a *value* is. `app/.env` overrides
`secrets.env`, and the script offers to delete `secrets.env` afterwards, so a
value admitted wrongly does not merely add a bad keychain entry — it replaces a
good one and then the plaintext original is offered up for deletion. A
placeholder copied from `.env.example` and a quoted dotenv value are the two
ways that happens.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (matches test_dead_modules.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import migrate_secrets_to_keychain as mig  # type: ignore[import-not-found]
import pytest

from core.config.credential_store import CREDENTIAL_CATALOG


class _FakeKeyring:
    """Stands in for the `keyring` package — records what reaches the keychain."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, key: str, value: str) -> None:
        self.store[(service, key)] = value

    def get_password(self, service: str, key: str) -> str | None:
        return self.store.get((service, key))

    def get_keyring(self) -> "_FakeKeyring":
        return self


# Every fixture value below has to clear the commit-time secret scan, which
# reads this file like any other: a credential name assigned a 20+ character
# non-placeholder is what it exists to block, and a fixture is
# indistinguishable from the real thing. Two of its placeholder forms are used
# here — `<...>`, which must span the WHOLE value (so a *quoted* one does not
# qualify), and anything under 20 characters. That is why the quoted cases are
# short rather than bracketed.
LEGACY_ENV = """\
# SKUEL Environment Configuration
SKUEL_ENVIRONMENT=local
NEO4J_URI=neo4j+s://d2d160c4.databases.neo4j.io
NEO4J_USERNAME=d2d160c4
NEO4J_PASSWORD=<a-neo4j-password>
OPENAI_API_KEY=<an-openai-key>
INTELLIGENCE_TIER=full
APP_PORT=8000
VAULT_ROOT=/home/someone/0bsidian/skuel
SIGNUP_INVITE_CODE=<an-invite-code>
"""


def test_it_takes_the_credentials(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(LEGACY_ENV)

    found = mig.parse_credentials(env_file)

    assert found == {
        "NEO4J_PASSWORD": "<a-neo4j-password>",
        "OPENAI_API_KEY": "<an-openai-key>",
        "SIGNUP_INVITE_CODE": "<an-invite-code>",
    }


def test_it_leaves_connection_config_alone(tmp_path: Path) -> None:
    """`NEO4J_URI` and `NEO4J_USERNAME` sit two lines from the password.

    They are read through `get_credential()` by real callers, so "it goes
    through the funnel" is not the test — catalog membership is.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(LEGACY_ENV)

    found = mig.parse_credentials(env_file)

    for key in ("NEO4J_URI", "NEO4J_USERNAME", "SKUEL_ENVIRONMENT", "APP_PORT", "VAULT_ROOT"):
        assert key not in found

    # Stated as the rule, not the sample: nothing outside the catalog gets through.
    assert set(found) <= set(CREDENTIAL_CATALOG)


def test_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    assert mig.parse_credentials(tmp_path / "nonexistent.env") == {}


class TestTheBackendSelector:
    """`ensure_backend_env_var` has to read the selector's VALUE, not just find one.

    `env` became a valid value in this arc. Left in place after a keychain
    migration, the app keeps reading the process environment — so once
    `secrets.env` is deleted, a fresh shell has no credentials at all.
    """

    def test_it_replaces_a_non_keyring_selector(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("APP_PORT=8000\nSKUEL_CREDENTIAL_BACKEND=env\nLOG_LEVEL=INFO\n")

        mig.ensure_backend_env_var(env_file, assume_yes=True)

        assert "SKUEL_CREDENTIAL_BACKEND=keyring" in env_file.read_text()
        # The rest of the file is untouched.
        assert "APP_PORT=8000" in env_file.read_text()
        assert "LOG_LEVEL=INFO" in env_file.read_text()

    def test_it_leaves_an_existing_keyring_selector_alone(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        before = "SKUEL_CREDENTIAL_BACKEND=keyring\n"
        env_file.write_text(before)

        mig.ensure_backend_env_var(env_file, assume_yes=True)

        assert env_file.read_text() == before

    def test_it_appends_when_absent(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("APP_PORT=8000\n")

        mig.ensure_backend_env_var(env_file, assume_yes=True)

        assert "SKUEL_CREDENTIAL_BACKEND=keyring" in env_file.read_text()


def test_the_compose_only_name_never_migrates(tmp_path: Path) -> None:
    """`secrets.env` is the *dedicated* secrets file and is still filtered.

    It holds `NEO4J_AUTH` so Docker Compose can interpolate `${NEO4J_AUTH}`,
    which is not a catalog credential and is never read through the funnel.
    Taking the file whole stores it on every re-run — harmless in itself, but it
    puts a name in the keychain inventory that `get_credential()` refuses, and
    the two write paths then disagree about what a credential is.
    """
    secrets_file = tmp_path / "secrets.env"
    secrets_file.write_text("NEO4J_AUTH=neo4j/<password>\nNEO4J_PASSWORD=<a-neo4j-password>\n")

    found = mig.parse_credentials(secrets_file)

    assert found == {"NEO4J_PASSWORD": "<a-neo4j-password>"}
    # The unfiltered read is what the filter sits on top of — assert the value
    # is there to be dropped, so this cannot pass on a parser that saw nothing.
    assert "NEO4J_AUTH" in mig._parse_env_shaped_file(secrets_file)


def test_a_placeholder_never_migrates(tmp_path: Path) -> None:
    """`.env.example`'s own values, which is what a copied `.env` carries.

    Admitting one overwrites a valid stored credential with a public string —
    and the script then offers to delete the plaintext file that still held the
    real value.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NEO4J_PASSWORD=your-neo4j-password\n"
        "OPENAI_API_KEY=sk-your-openai-key\n"
        "DEEPGRAM_API_KEY=your-deepgram-key\n"
        "SESSION_SECRET_KEY=\n"
        "STRIPE_WEBHOOK_SECRET=  # not set yet\n"
    )

    assert mig.parse_credentials(env_file) == {}


def test_a_quoted_value_migrates_unquoted(tmp_path: Path) -> None:
    """Stored with its quotes, the app authenticates with a different string.

    Hand-edited `.env` files quote routinely, and dotenv — which is what reads
    these files at runtime — does not treat the quotes as part of the value.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        'NEO4J_PASSWORD="<a-pw>"\n'
        "OPENAI_API_KEY='<a-key>'\n"
        'RESEND_API_KEY="<a-val>"  # with a trailing comment\n'
        'ANTHROPIC_API_KEY="<a#b>"\n'
    )

    assert mig.parse_credentials(env_file) == {
        "NEO4J_PASSWORD": "<a-pw>",
        "OPENAI_API_KEY": "<a-key>",
        "RESEND_API_KEY": "<a-val>",
        # The `#` is inside the quotes, so it is part of the value, not a comment.
        "ANTHROPIC_API_KEY": "<a#b>",
    }


def test_a_commented_out_blank_is_not_a_value(tmp_path: Path) -> None:
    """`KEY=  # note` — dotenv returns the comment text, and it is not a credential."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NEO4J_PASSWORD=  # not set yet\n"
        "export OPENAI_API_KEY= # also not set\n"
        "RESEND_API_KEY=<a-val>\n"
    )

    assert mig.parse_credentials(env_file) == {"RESEND_API_KEY": "<a-val>"}


def test_a_quoted_hash_value_is_kept(tmp_path: Path) -> None:
    """A credential may legitimately begin with `#`; the quote is what says so.

    Dropping it on the decoded value loses a credential from a migration that
    then offers to delete the plaintext original — silent, and unrecoverable.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("NEO4J_PASSWORD=\"#a-pw\"\nOPENAI_API_KEY='#a-key'\n")

    assert mig.parse_credentials(env_file) == {
        "NEO4J_PASSWORD": "#a-pw",
        "OPENAI_API_KEY": "#a-key",
    }


def test_a_dollar_sign_survives_verbatim(tmp_path: Path) -> None:
    """Interpolation is off — a credential is a literal, not a template."""
    env_file = tmp_path / ".env"
    env_file.write_text("NEO4J_PASSWORD=<abc$def-not-a-variable>\n")

    assert mig.parse_credentials(env_file) == {"NEO4J_PASSWORD": "<abc$def-not-a-variable>"}


class TestTheSourceFileSurvivesWhatTheFilterRefuses:
    """The catalog filter and the offer to delete the source are one decision.

    Whatever the filter refuses stays in the file, which makes the file that
    value's only copy — `scripts/dev/with-secrets` exports the keyring index,
    and an uncatalogued name is never in it. `secrets.env` holds `NEO4J_AUTH`
    for the `${NEO4J_AUTH}` interpolation in `infrastructure/docker-compose.yml`,
    so deleting the file on the way past takes the local Neo4j sandbox with it.

    Driven through `main()` under `--yes`, which answers every prompt: the guard
    is the only thing between the refused name and a zero-filled file.
    """

    @pytest.fixture
    def run_migration(self, monkeypatch, tmp_path):
        """Run `main()` against a temp secrets file and a fake keychain."""
        fake = _FakeKeyring()
        monkeypatch.setitem(sys.modules, "keyring", fake)
        monkeypatch.setattr(sys, "argv", ["migrate_secrets_to_keychain.py", "--yes"])

        def _run(secrets_body: str) -> tuple[Path, _FakeKeyring]:
            secrets = tmp_path / "secrets.env"
            secrets.write_text(secrets_body)
            env_file = tmp_path / ".env"
            env_file.write_text("SKUEL_CREDENTIAL_BACKEND=keyring\n")

            def _paths() -> tuple[Path, Path]:
                return secrets, env_file

            monkeypatch.setattr(mig, "detect_paths", _paths)
            assert mig.main() == 0
            return secrets, fake

        return _run

    def test_a_refused_name_keeps_the_file(self, run_migration) -> None:
        body = "NEO4J_AUTH=neo4j/<password>\nNEO4J_PASSWORD=<a-neo4j-password>\n"

        secrets, fake = run_migration(body)

        assert secrets.exists(), "the only copy of NEO4J_AUTH was deleted"
        assert secrets.read_text() == body, "the file was zero-filled in place"
        assert not secrets.with_suffix(".env.bak").exists()
        # The catalog half still happened — this is a narrower deletion, not a
        # migration that quietly did nothing.
        assert fake.store[("skuel", "NEO4J_PASSWORD")] == "<a-neo4j-password>"
        assert ("skuel", "NEO4J_AUTH") not in fake.store

    def test_a_fully_migrated_file_is_still_deleted(self, run_migration) -> None:
        """The complement: the guard must not freeze the behaviour it narrows."""
        secrets, fake = run_migration("NEO4J_PASSWORD=<a-neo4j-password>\n")

        assert not secrets.exists()
        assert secrets.with_suffix(".env.bak").exists()
        assert fake.store[("skuel", "NEO4J_PASSWORD")] == "<a-neo4j-password>"
