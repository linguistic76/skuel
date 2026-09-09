#!/usr/bin/env python3
"""
Migrate secrets into the OS keychain.
======================================

Sources, in order of increasing precedence. Every one is filtered to
``CREDENTIAL_CATALOG`` names, because connection config must never reach the
keychain — a keychain that answers ``NEO4J_URI`` is a second source of truth for
where the database lives, and it goes stale the day the database moves.

* ``~/.config/skuel/secrets.env`` — the dedicated secrets file. It also carries
  ``NEO4J_AUTH`` for Docker Compose ``${VAR}`` interpolation; that name is not a
  catalog credential and nothing reads it through the funnel, so the filter is
  what keeps a re-run from adding it to the keychain inventory.
* ``app/.env`` — the migration path for a legacy ``.env`` that still carries
  credentials, and mostly non-secret config besides; the file is READ only,
  never rewritten or deleted, since the config in it is still live.
* the current shell environment, when neither file exists.

After this script runs:

* Every credential found lives in the OS keychain (libsecret on Linux, Keychain
  on macOS, Credential Locker on Windows) under service ``skuel``.
* ``~/.config/skuel/secrets.env`` is deleted (with explicit confirmation),
  removing the last plaintext copy on disk — unless the catalog filter refused
  something in it, in which case the file is that value's only copy and is kept.
* ``SKUEL_CREDENTIAL_BACKEND=keyring`` needs to be set in your environment
  for the app to actually use the keychain. The migration script will offer
  to add it to ``app/.env`` (where direnv loads it from).

Idempotent: running twice is safe. Secrets already in the keychain are
left untouched; any that have been re-added to ``secrets.env`` since the
last run are picked up.

Caveats this script will print (worth re-reading before you delete the file):

1. Docker Compose reads ``.env`` directly for variable interpolation.
   With secrets in the keychain instead of ``.env``, any Compose service
   referencing ``${NEO4J_PASSWORD}`` (etc.) will fail unless you pre-export
   the value from the keychain into the shell before running ``docker
   compose up``.

2. CI / cron / any non-interactive shell that never touched direnv won't
   see the keychain either — it requires an unlocked desktop session.

3. The keychain is unlocked when you log into your desktop. Service tools
   (``secret-tool``, ``seahorse``) can inspect and rotate values without
   touching this script.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config.credential_store import CREDENTIAL_CATALOG, _is_placeholder

SERVICE_NAME = "skuel"

# `KEY=  # note` — an assignment whose UNQUOTED value is a comment. dotenv
# returns the comment text as the value, and Docker Compose reads it the same
# way; neither is a credential. Matched on the raw line rather than the decoded
# value because `KEY="#secret"` decodes to `#secret` too, and that one IS a
# credential — the quote is the only thing that tells them apart.
_COMMENTED_OUT_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*#", re.MULTILINE)


def detect_paths() -> tuple[Path, Path]:
    """Return (secrets_path, app_env_path)."""
    repo_app = Path(__file__).resolve().parents[1]
    return Path.home() / ".config" / "skuel" / "secrets.env", repo_app / ".env"


def _parse_env_shaped_file(path: Path) -> dict[str, str]:
    """Load usable KV pairs from a `.env`-shaped file, before the catalog gate.

    Private because an unfiltered read is never what a caller wants — go through
    `parse_credentials`.

    Parsed with `python-dotenv`, which is what these files are read by at
    runtime (`load_dotenv`, and direnv's `dotenv_if_exists` in `app/.envrc`) —
    so a quoted value (`NEO4J_PASSWORD="..."`) reaches the keychain as the
    string the app would have seen, not with its quotes attached. Interpolation
    is off: a credential containing `$` must survive verbatim.

    Two shapes are dropped as non-values:

    * a commented-out blank — `KEY=  # note`, decided on the raw line so that a
      quoted `KEY="#secret"` (a real credential that happens to start with `#`)
      is kept. Dropping it silently would lose a credential from a migration
      that then offers to delete the plaintext original.
    * a placeholder, by `_is_placeholder` — the credential funnel's own rule, so
      a half-filled template never reaches the keychain. Without this, a `.env`
      copied from `.env.example` migrates `your-neo4j-password` over a valid
      stored credential and the plaintext original is then offered for deletion.
    """
    if not path.exists():
        return {}
    text = path.read_text()
    commented_out = {m.group(1) for m in _COMMENTED_OUT_RE.finditer(text)}
    return {
        key: raw
        for key, raw in dotenv_values(path, interpolate=False).items()
        if raw is not None and key not in commented_out and not _is_placeholder(raw)
    }


def parse_credentials(path: Path) -> dict[str, str]:
    """Load only CREDENTIAL_CATALOG names from a `.env`-shaped file.

    The catalog is the same gate `get_credential()` applies before it writes an
    env-supplied value into the keychain (`credential_store.py`, auto-migration).
    This script writes to the keychain directly, so without the filter here the
    two paths disagree about what a credential is: `secrets.env` holds
    `NEO4J_AUTH` for Docker Compose, the funnel refuses that name, and a re-run
    of this script would store it anyway.
    """
    return {k: v for k, v in _parse_env_shaped_file(path).items() if k in CREDENTIAL_CATALOG}


def unmigrated_names(path: Path, migrated: dict[str, str]) -> list[str]:
    """Names `path` holds that the catalog filter did not migrate.

    The catalog gate and the offer to delete the source are two halves of one
    decision: whatever the gate refuses stays in the file, and the file is then
    that value's only copy. `secrets.env` holds `NEO4J_AUTH` for the
    `${NEO4J_AUTH}` interpolation in `infrastructure/docker-compose.yml`, which
    `scripts/dev/with-secrets` cannot supply — it exports the keyring index, and
    an uncatalogued name is never in it.
    """
    return sorted(set(_parse_env_shaped_file(path)) - set(migrated))


def confirm(prompt: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer == "y"


def ensure_backend_env_var(app_env_path: Path, *, assume_yes: bool) -> None:
    """Point ``SKUEL_CREDENTIAL_BACKEND`` at the keychain we just populated.

    The variable is non-secret (it just selects which backend to use), so it
    belongs in the in-repo .env, not the homedir secrets file. We append rather
    than overwrite to preserve any existing config.

    An existing assignment is checked, not merely detected: `env` is a valid
    value now, and leaving it in place after a keychain migration means the app
    keeps reading the process environment — so once `secrets.env` is deleted,
    a fresh shell has no credentials at all.
    """
    if not app_env_path.exists():
        print(
            f"⚠ {app_env_path} doesn't exist — please set SKUEL_CREDENTIAL_BACKEND=keyring manually."
        )
        return

    content = app_env_path.read_text()
    existing = re.search(
        r"^(\s*(?:export\s+)?SKUEL_CREDENTIAL_BACKEND\s*=\s*)(\S*)", content, re.MULTILINE
    )
    if existing:
        current = existing.group(2).strip().strip("\"'").lower()
        if current == "keyring":
            print(f"✓ {app_env_path.name} already selects the keychain; leaving it alone.")
            return
        print(
            f"⚠ {app_env_path.name} sets SKUEL_CREDENTIAL_BACKEND={current or '(empty)'}, "
            f"so the app would not read the keychain you just populated."
        )
        if not confirm(
            f"Change it to keyring in {app_env_path}?",
            assume_yes=assume_yes,
        ):
            print("⚠ Skipped. The credentials are in the keychain but the app will not read them.")
            return
        start, end = existing.span()
        app_env_path.write_text(content[:start] + existing.group(1) + "keyring" + content[end:])
        print(f"✓ Set SKUEL_CREDENTIAL_BACKEND=keyring in {app_env_path}")
        return

    if not confirm(
        f"Append SKUEL_CREDENTIAL_BACKEND=keyring to {app_env_path}?",
        assume_yes=assume_yes,
    ):
        print("⚠ Skipped. Set SKUEL_CREDENTIAL_BACKEND=keyring yourself before starting the app.")
        return

    suffix = "" if content.endswith("\n") else "\n"
    addition = (
        "\n# Route credential reads through the OS keychain (the default).\n"
        "# The only other value is `env` — the read-only process environment,\n"
        "# for headless boxes with no keychain daemon.\n"
        "SKUEL_CREDENTIAL_BACKEND=keyring\n"
    )
    app_env_path.write_text(content + suffix + addition)
    print(f"✓ Appended SKUEL_CREDENTIAL_BACKEND=keyring to {app_env_path}")


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
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="Don't delete ~/.config/skuel/secrets.env after migration (useful for testing)",
    )
    args = parser.parse_args()

    secrets_path, app_env_path = detect_paths()

    # Import keyring lazily so --help works without the dependency.
    try:
        import keyring as _keyring
    except ImportError:
        print("✗ The 'keyring' package isn't installed. Run: uv add keyring")
        return 1

    backend = _keyring.get_keyring()
    print(f"Backend:  {type(backend).__module__}.{type(backend).__name__}")
    print(f"Service:  {SERVICE_NAME}")

    # `app/.env` wins over `secrets.env`: a credential sitting in the worktree
    # is the one that most needs moving, and the diff below shows every
    # overwrite before anything is written.
    from_secrets = parse_credentials(secrets_path) if secrets_path.exists() else {}
    from_env_file = parse_credentials(app_env_path) if app_env_path.exists() else {}
    secrets = {**from_secrets, **from_env_file}
    if from_secrets:
        print(f"Source:   {secrets_path} ({len(from_secrets)}, catalog names only)")
    if from_env_file:
        print(f"Source:   {app_env_path} ({len(from_env_file)}, catalog names only)")

    if not secrets:
        # Fall back to the current shell env — useful when direnv already
        # loaded the values but the source files are gone.
        secrets = {
            k: v for k in CREDENTIAL_CATALOG if (v := os.getenv(k)) and not _is_placeholder(v)
        }
        if not secrets:
            print("\nNo credentials found in either file or the shell environment.")
            print("Nothing to migrate.")
            return 0
        print(f"Source:   shell environment ({len(secrets)}, catalog names only)")

    print()

    # Diff against what's already in the keychain so the user sees what
    # actually changes.
    new_keys: list[str] = []
    overwrite_keys: list[str] = []
    already_correct: list[str] = []
    for key, value in sorted(secrets.items()):
        try:
            existing = _keyring.get_password(SERVICE_NAME, key)
        except Exception as e:
            print(f"✗ Couldn't query keychain for {key}: {e}")
            return 1
        if existing is None:
            new_keys.append(key)
        elif existing == value:
            already_correct.append(key)
        else:
            overwrite_keys.append(key)

    if new_keys:
        print(f"Will WRITE {len(new_keys)} new credential(s) to keychain:")
        for k in new_keys:
            print(f"  + {k}")
    if overwrite_keys:
        print(f"Will OVERWRITE {len(overwrite_keys)} credential(s) (value differs):")
        for k in overwrite_keys:
            print(f"  ~ {k}")
    if already_correct:
        print(f"Already up-to-date in keychain ({len(already_correct)}):")
        for k in already_correct:
            print(f"  = {k}")
    print()

    if args.dry_run:
        print("--dry-run set; no changes written.")
        return 0

    if not (new_keys or overwrite_keys):
        print("Keychain is already in sync — nothing to write.")
    else:
        if not confirm(
            "Proceed with writing credentials to the OS keychain?",
            assume_yes=args.yes,
        ):
            print("Aborted.")
            return 1
        for key in new_keys + overwrite_keys:
            _keyring.set_password(SERVICE_NAME, key, secrets[key])
            print(f"✓ Stored {key}")

    # Refresh the keyring-index.json that KeyringBackend maintains so the
    # interactive credential_setup.py can show what's stored.
    index_path = secrets_path.parent / "keyring-index.json"
    # Migrating straight from `app/.env` never touches ~/.config/skuel, and
    # KeyringBackend (which creates it) is never instantiated here.
    index_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    import json

    existing_index: list[str] = []
    if index_path.exists():
        try:
            existing_index = list(json.loads(index_path.read_text()))
        except OSError, json.JSONDecodeError:
            existing_index = []
    merged_index = sorted(set(existing_index) | set(secrets.keys()))
    index_path.write_text(json.dumps(merged_index, indent=2))
    index_path.chmod(0o600)
    print(f"✓ Updated index at {index_path}")

    # Make sure the app knows to use the keychain backend.
    ensure_backend_env_var(app_env_path, assume_yes=args.yes)

    # Finally — offer to remove the plaintext source file.
    if args.keep_source:
        print(f"\nKeeping {secrets_path} intact (--keep-source).")
    elif secrets_path.exists() and (residue := unmigrated_names(secrets_path, from_secrets)):
        print(
            f"\nKeeping {secrets_path} — it still holds {', '.join(residue)}, which "
            f"{'is' if len(residue) == 1 else 'are'} not a catalog credential and so "
            f"{'was' if len(residue) == 1 else 'were'} not migrated. This file is the "
            f"only copy; Docker Compose interpolates from it directly."
        )
    elif secrets_path.exists():
        if confirm(
            f"\nDelete {secrets_path} now? It contains the credentials you just migrated.",
            assume_yes=args.yes,
        ):
            # Best-effort: overwrite with zeros before unlink so the disk
            # blocks don't trivially carry the credential bytes forward.
            try:
                size = secrets_path.stat().st_size
                with secrets_path.open("r+b") as f:
                    f.write(b"\x00" * size)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                print(f"  (couldn't zero file before unlink: {e})")
            backup = secrets_path.with_suffix(secrets_path.suffix + ".bak")
            shutil.move(str(secrets_path), str(backup))
            print(f"✓ Moved to {backup} (still plaintext — `shred -u` it once verified).")
        else:
            print(f"  Kept {secrets_path}. Delete it manually when ready.")

    print()
    print("Verification:")
    print("  python -c \"import keyring; print(keyring.get_password('skuel', 'NEO4J_PASSWORD'))\"")
    print("    (should print the password if migrated)")
    print()
    print("Caveats:")
    print("  • Docker Compose reads .env directly. Anything referencing")
    print("    ${NEO4J_PASSWORD} etc. in Compose will need an explicit")
    print(
        "    pre-export from the keychain — see app/docs/roadmap/done/secrets-out-of-worktree.md."
    )
    print("  • The keychain is unlocked when your desktop session is unlocked.")
    print("    Headless / CI / cron environments do not get keychain access.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
