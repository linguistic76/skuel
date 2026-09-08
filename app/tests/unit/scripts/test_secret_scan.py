"""Pin ``scripts/git-hooks/secret-scan.sh`` — the commit- and push-time secret fence.

What this file guards
---------------------
The scan must catch six shapes. Five of them are easy to get wrong, in two
different ways:

===========================================  ====================================
shape                                         caught by
===========================================  ====================================
``sk-proj-…`` (OpenAI project key)            content pattern
``sk-ant-api03-…`` (Anthropic)                content pattern
``sk-<48>`` (legacy OpenAI)                   content pattern
Deepgram 40-hex                               assignment shape
AuraDB password (43-char base64url)           assignment shape
``SESSION_SECRET_KEY`` (43-char base64url)    assignment shape
===========================================  ====================================

The bottom three cannot be content patterns at all. They are prefix-free
high-entropy strings, so a regex matching them matches every hash, UUID and
lockfile digest in the tree — which is why the scan has a second half that keys
off the credential NAME and never inspects the value's appearance.

Every key below is generated from ``secrets`` (i.e. ``/dev/urandom``) at run
time. No real key, and no value that could be mistaken for one, appears in this
file or in its failure output.

Assignment-shape cases are composed through the helpers below rather than written
as inline f-strings. A source line that puts a literal catalog name beside a long
space-free token is itself an assignment-shape match, so writing the case out
literally makes this file un-committable — the scan blocks the commit that adds
its own test.

The negatives matter as much as the positives: a scan that blocks
``.env.example`` gets bypassed with ``SKUEL_ALLOW_SECRETS=1`` until it stops
being a fence at all. So the false-positive floor is asserted against the *live*
``.env.example`` and ``.env.production.example`` rather than a copied excerpt — a
placeholder added there later is covered without touching this file.
"""

from __future__ import annotations

import secrets
import string
import subprocess
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
HOOK_DIR = APP_ROOT / "scripts" / "git-hooks"
SCAN = HOOK_DIR / "secret-scan.sh"
PATTERNS_FILE = HOOK_DIR / "secret-patterns.txt"
CATALOG_FILE = HOOK_DIR / "credential-keys.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run_scan(*added_lines: str) -> subprocess.CompletedProcess[str]:
    """Feed synthetic diff-added lines to the real scan script."""
    diff = "".join(f"+{line}\n" for line in added_lines)
    return subprocess.run(
        ["bash", str(SCAN), "the test diff"],
        input=diff,
        capture_output=True,
        text=True,
        check=False,
    )


def detects(*added_lines: str) -> bool:
    return run_scan(*added_lines).returncode != 0


def as_diff(file_path: Path) -> list[str]:
    """Every line of a file, as if each were newly added in a diff."""
    return file_path.read_text().splitlines()


