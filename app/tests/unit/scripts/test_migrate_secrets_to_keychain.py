"""Pin the `app/.env` source in ``scripts/migrate_secrets_to_keychain.py``.

Why this file exists
--------------------
`app/.env` is mostly non-secret config — `NEO4J_URI`, `APP_PORT`,
`INTELLIGENCE_TIER`, vault paths. It is a migration source because a legacy
`.env` can still carry credentials, and it is the only tool that reads one; the
README sends people here for exactly that case.

Reading it whole would put connection config in the keychain, which is the
defect the credential funnel's catalog gate exists to prevent: a keychain that
answers `NEO4J_URI` is a second source of truth for where the database lives,
and it goes stale the day the database moves. So the filter is the contract,
and both halves of it are asserted below — the names that must come through,
and the names that must not.

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

from core.config.credential_store import CREDENTIAL_CATALOG

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

    found = mig.parse_env_file_credentials(env_file)

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

    found = mig.parse_env_file_credentials(env_file)

    for key in ("NEO4J_URI", "NEO4J_USERNAME", "SKUEL_ENVIRONMENT", "APP_PORT", "VAULT_ROOT"):
        assert key not in found

    # Stated as the rule, not the sample: nothing outside the catalog gets through.
    assert set(found) <= set(CREDENTIAL_CATALOG)


def test_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    assert mig.parse_env_file_credentials(tmp_path / "nonexistent.env") == {}


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

    assert mig.parse_env_file_credentials(env_file) == {}


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

    assert mig.parse_env_file_credentials(env_file) == {
        "NEO4J_PASSWORD": "<a-pw>",
        "OPENAI_API_KEY": "<a-key>",
        "RESEND_API_KEY": "<a-val>",
        # The `#` is inside the quotes, so it is part of the value, not a comment.
        "ANTHROPIC_API_KEY": "<a#b>",
    }


def test_a_dollar_sign_survives_verbatim(tmp_path: Path) -> None:
    """Interpolation is off — a credential is a literal, not a template."""
    env_file = tmp_path / ".env"
    env_file.write_text("NEO4J_PASSWORD=<abc$def-not-a-variable>\n")

    assert mig.parse_env_file_credentials(env_file) == {
        "NEO4J_PASSWORD": "<abc$def-not-a-variable>"
    }
