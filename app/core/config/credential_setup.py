#!/usr/bin/env python3
"""
Credential Setup Tool
=====================

Interactive tool to set up and manage encrypted credentials for SKUEL.
All sensitive data is stored encrypted, never in plain text.
"""

__version__ = "1.0"

import getpass
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

# Load environment variables from .env file if it exists
from dotenv import load_dotenv

from core.config.credential_store import CredentialStore, get_credential_store
from core.utils.logging import get_logger

load_dotenv()

logger = get_logger(__name__)


def _validate_openai_key(key: str) -> bool:
    """Validate OpenAI API key format."""
    if not key.startswith("sk-"):
        print("⚠️  Warning: OpenAI keys usually start with 'sk-'")
        return False
    return True


class CredentialSetup:
    """Interactive credential setup utility."""

    # Credentials to manage
    CREDENTIALS: ClassVar[dict[str, dict[str, Any | bool | None | Callable[[str], bool]]]] = {
        "NEO4J_PASSWORD": {
            "description": "Neo4j database password",
            "required": False,
            "sensitive": True,
            "default": None,
        },
        "OPENAI_API_KEY": {
            "description": "OpenAI API key for embeddings and AI features",
            "required": True,
            "sensitive": True,
            "default": None,
            "validation": _validate_openai_key,
        },
        "DEEPGRAM_API_KEY": {
            "description": "Deepgram API key for audio transcription",
            "required": False,
            "sensitive": True,
            "default": None,
        },
    }

    def __init__(self) -> None:
        """Initialize the credential setup."""
        self.store: CredentialStore | None = None
        self._check_master_key()

    def _check_master_key(self) -> bool:
        """Check if master key is set up."""
        if not os.getenv("SKUEL_MASTER_KEY"):
            print("\n⚠️  SKUEL_MASTER_KEY not found!")
            print("\nThe master key is required to encrypt credentials.")
            print("Options:")
            print("  1. Generate a new master key")
            print("  2. Use existing master key from .env")
            print("  3. Exit")

            choice = input("\nChoice [1-3]: ").strip()

            if choice == "1":
                self._generate_master_key()
                return True
            elif choice == "2":
                print("\nPlease ensure SKUEL_MASTER_KEY is set in your .env file")
                return False
            else:
                sys.exit(0)
        return True

    def _generate_master_key(self) -> None:
        """Generate and display a new master key."""
        import base64
        import secrets

        key = base64.b64encode(secrets.token_bytes(32)).decode()

        print("\n🔑 Generated master key:")
        print(f"\nSKUEL_MASTER_KEY={key}")
        print("\n⚠️  IMPORTANT:")
        print("  1. Add this to your .env file")
        print("  2. Keep this key safe - it's needed to decrypt credentials")
        print("  3. Never commit this key to version control")

        save = input("\nSave to .env file? [y/N]: ").strip().lower()
        if save == "y":
            self._update_env_file("SKUEL_MASTER_KEY", key)
            os.environ["SKUEL_MASTER_KEY"] = key
            print("✅ Master key saved to .env")

    def _update_env_file(self, key: str, value: str) -> None:
        """Update or add a key in .env file."""
        env_path = Path.cwd() / ".env"

        if env_path.exists():
            lines = env_path.read_text().splitlines()
            updated = False

            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    updated = True
                    break

            if not updated:
                lines.append("\n# Added by credential setup")
                lines.append(f"{key}={value}")

            env_path.write_text("\n".join(lines) + "\n")
        else:
            env_path.write_text(f"# SKUEL Environment Configuration\n{key}={value}\n")

    def run(self):
        """Run the interactive credential setup."""
        print("\n" + "=" * 60)
        print("SKUEL Encrypted Credential Setup")
        print("=" * 60)

        if not self._check_master_key():
            return

        try:
            self.store = get_credential_store()
        except ValueError as e:
            print(f"\n❌ Error: {e}")
            return

        print("\nThis tool will help you securely store sensitive credentials.")
        print("All credentials are encrypted using your master key.\n")

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
        if self.store is None:
            print("❌ Credential store not initialized")
            return

        print("\n📝 Setting up all credentials...\n")

        for cred_name, config in self.CREDENTIALS.items():
            current = self.store.get(cred_name)

            if current:
                update = input(f"{cred_name} already set. Update? [y/N]: ").strip().lower()
                if update != "y":
                    continue

            self._setup_credential(cred_name, config)

    def _setup_single_credential(self) -> None:
        """Set up a single credential."""
        print("\nAvailable credentials:")
        for i, (name, config) in enumerate(self.CREDENTIALS.items(), 1):
            required = "Required" if config["required"] else "Optional"
            print(f"  {i}. {name} - {config['description']} [{required}]")

        choice = input(f"\nSelect credential [1-{len(self.CREDENTIALS)}]: ").strip()

        try:
            idx = int(choice) - 1
            cred_name = list(self.CREDENTIALS.keys())[idx]
            self._setup_credential(cred_name, self.CREDENTIALS[cred_name])
        except (ValueError, IndexError):
            print("❌ Invalid choice")

    def _setup_credential(self, name: str, config: dict) -> None:
        """Set up a single credential."""
        if self.store is None:
            print("❌ Credential store not initialized")
            return

        print(f"\n{config['description']}:")

        if config["sensitive"]:
            value = getpass.getpass(f"Enter {name}: ").strip()
            if value:
                confirm = getpass.getpass(f"Confirm {name}: ").strip()
                if value != confirm:
                    print("❌ Values don't match!")
                    return
        else:
            value = input(f"Enter {name}: ").strip()

        if not value:
            if config["required"]:
                print(f"❌ {name} is required!")
                return
            else:
                print(f"⏭️  Skipping {name}")
                return

        # Validate if validator exists
        if config.get("validation"):
            config["validation"](value)

        self.store.set(name, value)
        print(f"✅ {name} stored securely")

    def _view_credentials(self) -> None:
        """View stored credentials (keys only, not values)."""
        if self.store is None:
            print("❌ Credential store not initialized")
            return

        print("\n📋 Stored credentials:")
        keys = self.store.list_keys()

        if not keys:
            print("  No credentials stored")
        else:
            for key in keys:
                desc = self.CREDENTIALS.get(key, {}).get("description", "Unknown")
                print(f"  • {key}: {desc}")

    def _migrate_from_env(self) -> None:
        """Migrate credentials from environment variables."""
        if self.store is None:
            print("❌ Credential store not initialized")
            return

        print("\n🔄 Migrating from environment variables...\n")

        migrated = []
        for cred_name in self.CREDENTIALS:
            env_value = os.getenv(cred_name)

            # Skip placeholders
            if env_value and env_value not in [
                "your-api-key-here",
                "your-openai-api-key-here",
                "your-deepgram-api-key-here",
                "password",
            ]:
                existing = self.store.get(cred_name)
                if existing:
                    print(f"  ⏭️  {cred_name} already in store, skipping")
                else:
                    self.store.set(cred_name, env_value)
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
        """Test stored credentials."""
        if self.store is None:
            print("❌ Credential store not initialized")
            return

        print("\n🧪 Testing credentials...\n")

        # Test Neo4j
        neo4j_pass = self.store.get("NEO4J_PASSWORD")
        if neo4j_pass:
            print("  • NEO4J_PASSWORD: ✅ Set")
        else:
            print("  • NEO4J_PASSWORD: ❌ Not set")

        # Test OpenAI
        openai_key = self.store.get("OPENAI_API_KEY")
        if openai_key:
            if openai_key.startswith("sk-"):
                print("  • OPENAI_API_KEY: ✅ Set (format looks valid)")
            else:
                print("  • OPENAI_API_KEY: ⚠️  Set (format may be invalid)")
        else:
            print("  • OPENAI_API_KEY: ❌ Not set (REQUIRED)")

        # Test Deepgram
        deepgram_key = self.store.get("DEEPGRAM_API_KEY")
        if deepgram_key:
            print("  • DEEPGRAM_API_KEY: ✅ Set")
        else:
            print("  • DEEPGRAM_API_KEY: ⚠️  Not set (optional)")

    def _remove_credential(self) -> None:
        """Remove a credential from the store."""
        if self.store is None:
            print("❌ Credential store not initialized")
            return

        keys = self.store.list_keys()

        if not keys:
            print("\n  No credentials to remove")
            return

        print("\nStored credentials:")
        for i, key in enumerate(keys, 1):
            print(f"  {i}. {key}")

        choice = input(f"\nSelect credential to remove [1-{len(keys)}]: ").strip()

        try:
            idx = int(choice) - 1
            key_to_remove = keys[idx]

            confirm = (
                input(f"\n⚠️  Remove {key_to_remove}? This cannot be undone. [y/N]: ")
                .strip()
                .lower()
            )
            if confirm == "y":
                self.store.delete(key_to_remove)
                print(f"✅ {key_to_remove} removed")
        except (ValueError, IndexError):
            print("❌ Invalid choice")


def main():
    """Main entry point for credential setup."""
    try:
        setup = CredentialSetup()
        setup.run()
    except KeyboardInterrupt:
        print("\n\n👋 Credential setup cancelled")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