def alnum(n: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def inline_dict(key: str, value: str) -> str:
    """`config = {"KEY": "value"}` — a one-line dict literal."""
    return f'config = {{"{key}": "{value}"}}'


def subscript(key: str, value: str, quote: str = '"') -> str:
    """`config["KEY"] = "value"` — the Python/JS subscript form."""
    return f"config[{quote}{key}{quote}] = {quote}{value}{quote}"


def annotated(key: str, value: str, annotation: str) -> str:
    """`KEY: str = "value"` — a typed Python constant."""
    return f'{key}: {annotation} = "{value}"'


def read_data_file(path: Path) -> list[str]:
    """Non-comment, non-blank lines — the same filter the shell script applies."""
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


# Synthetic keys, generated per call so no fixed string ever lands in a fixture.
def anthropic_key() -> str:
    return "sk-ant-api03-" + secrets.token_urlsafe(72)


def openai_legacy_key() -> str:
    return "sk-" + alnum(48)


def openai_project_key() -> str:
    return "sk-proj-" + secrets.token_urlsafe(40)


def deepgram_key() -> str:
    return secrets.token_hex(20)  # 40 hex chars


def base64url_secret() -> str:
    return secrets.token_urlsafe(32)  # 43 chars — AuraDB / SESSION_SECRET_KEY shape


# ---------------------------------------------------------------------------
# The measured matrix — every row of it must now detect
# ---------------------------------------------------------------------------
class TestRequiredShapes:
    """The six shapes the scan is required to catch, one test each."""

    def test_anthropic_key_detected(self) -> None:
        assert detects(f"ANTHROPIC_API_KEY={anthropic_key()}")

    def test_anthropic_key_detected_by_content_alone(self) -> None:
        # Not merely by its assignment: a key pasted into a .py or a doc, with no
        # catalog name in sight, is the case the content half exists for.
        assert detects(f'client = Anthropic(api_key="{anthropic_key()}")')

    def test_legacy_openai_key_detected_by_content_alone(self) -> None:
        assert detects(f'OPENAI = "{openai_legacy_key()}"')

    def test_deepgram_key_detected(self) -> None:
        assert detects(f"DEEPGRAM_API_KEY={deepgram_key()}")

    def test_auradb_password_detected(self) -> None:
        assert detects(f"NEO4J_PASSWORD={base64url_secret()}")

    def test_session_secret_key_detected(self) -> None:
        assert detects(f"SESSION_SECRET_KEY={base64url_secret()}")

    def test_openai_project_key_detected(self) -> None:
        assert detects(f'key = "{openai_project_key()}"')


class TestAssignmentShapeCoverage:
    """Every catalog name, not just the ones that happened to get a test row."""

    @pytest.mark.parametrize("key", read_data_file(CATALOG_FILE))
    def test_every_catalog_key_is_caught_when_assigned(self, key: str) -> None:
        assert detects(f"{key}={base64url_secret()}")

    @pytest.mark.parametrize("key", read_data_file(CATALOG_FILE))
    def test_export_form_is_caught(self, key: str) -> None:
        # `.envrc` and shell snippets write `export KEY=value`.
        assert detects(f"export {key}={base64url_secret()}")

    def test_quoted_and_indented_forms_are_caught(self) -> None:
        secret = base64url_secret()
        assert detects(f'  NEO4J_PASSWORD="{secret}"')
        assert detects(f"  NEO4J_PASSWORD='{secret}'")

    def test_trailing_comment_does_not_hide_the_value(self) -> None:
        assert detects(f"NEO4J_PASSWORD={base64url_secret()}  # local only, honest")

    @pytest.mark.parametrize("key", read_data_file(CATALOG_FILE))
    def test_yaml_mapping_form_is_caught(self, key: str) -> None:
        """`KEY: value`, the form the compose files use, is the same leak as `KEY=value`."""
        assert detects(f"      {key}: {base64url_secret()}")

    @pytest.mark.parametrize("key", read_data_file(CATALOG_FILE))
    def test_json_data_literal_is_caught(self, key: str) -> None:
        """`"KEY": "value"` — JSON, and Python/JS dict literals."""
        assert detects(f'        "{key}": "{base64url_secret()}",')

    def test_composite_and_angle_bracket_placeholders(self) -> None:
        """`NEO4J_AUTH=neo4j/<password>` is a doc placeholder, not a leak.

        Its placeholder half is SECOND, so the `your-` arm never sees it — the value
        starts `neo4j/`. `SETUP.md` and `infrastructure/README.md` both carry this
        line. A real credential contains no angle brackets.
        """
        assert not detects(
            "NEO4J_AUTH=neo4j/<your-password>",
            "NEO4J_AUTH=neo4j/<password>",
            "OPENAI_API_KEY=<your-openai-key>",
            "NEO4J_PASSWORD=<must-match-the-infrastructure-env-file>",
        )
        assert detects(f"NEO4J_AUTH=neo4j/{base64url_secret()}")

    def test_a_quoted_passphrase_is_measured_whole(self) -> None:
        """A passphrase is one value, not four.

        The length floor has to see past the first space, or
        `NEO4J_PASSWORD="correct horse battery staple"` clears it on a five-letter
        first word. Neo4j and the local test accounts can legitimately hold one.
        """
        assert detects('NEO4J_PASSWORD="a quite long spoken pass phrase"')
        assert detects("TEST_USER_PASSWORD='another long spoken passphrase'")

    def test_inline_dict_literal_is_caught(self) -> None:
        """A dict literal is as often inline as it is one key per line."""
        assert detects(inline_dict("NEO4J_PASSWORD", base64url_secret()))

    def test_subscript_assignment_is_caught(self) -> None:
        """`config["KEY"] = value` — the Python/JS form, with `]` before the `=`."""
        assert detects(subscript("NEO4J_PASSWORD", base64url_secret()))
        assert detects(subscript("SESSION_SECRET_KEY", base64url_secret(), quote="'"))

    @pytest.mark.parametrize("prefix", ["# ", "#   ", "// ", "-- ", "; ", " *  "])
    def test_commented_assignment_is_caught(self, prefix: str) -> None:
        """A credential parked in a commented config example is in history all the same."""
        assert detects(f"{prefix}NEO4J_PASSWORD={base64url_secret()}")

    def test_commented_export_is_caught(self) -> None:
        assert detects(f"#   export DEEPGRAM_API_KEY={base64url_secret()}")

    def test_a_credential_in_an_interpolation_fallback_is_caught(self) -> None:
        """`${VAR:-default}` carries a real value, so the fallback is measured.

        Compose uses this idiom live (`${FIREFLY_DB_PASSWORD:-firefly-local-dev}`).
        Exempting anything that starts with `$` would let a production credential
        hide inside the fallback of a reference to itself.
        """
        secret = base64url_secret()
        assert detects(f"NEO4J_PASSWORD=${{NEO4J_PASSWORD:-{secret}}}")
        assert detects(f"      MYSQL_PASSWORD: ${{FIREFLY_DB_PASSWORD:-{secret}}}")
        assert detects(f"      - GF_SECURITY_ADMIN_PASSWORD=${{GRAFANA_PASSWORD:-{secret}}}")

    def test_the_live_compose_interpolations_stay_clean(self) -> None:
        """A reference, and a fallback under the floor, carry no secret."""
        assert not detects(
            "      MYSQL_PASSWORD: ${FIREFLY_DB_PASSWORD:-firefly-local-dev}",
            "      DB_PASSWORD: ${FIREFLY_DB_PASSWORD:-firefly-local-dev}",
            "      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}",
            "      DEEPGRAM_API_KEY: ${DEEPGRAM_API_KEY:-}",
            "      NEO4J_PASSWORD: ${NEO4J_PASSWORD}",
            '      NEO4J_AUTH: "${NEO4J_AUTH}"',
            "      APP_KEY: ${FIREFLY_APP_KEY}              # MUST start with base64:",
            "export SESSION_SECRET_KEY=$SESSION_SECRET_KEY_FROM_SOMEWHERE_ELSE",
        )

    def test_quoted_compose_list_scalar_is_caught(self) -> None:
        """`- "KEY=value"` — compose writes env lists as a quoted scalar.

        The quote wraps name AND value there, so the assignment lead has to take an
        opening quote. It does not let a data literal in: `"KEY": "prose"` closes
        its quote before the separator.
        """
        assert detects(f'      - "GF_SECURITY_ADMIN_PASSWORD={base64url_secret()}"')
        assert detects(f"      - 'MYSQL_PASSWORD={base64url_secret()}'")
        assert not detects(
            '        "OPENAI_API_KEY": "OpenAI API key for embeddings and AI features"'
        )

    def test_annotated_assignment_is_caught(self) -> None:
        """`KEY: str = value` — a typed Python constant.

        The bare `:` of a YAML mapping and the `:` of a type annotation look alike;
        without the annotation arm the matcher reads `str` as the value and clears
        the floor on three characters.
        """
        assert detects(annotated("SESSION_SECRET_KEY", base64url_secret(), "str"))
        assert detects(annotated("NEO4J_PASSWORD", base64url_secret(), "Final[str]"))

    def test_the_key_survives_redaction_in_an_inline_literal(self) -> None:
        """Redaction anchors on the key, not the line's first `=`.

        `config = {"NEO4J_PASSWORD": …}` assigns `config` first; redacting from
        there swallows the one thing the author needs — which credential to rotate.
        """
        secret = base64url_secret()
        result = run_scan(inline_dict("NEO4J_PASSWORD", secret))
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert secret not in combined
        assert "NEO4J_PASSWORD" in combined

    def test_a_dict_of_credential_descriptions_is_not_a_leak(self) -> None:
        """The data-literal form requires a SPACE-FREE value, and this pins why.

        This is the one place the two syntaxes disagree — the assignment branch
        measures a quoted passphrase whole, this one will not — so it is a
        deliberate gap with a measured price on the other side.

        A dict keyed by a credential name, in this repo, holds a description.
        Accepting a spaced value here reports six lines in the files that ARE this
        scan's source of truth: `core/config/environment_validator.py`,
        `CredentialSetup.CREDENTIALS`, and this test file and the hook README that
        quote them. No syntactic signal separates a description of a credential
        from a passphrase.

        The cost: a SPACED passphrase hard-coded in a dict literal is not caught.
        A space-free one is, in every form. If the rule is ever removed, this test
        fails and the catalog-files question has to be answered again.
        """
        assert not detects(
            '        "OPENAI_API_KEY": "OpenAI API key for embeddings and AI features"',
            '        "NEO4J_PASSWORD": "Neo4j password (defaults to password)",',
            '        "NEO4J_PASSWORD": {',
            '            "description": "Session cookie signing key (32+ random bytes)",',
        )
        # The documented gap, pinned: spaced in a data literal is out of reach...
        assert not detects('{"NEO4J_PASSWORD": "correct horse battery staple"}')
        # ...while the same passphrase in the assignment form is caught.
        assert detects('NEO4J_PASSWORD="correct horse battery staple"')

    def test_interpolation_references_are_not_values(self) -> None:
        """`docker-compose.yml` assigns credentials by reference, not by value.

        `DEEPGRAM_API_KEY: ${DEEPGRAM_API_KEY:-}` is 23 characters, so it clears the
        length floor; without the `$` guard the compose files stop being editable.
        """
        assert not detects(
            "      NEO4J_PASSWORD: ${NEO4J_PASSWORD}",
            '      "NEO4J_PASSWORD": "${NEO4J_PASSWORD_FROM_THE_ENVIRONMENT}"',
            "      DEEPGRAM_API_KEY: ${DEEPGRAM_API_KEY:-}",
            "      FIREFLY_PAT_PERSONAL: ${FIREFLY_PAT_PERSONAL_LONG_ENOUGH_NAME}",
            "export SESSION_SECRET_KEY=$SESSION_SECRET_KEY_FROM_SOMEWHERE_ELSE",
        )


# ---------------------------------------------------------------------------
# The false-positive floor — a fence that cries wolf gets bypassed
# ---------------------------------------------------------------------------
class TestFalsePositiveFloor:
    @pytest.mark.parametrize("name", [".env.example", ".env.production.example"])
    def test_committed_env_templates_stay_committable(self, name: str) -> None:
        result = run_scan(*as_diff(APP_ROOT / name))
        assert result.returncode == 0, (
            f"{name} no longer commits cleanly:\n{result.stderr}\n"
            "A placeholder there must be empty, under 20 characters, or `your-`-prefixed."
        )

    def test_placeholder_values_agree_with_the_credential_funnel(self) -> None:
        """The hook and `_is_placeholder` must call the same values placeholders.

        The script implements the rule as "empty, under 20 chars, or `your-`-prefixed",
        which subsumes `_PLACEHOLDER_VALUES` today. This drives the real script with
        every member of the real set, so a future placeholder that escapes those two
        arms fails here instead of silently blocking a legitimate template commit.
        """
        from core.config.credential_store import _PLACEHOLDER_VALUES

        catalog = read_data_file(CATALOG_FILE)
        lines = [f"{key}={value}" for key in catalog for value in _PLACEHOLDER_VALUES]
        result = run_scan(*lines)
        assert result.returncode == 0, (
            f"A member of _PLACEHOLDER_VALUES is reported as a secret:\n{result.stderr}"
        )

    def test_the_length_floor_and_its_cost_are_deliberate(self) -> None:
        """The assignment half treats a short value as a placeholder. That is a choice.

        `_is_placeholder` calls only the empty string, a `your-` prefix and its own
        `_PLACEHOLDER_VALUES` list placeholders, so the hook's floor is strictly
        broader — and it has to be. `.env.example` and `SETUP.md` carry placeholders
        that fit none of those arms (asserted below); an exact-list rule reports all
        of them, and a scan that blocks the committed templates gets bypassed.

        The cost is a locally-chosen credential under the floor. It is bounded: every
        provider-issued credential in the catalog is far longer, and provider keys are
        caught by the content half however they are assigned. If the floor is ever
        removed, this test fails and the template question has to be answered again.
        """
        # The live template placeholders no exact-list rule would cover.
        assert not detects(
            "FIREFLY_DB_PASSWORD=firefly-local-dev",  # 17 chars, not `your-`-prefixed
            "OPENAI_API_KEY=sk-your-openai-key",  # 18 chars, prefix is `sk-your-`
            "OPENAI_API_KEY=<your-openai-key>",  # 17 chars, SETUP.md form
            # 25 chars, and `your-` sits behind the provider prefix — which is why
            # that arm matches anywhere in the value rather than only at its start.
            "# ANTHROPIC_API_KEY=sk-ant-your-anthropic-key   # [SECRET]",
        )
        # The gap that buys: a short hand-picked password is not reported.
        assert not detects(f"TEST_ADMIN_PASSWORD={alnum(19)}")
        # One character more, and it is.
        assert detects(f"TEST_ADMIN_PASSWORD={alnum(20)}")

    def test_lockfile_digests_are_not_secrets(self) -> None:
        sha512 = secrets.token_urlsafe(64)
        sha256 = secrets.token_hex(32)
        uuid_like = "-".join(secrets.token_hex(n) for n in (4, 2, 2, 2, 6))
        assert not detects(
            f'      "integrity": "sha512-{sha512}==",',
            f'hash = "sha256:{sha256}"',
            f"    id: {uuid_like}",
            f"    revision = {alnum(40)}",
        )

    def test_hook_documentation_of_its_own_bypass_is_not_a_leak(self) -> None:
        """`#   SKUEL_ALLOW_SECRETS=1 git commit ...` — a commented usage line."""
        assert not detects(
            "#   SKUEL_ALLOW_SECRETS=1 git commit ...   # skip secret scan only",
            "# SIGNUP_INVITE_CODE=choose-a-code",
        )

    def test_a_non_catalog_name_is_not_flagged(self) -> None:
        # Paths, hosts and tiers are config: long, sometimes high-entropy, not secret.
        assert not detects(
            "SKUEL_USER_VAULTS_ROOT=/home/someone/vaults/and/a/long/path",
            "NEO4J_URI=neo4j+s://d2d160c4.databases.neo4j.io",
            f"BUILD_REVISION={alnum(40)}",
        )

    def test_removed_lines_are_never_scanned(self) -> None:
        """Deleting a secret must not block the commit that deletes it."""
        diff = f"-NEO4J_PASSWORD={base64url_secret()}\n"
        result = subprocess.run(
            ["bash", str(SCAN), "the test diff"],
            input=diff,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_empty_diff_is_clean(self) -> None:
        result = subprocess.run(
            ["bash", str(SCAN), "the test diff"],
            input="",
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Redaction — a fence that echoes the key it caught is its own leak
# ---------------------------------------------------------------------------
class TestRedaction:
    def test_content_match_is_not_echoed(self) -> None:
        key = anthropic_key()
        result = run_scan(f'client = Anthropic(api_key="{key}")')
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert key not in combined
        assert "[REDACTED]" in combined

    def test_a_second_credential_on_the_line_is_redacted_too(self) -> None:
        """Every redaction applies to every printed line, not just the matching one.

        One line can carry two credentials. Reporting them separately with only the
        current expression prints each secret verbatim inside the other's report —
        the scan would leak exactly what it exists to contain.
        """
        openai = openai_project_key()
        anthropic = anthropic_key()
        result = run_scan(f'k1 = "{openai}" ; k2 = "{anthropic}"')
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert openai not in combined
        assert anthropic not in combined
        # Both reports fire, and both are clean.
        assert "OpenAI key" in combined
        assert "Anthropic key" in combined

    def test_assignment_match_is_not_echoed(self) -> None:
        secret = base64url_secret()
        result = run_scan(f"NEO4J_PASSWORD={secret}")
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert secret not in combined
        # The NAME survives redaction — it is what tells the author what to rotate.
        assert "NEO4J_PASSWORD" in combined


# ---------------------------------------------------------------------------
# Drift — the two data files, and the two hooks that share them
# ---------------------------------------------------------------------------
# Names in credential-keys.txt that are NOT funnel credentials. What puts a name
# in that file is that assigning it a literal is a leak — a wider question than
# whether `get_credential()` manages it. Declared here so the drift test still
# pins the mirror exactly in both directions: an unexplained extra name fails.
NON_FUNNEL_KEYS = {
    # Docker Compose reads it directly for ${VAR} interpolation
    # (infrastructure/docker-compose.yml), and its `user/password` value carries a
    # real password. Never read through get_credential().
    "NEO4J_AUTH",
    # Not a stored credential — the key that decrypts the whole Fernet store
    # (core/config/credential_store.py). Leaking it exposes every key in the store.
    "SKUEL_MASTER_KEY",
    # Read through get_credential() (adapters/inbound/auth_ui.py) but absent from
    # the catalog, and its name matches none of SKUEL019's credential-shaped
    # suffixes — so nothing else in the tree treats it as one. Leaking it opens
    # registration; DO_MIGRATION_GUIDE.md calls it the throttle on node-cap growth
    # and LLM-cost abuse.
    "SIGNUP_INVITE_CODE",
    # Credential env keys the deployed services read, enumerated from the compose
    # files. Each is an interpolation there today, so a literal in its place is the
    # leak. app/docker-compose.yml lines 114, 136, 142, 171, 224.
    "MYSQL_PASSWORD",
    "DB_PASSWORD",
    "APP_KEY",
    "FIREFLY_III_ACCESS_TOKEN",
    "GF_SECURITY_ADMIN_PASSWORD",
    "GRAFANA_PASSWORD",
}


class TestCatalogDrift:
    """`credential-keys.txt` mirrors CredentialSetup.CREDENTIALS, plus declared extras.

    Bash cannot import Python, so the names are duplicated. This is the same
    arrangement (and the same failure mode) as
    `scripts/lint_skuel.py::SkuelLinter.CREDENTIAL_CATALOG`: if the mirror drifts,
    a newly-added credential silently stops being scanned for.
    """

    def test_mirror_matches_credential_setup_plus_declared_extras(self) -> None:
        from core.config.credential_setup import CredentialSetup

        expected = set(CredentialSetup.CREDENTIALS) | NON_FUNNEL_KEYS
        mirrored = set(read_data_file(CATALOG_FILE))

        missing = expected - mirrored
        extra = mirrored - expected
        assert not missing, (
            f"scripts/git-hooks/credential-keys.txt is missing keys present in "
            f"CredentialSetup.CREDENTIALS: {sorted(missing)}. Add them — until then "
            f"the secret scan does not look for them."
        )
        assert not extra, (
            f"scripts/git-hooks/credential-keys.txt has keys in neither "
            f"CredentialSetup.CREDENTIALS nor NON_FUNNEL_KEYS: {sorted(extra)}. "
            f"A credential-bearing name outside the funnel belongs in NON_FUNNEL_KEYS "
            f"with a reason; anything else is drift."
        )

    def test_declared_extras_are_actually_outside_the_funnel(self) -> None:
        """A name that joins the catalog must leave NON_FUNNEL_KEYS, not sit in both."""
        from core.config.credential_setup import CredentialSetup

        overlap = NON_FUNNEL_KEYS & set(CredentialSetup.CREDENTIALS)
        assert not overlap, (
            f"{sorted(overlap)} is in CredentialSetup.CREDENTIALS now — drop it from "
            f"NON_FUNNEL_KEYS so the mirror pins it as a funnel credential."
        )

    def test_the_compose_auth_credential_is_scanned(self) -> None:
        """`NEO4J_AUTH: "neo4j/<password>"` is a leak the content half cannot see."""
        assert detects(f'      NEO4J_AUTH: "neo4j/{base64url_secret()}"')
        assert not detects('      NEO4J_AUTH: "${NEO4J_AUTH}"')

    def test_the_store_master_key_is_scanned(self) -> None:
        """It decrypts every other credential, so it is the highest-value single line."""
        assert detects(f"SKUEL_MASTER_KEY={base64url_secret()}")
        assert not detects("SKUEL_MASTER_KEY=${SKUEL_MASTER_KEY}")

    def test_the_deployed_service_credentials_are_scanned(self) -> None:
        """A compose interpolation replaced by a literal is the leak these cover."""
        assert detects(f"      MYSQL_PASSWORD: {base64url_secret()}")
        assert detects(f"      FIREFLY_III_ACCESS_TOKEN: {base64url_secret()}")
        assert detects(f"      - GF_SECURITY_ADMIN_PASSWORD={base64url_secret()}")
        # The interpolations they are today stay clean.
        assert not detects(
            "      MYSQL_PASSWORD: ${FIREFLY_DB_PASSWORD:-firefly-local-dev}",
            "      DB_PASSWORD: ${FIREFLY_DB_PASSWORD:-firefly-local-dev}",
            "      APP_KEY: ${FIREFLY_APP_KEY}              # MUST start with base64:",
            "      FIREFLY_III_ACCESS_TOKEN: ${FIREFLY_PAT_SKUEL:-}",
            "      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}",
            '      MYSQL_RANDOM_ROOT_PASSWORD: "yes"',
        )

    def test_the_signup_gate_is_scanned(self) -> None:
        """A leaked invite code opens registration — it is a secret, not config."""
        assert detects(f"SIGNUP_INVITE_CODE={base64url_secret()}")
        # `.env.example` carries it commented out; a comment is not an assignment.
        assert not detects("# SIGNUP_INVITE_CODE=choose-a-code")


class TestPatternFile:
    def test_every_line_is_label_pipe_regex(self) -> None:
        for entry in read_data_file(PATTERNS_FILE):
            label, sep, regex = entry.partition("|")
            assert sep, f"pattern line has no `label|regex` separator: {entry!r}"
            assert label.strip(), f"pattern line has an empty label: {entry!r}"
            assert regex.strip(), f"pattern line has an empty regex: {entry!r}"

    def test_no_regex_contains_an_unescaped_slash(self) -> None:
        """`/` is the sed s/// delimiter used to redact matches.

        A pattern containing one makes the redaction expression malformed, which
        the script handles by withholding the line entirely — the match is still
        blocked, but the author is told nothing useful about it.
        """
        for entry in read_data_file(PATTERNS_FILE):
            regex = entry.partition("|")[2]
            assert "/" not in regex.replace("\\/", ""), (
                f"pattern regex contains an unescaped `/`: {entry!r}"
            )


class TestBothHooksShareTheScan:
    """One pattern set, read by both hooks.

    A hook that grows its own copy makes one of the two fences the weaker, and the
    weakness is invisible until a key gets through the one nobody updated.
    """

    @pytest.mark.parametrize("hook", ["pre-commit", "pre-push"])
    def test_hook_delegates_to_the_shared_script(self, hook: str) -> None:
        source = (HOOK_DIR / hook).read_text()
        assert "secret-scan.sh" in source, f"{hook} no longer calls the shared scan"
        assert "patterns=(" not in source, (
            f"{hook} declares its own pattern array — both hooks must read "
            f"secret-patterns.txt, not re-implement it."
        )
