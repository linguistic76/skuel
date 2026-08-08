#!/usr/bin/env python3
"""
Migrate secrets from ~/.config/skuel/secrets.env into the OS keychain (Stage 3).
================================================================================

After this script runs:

* Every credential currently in ``~/.config/skuel/secrets.env`` lives in the
  OS keychain (libsecret on Linux, Keychain on macOS, Credential Locker on
  Windows) under service ``skuel``.
* ``~/.config/skuel/secrets.env`` is deleted (with explicit confirmation),
  removing the last plaintext copy on disk.
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

# Same KV regex shape as the Stage 2 migration — kept literal so the script
# runs without an import dependency on the package.
KV_LINE_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$")

SERVICE_NAME = "skuel"


def detect_paths() -> tuple[Path, Path]:
    """Return (secrets_path, app_env_path)."""
    repo_app = Path(__file__).resolve().parents[1]
    return Path.home() / ".config" / "skuel" / "secrets.env", repo_app / ".env"


def parse_secrets_file(path: Path) -> dict[str, str]:
    """Load KV pairs from secrets.env (or any .env-shaped file)."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        m = KV_LINE_RE.match(line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        # Strip dotenv-style trailing `# comment` for unquoted values.
        # Matches the Docker-Compose-quirk handling in Stage 2's migration.
        if raw and raw[0] not in ('"', "'"):
            for sep in ("  #", "\t#"):
                idx = raw.find(sep)
                if idx != -1:
                    raw = raw[:idx].rstrip()
                    break
            if raw.startswith("#"):
                raw = ""
        if raw:
            out[key] = raw
    return out


def confirm(prompt: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer == "y"


def ensure_backend_env_var(app_env_path: Path, *, assume_yes: bool) -> None:
    """Add ``SKUEL_CREDENTIAL_BACKEND=keyring`` to app/.env if missing.

    The variable is non-secret (it just selects which backend to use), so it
    belongs in the in-repo .env, not the homedir secrets file. We append
    rather than overwrite to preserve any existing config.
    """
    if not app_env_path.exists():
        print(
            f"⚠ {app_env_path} doesn't exist — please set SKUEL_CREDENTIAL_BACKEND=keyring manually."
        )
        return

    content = app_env_path.read_text()
    if re.search(r"^\s*SKUEL_CREDENTIAL_BACKEND\s*=", content, re.MULTILINE):
        print(f"✓ {app_env_path.name} already has SKUEL_CREDENTIAL_BACKEND set; leaving it alone.")
        return

    if not confirm(
        f"Append SKUEL_CREDENTIAL_BACKEND=keyring to {app_env_path}?",
        assume_yes=assume_yes,
    ):
        print("⚠ Skipped. Set SKUEL_CREDENTIAL_BACKEND=keyring yourself before starting the app.")
        return

    suffix = "" if content.endswith("\n") else "\n"
    addition = (
        "\n# Stage 3: route credential reads through the OS keychain.\n"
        "# Unset to fall back to the Fernet-encrypted JSON store (~/.skuel/credentials.enc).\n"
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
    print(f"Source:   {secrets_path}")
    print(f"Backend:  {type(backend).__module__}.{type(backend).__name__}")
    print(f"Service:  {SERVICE_NAME}")
    print()

    if not secrets_path.exists():
        # Fall back to current shell env — useful if direnv already loaded
        # secrets.env but the user has since deleted the source file.
        from_env_only = {
            k: v
            for k, v in os.environ.items()
            if k.endswith(("_PASSWORD", "_KEY", "_TOKEN", "_SECRET", "_PAT", "_AUTH"))
            and not k.startswith(("SKUEL_", "FIREFLY_TIMEOUT_"))
        }
        if not from_env_only:
            print(f"⚠ {secrets_path} doesn't exist and no credential-shaped env vars found.")
            print("  Nothing to migrate.")
            return 0
        print(f"⚠ {secrets_path} doesn't exist; falling back to current shell env.")
        secrets = from_env_only
    else:
        secrets = parse_secrets_file(secrets_path)

    if not secrets:
        print("No secrets to migrate.")
        return 0

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
    print("    pre-export from the keychain — see app/docs/roadmap/done/secrets-out-of-worktree.md.")
    print("  • The keychain is unlocked when your desktop session is unlocked.")
    print("    Headless / CI / cron environments do not get keychain access.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
