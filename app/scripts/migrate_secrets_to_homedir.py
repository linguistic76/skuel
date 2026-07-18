#!/usr/bin/env python3
"""
Migrate secrets out of the worktree (Stage 2).
==============================================

Splits ``app/.env`` into two files:

* ``~/.config/skuel/secrets.env`` (mode 0600) — credentials only.
  Lives outside any git worktree, so `git add . .env` cannot stage it.
* ``app/.env`` — keeps everything that *isn't* a credential
  (NEO4J_URI, APP_PORT, INTELLIGENCE_TIER, vault paths, etc.).
  Still gitignored; the secret-scan pre-commit hook remains as the seatbelt.

Both files are sourced by ``app/.envrc`` via direnv on `cd` into the project.

Idempotent
----------
Running twice is safe:
* If a key is in both ``.env`` and ``secrets.env``, the ``.env`` value wins
  (so re-adding a credential to ``.env`` "for testing" gets caught and moved).
* If a key is in neither, it's left alone — no placeholder rows added.
* Re-running after a clean migration is a no-op.

The script asks for confirmation before any destructive write. Pass
``--yes`` to skip prompts (for automation).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# Canonical inventory of secret keys. Anything not in this set is treated
# as non-secret config and stays in app/.env. Kept literal (not imported
# from credential_setup.CREDENTIALS) so the script runs without the package
# on the import path — uv may not be available at homedir-rewrite time.
SECRET_KEYS: frozenset[str] = frozenset(
    {
        # Database / infra
        "NEO4J_PASSWORD",
        "NEO4J_AUTH",  # "user/password" form — Docker reads this
        "NEO4J_OPENAI_API_KEY",  # legacy Neo4j GenAI plugin key
        # AI providers
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "HF_API_TOKEN",
        "DEEPGRAM_API_KEY",
        # Session signing
        "SESSION_SECRET_KEY",
        # Firefly III sidecar
        "FIREFLY_APP_KEY",
        "FIREFLY_DB_PASSWORD",
        "FIREFLY_PAT_PERSONAL",
        "FIREFLY_PAT_SKUEL",
        # Stripe webhook
        "STRIPE_WEBHOOK_SECRET",
        # Dev/test passwords (usernames + emails stay in .env)
        "TEST_ADMIN_PASSWORD",
        "TEST_USER_PASSWORD",
        # Meta — protects the encrypted credential_store.py JSON
        "SKUEL_MASTER_KEY",
    }
)

# Matches `KEY=` at start of line (allows leading spaces, no leading `#`).
# Captures the key in group 1 and the raw RHS (with any trailing comment) in
# group 2. We deliberately don't try to strip inline `# comment` because
# Docker Compose treats those as part of the value — and we'd corrupt it.
KV_LINE_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$")


def detect_paths() -> tuple[Path, Path, Path]:
    """Return (env_path, secrets_dir, secrets_path) with no I/O side effects."""
    # scripts/migrate_secrets_to_homedir.py → app/ → repo root
    repo_app = Path(__file__).resolve().parents[1]
    env_path = repo_app / ".env"
    secrets_dir = Path.home() / ".config" / "skuel"
    secrets_path = secrets_dir / "secrets.env"
    return env_path, secrets_dir, secrets_path


def _clean_value(raw: str) -> str:
    """Strip dotenv-style trailing `# comment` from an unquoted value.

    `.env.example` warns that Docker Compose treats `KEY=    # foo` as
    `KEY` having the literal value `# foo` — which is what bare line
    parsing would also give us. We're explicitly *not* preserving that
    quirk: lines like `FIREFLY_PAT_PERSONAL=    # placeholder` are
    obviously empty placeholders, and migrating them as-if their value
    were the comment string would carry garbage into secrets.env.

    Quoted values ("..." / '...') are returned as-is (no comment-strip),
    matching python-dotenv. We have no quoted values in scope today.
    """
    stripped = raw.strip()
    if not stripped:
        return ""
    if stripped[0] in ('"', "'"):
        return stripped  # quoted — preserve verbatim
    # Two spaces or a tab before `#` flags an inline comment. A single
    # space is too aggressive (could be inside a value).
    for sep in ("  #", "\t#"):
        idx = stripped.find(sep)
        if idx != -1:
            stripped = stripped[:idx].rstrip()
            break
    # Bare `# comment` lines wouldn't match KV_LINE_RE in the first place,
    # but a value that begins with `#` after RHS-trim is treated as comment.
    if stripped.startswith("#"):
        return ""
    return stripped


def parse_env_file(path: Path) -> tuple[list[str], dict[str, str]]:
    """Return (raw_lines, secret_values).

    raw_lines is every line in the file (preserved verbatim).
    secret_values is {KEY: cleaned_value} for every line whose key is in
    SECRET_KEYS and whose value is non-empty after inline-comment stripping.
    Last occurrence wins if the same key appears twice.
    """
    if not path.exists():
        return [], {}

    raw_lines = path.read_text().splitlines(keepends=True)
    secret_values: dict[str, str] = {}
    for line in raw_lines:
        m = KV_LINE_RE.match(line.rstrip("\n"))
        if not m:
            continue
        key, raw_rhs = m.group(1), m.group(2)
        value = _clean_value(raw_rhs)
        if key in SECRET_KEYS and value:  # skip empty placeholders
            secret_values[key] = value
    return raw_lines, secret_values


def parse_secrets_file(path: Path) -> dict[str, str]:
    """Load any existing secrets so we can merge without clobbering."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        m = KV_LINE_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2).rstrip()
    return out


