"""Pin ``scripts/git-hooks/secret-scan.sh`` — the commit- and push-time secret fence.

Why this file exists
--------------------
The scan had no test at all, and a measurement of its own pattern array against
six synthetic key shapes found it caught **one**:

===========================================  ==============
shape                                         before
===========================================  ==============
``sk-proj-…`` (OpenAI project key)            detected
``sk-ant-api03-…`` (Anthropic)                NOT detected
``sk-<48>`` (legacy OpenAI)                   NOT detected
Deepgram 40-hex                               NOT detected
AuraDB password (43-char base64url)           NOT detected
``SESSION_SECRET_KEY`` (43-char base64url)    NOT detected
===========================================  ==============

The last three rows are the reason the scan grew a second half. They are
prefix-free high-entropy strings: a *content* regex that matched them would also
match every hash, UUID and lockfile digest in the tree. So they are caught by
*assignment shape* — a name from the credential catalog given a non-placeholder
value — and the value's appearance is never consulted.

Every key below is generated from ``secrets`` (i.e. ``/dev/urandom``) at run
time. No real key, and no value that could be mistaken for one, appears in this
file or in its failure output.

The negatives matter as much as the positives: a scan that blocks ``.env.example``
gets bypassed with ``SKUEL_ALLOW_SECRETS=1`` until it stops being a fence at all.
So the false-positive floor is asserted against the *live* ``.env.example`` and
``.env.production.example`` rather than a copied excerpt — a placeholder added
there later is covered without touching this file.
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
class TestMeasuredGaps:
    """The six shapes probed against the old pattern array. Five used to slip."""

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

    def test_openai_project_key_still_detected(self) -> None:
        """The one shape that already worked — a regression here is a loss."""
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

    def test_a_non_catalog_name_is_not_flagged(self) -> None:
        # `SIGNUP_INVITE_CODE` and friends are config, not credentials.
        assert not detects(f"SIGNUP_INVITE_CODE={alnum(40)}")

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
class TestCatalogDrift:
    """`credential-keys.txt` is a mirror of CredentialSetup.CREDENTIALS.

    Bash cannot import Python, so the names are duplicated. This is the same
    arrangement (and the same failure mode) as
    `scripts/lint_skuel.py::SkuelLinter.CREDENTIAL_CATALOG`: if the mirror drifts,
    a newly-added credential silently stops being scanned for.
    """

    def test_mirror_matches_credential_setup(self) -> None:
        from core.config.credential_setup import CredentialSetup

        actual = set(CredentialSetup.CREDENTIALS)
        mirrored = set(read_data_file(CATALOG_FILE))

        missing = actual - mirrored
        extra = mirrored - actual
        assert not missing, (
            f"scripts/git-hooks/credential-keys.txt is missing keys present in "
            f"CredentialSetup.CREDENTIALS: {sorted(missing)}. Add them — until then "
            f"the secret scan does not look for them."
        )
        assert not extra, (
            f"scripts/git-hooks/credential-keys.txt has keys not in "
            f"CredentialSetup.CREDENTIALS: {sorted(extra)}."
        )


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
    """pre-commit and pre-push used to carry hand-synced copies of the array.

    The README asked humans to keep them equal; a drift there silently made the
    push-time fence the weaker of the two. Neither may grow its own copy again.
    """

    @pytest.mark.parametrize("hook", ["pre-commit", "pre-push"])
    def test_hook_delegates_to_the_shared_script(self, hook: str) -> None:
        source = (HOOK_DIR / hook).read_text()
        assert "secret-scan.sh" in source, f"{hook} no longer calls the shared scan"
        assert "patterns=(" not in source, (
            f"{hook} declares its own pattern array again — the two hooks must share "
            f"secret-patterns.txt, not re-implement it."
        )
