#!/usr/bin/env python3
"""
Set Neo4j Password in Encrypted Credential Store
==================================================

Simple script to securely store your Neo4j password.
"""

import sys
import traceback
from getpass import getpass

from dotenv import load_dotenv

from core.config.credential_store import get_credential_store

# Add parent directory to path

load_dotenv()


def main():
    """Set Neo4j password in encrypted credential store."""
    print("=" * 60)
    print("SKUEL - Set Neo4j Password")
    print("=" * 60)
    print()
    print("This will store your Neo4j password securely in the")
    print("encrypted credential store at: ~/.skuel/credentials.enc")
    print()

    try:
        # Get credential store
        store = get_credential_store()
        print("✅ Credential store initialized")
        print()

        # Check if password already exists
        if store.exists("NEO4J_PASSWORD"):
            print("⚠️  Neo4j password already exists in credential store")
            overwrite = input("   Overwrite existing password? (y/n): ").strip().lower()
            if overwrite != "y":
                print("   Cancelled. Password not changed.")
                return

        # Get password from user
        password = getpass("Enter your Neo4j password: ")
        if not password:
            print("❌ Password cannot be empty")
            return

        # Confirm password
        confirm = getpass("Confirm password: ")
        if password != confirm:
            print("❌ Passwords do not match")
            return

        # Store password
        store.set("NEO4J_PASSWORD", password)

        print()
        print("=" * 60)
        print("✅ SUCCESS!")
        print("=" * 60)
        print()
        print("Neo4j password has been securely stored.")
        print()
        print("The password is encrypted and stored at:")
        print(f"  {store.store_path}")
        print()
        print("You can now start SKUEL:")
        print("  poetry run python main.py")
        print()

    except ValueError as e:
        print(f"\n❌ Error: {e}")
        print()
        print("Make sure SKUEL_MASTER_KEY is set in your .env file:")
        print("  SKUEL_MASTER_KEY=<your-master-key>")
        print()
        print("Generate a new master key with:")
        print("  openssl rand -base64 32")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