def rewrite_env_without_secrets(raw_lines: list[str]) -> list[str]:
    """Drop secret-key lines from .env, leaving comments + non-secret keys."""
    kept: list[str] = []
    for line in raw_lines:
        m = KV_LINE_RE.match(line.rstrip("\n"))
        if m and m.group(1) in SECRET_KEYS:
            # Drop the line entirely. Leaving a breadcrumb comment in .env
            # would risk being committed; the source of truth is the plan +
            # the .env.example header.
            continue
        kept.append(line)
    # Collapse runs of >2 blank lines that the removals may have created.
    collapsed: list[str] = []
    blank_run = 0
    for line in kept:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                collapsed.append(line)
        else:
            blank_run = 0
            collapsed.append(line)
    return collapsed


def write_secrets_file(path: Path, secrets: dict[str, str]) -> None:
    """Write secrets.env with mode 0600. Atomic via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)

    header = (
        "# SKUEL secrets — managed by app/scripts/migrate_secrets_to_homedir.py.\n"
        "# Loaded by app/.envrc via direnv on `cd` into the project.\n"
        "# DO NOT commit. This file lives outside any git worktree by design.\n"
        "#\n"
        "# To rotate a value: edit here, then `direnv allow` in the project.\n"
        "# To add a new secret type: update SECRET_KEYS in the migration script.\n"
        "\n"
    )
    body = "\n".join(f"{k}={v}" for k, v in sorted(secrets.items())) + "\n"

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(header + body)
    tmp.chmod(0o600)
    tmp.replace(path)


def confirm(prompt: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer == "y"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompts")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing anything",
    )
    args = parser.parse_args()

    env_path, _secrets_dir, secrets_path = detect_paths()

    print(f"Source:  {env_path}")
    print(f"Target:  {secrets_path}")
    print()

    if not env_path.exists():
        print(f"⚠ {env_path} does not exist — nothing to migrate.")
        return 0

    raw_lines, from_env = parse_env_file(env_path)
    from_secrets = parse_secrets_file(secrets_path)

    # Merge: .env wins (it's the freshly-edited source). Existing secrets
    # in secrets.env are kept only if NOT also present in .env.
    merged: dict[str, str] = {**from_secrets, **from_env}

    if not merged:
        print("No secret-shaped keys found in .env. Nothing to do.")
        return 0

    already_there = sorted(set(from_secrets) - set(from_env))
    print(f"Found {len(from_env)} secret keys in {env_path.name}:")
    for k in sorted(from_env):
        print(f"  • {k}")
    if already_there:
        print(f"\nAlready in {secrets_path.name} and not in {env_path.name}:")
        for k in already_there:
            print(f"  • {k}")
    print()

    if args.dry_run:
        print("--dry-run set; no changes written.")
        return 0

    if not confirm(
        f"Move these secrets to {secrets_path} and rewrite {env_path}?",
        assume_yes=args.yes,
    ):
        print("Aborted.")
        return 1

    # Back up .env before rewriting — cheap insurance.
    backup = env_path.with_suffix(env_path.suffix + ".bak")
    shutil.copy2(env_path, backup)
    print(f"✓ Backed up to {backup}")

    write_secrets_file(secrets_path, merged)
    secrets_path.chmod(0o600)
    print(f"✓ Wrote {len(merged)} secrets to {secrets_path} (mode 0600)")

    new_env = rewrite_env_without_secrets(raw_lines)
    env_path.write_text("".join(new_env))
    print(f"✓ Rewrote {env_path} without secret lines")

    print()
    print("Next steps:")
    print("  1. Run:  direnv allow")
    print("     (in the app/ directory)")
    print("  2. Verify:  env | grep -E 'NEO4J_PASSWORD|SESSION_SECRET_KEY'")
    print("     after `cd app/` should print the values")
    print("  3. Delete the backup once you're satisfied the migration worked:")
    print(f"     rm {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
