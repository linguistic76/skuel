#!/usr/bin/env python3
# skuel-lint: disable-file=SKUEL015 -- Interactive CLI utility
"""
Credential Setup Tool
=====================

Interactive tool to load SKUEL's credentials into the active backend
(`uv run python -m core.config`). It writes through ``get_active_backend()``,
so what it stores is exactly what ``get_credential()`` later reads — there is
no second write path.

The catalog it walks is ``CREDENTIAL_CATALOG`` in ``credential_store.py``.
"""

__version__ = "2.0"

import getpass
import os
import sys

# Load environment variables from .env file if it exists
from dotenv import load_dotenv

from core.config.credential_store import (
    CREDENTIAL_CATALOG,
    CredentialBackend,
    CredentialSpec,
    _is_placeholder,
    get_active_backend,
)
from core.errors import ConfigurationError
from core.utils.logging import get_logger

load_dotenv()

logger = get_logger(__name__)


def _env_value(name: str) -> str | None:
    """The environment's value for `name`, or None when it is a placeholder.

    Uses the same placeholder rule as `get_credential()`'s auto-migration, so a
    half-filled `.env` template never lands in the backend either way.
    """
    value = os.getenv(name)
    return None if _is_placeholder(value) else value


class CredentialSetup:
    """Interactive credential setup utility."""

    def __init__(self) -> None:
        """Initialize the credential setup against the active backend."""
        self.backend: CredentialBackend = get_active_backend()

    def run(self) -> None:
        """Run the interactive credential setup."""
        print("\n" + "=" * 60)
        print("SKUEL Credential Setup")
        print("=" * 60)

        backend_name = type(self.backend).__name__
        if self.backend.READ_ONLY:
            print(f"\n❌ The active backend ({backend_name}) is read-only.")
            print("\nSKUEL_CREDENTIAL_BACKEND=env resolves credentials from the process")
            print("environment — this tool has nothing to write to. Set the values in")
            print("whatever loads that environment (on the droplet: /opt/skuel/secrets.env,")
            print("loaded by docker-compose.production.yml), or switch to")
            print("SKUEL_CREDENTIAL_BACKEND=keyring on a machine with a keychain.")
            return

        print(f"\nCredentials are stored via {backend_name} — never in plain text.\n")

        while True:
            self._show_menu()
            choice = input("\nChoice: ").strip()

            if choice == "1":
                self._setup_all_credentials()
            elif choice == "2":
                self._setup_single_credential()
            elif choice == "3":
                self._view_credentials()
            elif choice == "4":
                self._migrate_from_env()
            elif choice == "5":
                self._test_credentials()
            elif choice == "6":
                self._remove_credential()
            elif choice == "0":
                print("\n✅ Credential setup complete!")
                break
            else:
                print("\n❌ Invalid choice")

    def _show_menu(self) -> None:
        """Show the main menu."""
        print("\n" + "-" * 40)
        print("Options:")
        print("  1. Set up all credentials")
        print("  2. Set up single credential")
        print("  3. View stored credentials")
        print("  4. Migrate from environment/file")
        print("  5. Test credentials")
        print("  6. Remove credential")
        print("  0. Exit")

    def _setup_all_credentials(self) -> None:
        """Set up all credentials interactively."""
        print("\n📝 Setting up all credentials...\n")

        for cred_name, spec in CREDENTIAL_CATALOG.items():
            if self.backend.exists(cred_name):
                update = input(f"{cred_name} already set. Update? [y/N]: ").strip().lower()
                if update != "y":
                    continue

            self._setup_credential(cred_name, spec)

    def _setup_single_credential(self) -> None:
        """Set up a single credential."""
        print("\nAvailable credentials:")
        for i, (name, spec) in enumerate(CREDENTIAL_CATALOG.items(), 1):
            required = "Required" if spec.required else "Optional"
            print(f"  {i}. {name} - {spec.description} [{required}]")

        choice = input(f"\nSelect credential [1-{len(CREDENTIAL_CATALOG)}]: ").strip()

        try:
            idx = int(choice) - 1
            if idx < 0:
                raise IndexError(choice)
            cred_name = list(CREDENTIAL_CATALOG)[idx]
        except (ValueError, IndexError):  # fmt: skip
            print("❌ Invalid choice")
            return

        self._setup_credential(cred_name, CREDENTIAL_CATALOG[cred_name])

    def _setup_credential(self, name: str, spec: CredentialSpec) -> None:
        """Prompt for one credential and store it."""
        print(f"\n{spec.description}:")

        value = getpass.getpass(f"Enter {name}: ").strip()
        if value:
            confirm = getpass.getpass(f"Confirm {name}: ").strip()
            if value != confirm:
                print("❌ Values don't match!")
                return

        if not value:
            if spec.required:
                print(f"❌ {name} is required!")
            else:
                print(f"⏭️  Skipping {name}")
            return

        if spec.expected_prefix and not value.startswith(spec.expected_prefix):
            # Advisory only — storing anyway. See CredentialSpec.expected_prefix.
            print(f"⚠️  Warning: {name} values usually start with '{spec.expected_prefix}'")

        self.backend.set(name, value)
        print(f"✅ {name} stored securely")

    def _view_credentials(self) -> None:
        """View stored credentials (keys only, not values)."""
        print("\n📋 Stored credentials:")
        keys = self.backend.list_keys()

        if not keys:
            print("  No credentials stored")
            return

        for key in keys:
            spec = CREDENTIAL_CATALOG.get(key)
            description = spec.description if spec else "Not in the credential catalog"
            print(f"  • {key}: {description}")

    def _migrate_from_env(self) -> None:
        """Migrate catalog credentials from environment variables."""
        print("\n🔄 Migrating from environment variables...\n")

        migrated = []
        for cred_name in CREDENTIAL_CATALOG:
            env_value = _env_value(cred_name)
            if not env_value:
                continue

            if self.backend.exists(cred_name):
                print(f"  ⏭️  {cred_name} already stored, skipping")
                continue

            self.backend.set(cred_name, env_value)
            migrated.append(cred_name)
            print(f"  ✅ Migrated {cred_name}")

        if migrated:
            print(f"\n✅ Migrated {len(migrated)} credential(s)")
            print("\n⚠️  You can now remove these from your .env file:")
            for name in migrated:
                print(f"  - {name}")
        else:
            print("\n  No credentials to migrate")

    def _test_credentials(self) -> None:
        """Report which catalog credentials are present."""
        print("\n🧪 Testing credentials...\n")

        for name, spec in CREDENTIAL_CATALOG.items():
            requirement = "REQUIRED" if spec.required else "optional"
            if self.backend.exists(name):
                print(f"  • {name}: ✅ Set ({requirement})")
            elif spec.required:
                print(f"  • {name}: ❌ Not set ({requirement})")
            else:
                print(f"  • {name}: ⚠️  Not set ({requirement})")

    def _remove_credential(self) -> None:
        """Remove a credential from the backend."""
        keys = self.backend.list_keys()

        if not keys:
            print("\n  No credentials to remove")
            return

        print("\nStored credentials:")
        for i, key in enumerate(keys, 1):
            print(f"  {i}. {key}")

        choice = input(f"\nSelect credential to remove [1-{len(keys)}]: ").strip()

        try:
            idx = int(choice) - 1
            if idx < 0:
                raise IndexError(choice)
            key_to_remove = keys[idx]
        except (ValueError, IndexError):  # fmt: skip
            print("❌ Invalid choice")
            return

        confirm = (
            input(f"\n⚠️  Remove {key_to_remove}? This cannot be undone. [y/N]: ").strip().lower()
        )
        if confirm == "y":
            self.backend.delete(key_to_remove)
            print(f"✅ {key_to_remove} removed")


def main() -> None:
    """Main entry point for credential setup."""
    try:
        setup = CredentialSetup()
        setup.run()
    except KeyboardInterrupt, EOFError:
        print("\n\n👋 Credential setup cancelled")
        sys.exit(0)
    except ConfigurationError as e:
        print(f"\n❌ {e}")
        sys.exit(1)
    except Exception as e:  # intentional-broad: CLI entrypoint
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
